#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import ast
import json
import os
import re
import sys


CONVERTER_TO_TYPE = {
    "int": "integer",
    "float": "number",
    "path": "string",
    "string": "string",
    "uuid": "string",
}


def _string_value(node):
    if isinstance(node, ast.Str):
        return node.s
    if hasattr(ast, "Constant") and isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _list_of_strings(node):
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    values = []
    for item in node.elts:
        value = _string_value(item)
        if value is not None:
            values.append(value)
    return values


def _decorator_name(decorator):
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    if isinstance(decorator, ast.Call):
        return _decorator_name(decorator.func)
    return None


def _parse_route_decorator(decorator):
    if not isinstance(decorator, ast.Call):
        return None
    if _decorator_name(decorator.func) != "route":
        return None

    route_path = None
    methods = None

    if decorator.args:
        route_path = _string_value(decorator.args[0])

    for keyword in decorator.keywords:
        if keyword.arg == "methods":
            methods = _list_of_strings(keyword.value)

    if route_path is None:
        return None

    if not methods:
        methods = ["GET"]

    return {
        "path": route_path,
        "methods": [m.upper() for m in methods],
    }


def _parse_json_description_file(decorator):
    if not isinstance(decorator, ast.Call):
        return None
    if _decorator_name(decorator.func) != "json_description":
        return None

    for keyword in decorator.keywords:
        if keyword.arg == "file":
            return _string_value(keyword.value)
    return None


def _flask_path_to_openapi(path):
    return re.sub(r"<(?:(?:int|float|string|path|uuid):)?([^>]+)>", r"{\1}", path)


def _extract_path_parameters(path):
    found = re.findall(r"<(?:(int|float|string|path|uuid):)?([^>]+)>", path)
    params = []
    for converter, name in found:
        params.append(
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": CONVERTER_TO_TYPE.get(converter, "string")},
            }
        )
    return params


def _default_operation(method, openapi_path, path_parameters):
    operation = {
        "summary": "%s %s" % (method, openapi_path),
        "responses": {"200": {"description": "Success"}},
    }
    if path_parameters:
        operation["parameters"] = path_parameters
    if method in ["POST", "PUT", "PATCH"]:
        operation["requestBody"] = {
            "required": False,
            "content": {
                "application/json": {
                    "schema": {"type": "object"}
                }
            },
        }
    return operation


def _walk_python_files(root_path):
    for root, _, files in os.walk(root_path):
        for file_name in files:
            if file_name.endswith(".py") and file_name != "__init__.py":
                yield os.path.join(root, file_name)


def _load_json_description_file(app_web_root, file_ref, cache):
    if not file_ref:
        return {}

    if file_ref in cache:
        return cache[file_ref]

    target = file_ref
    if not os.path.isabs(target):
        target = os.path.join(app_web_root, target)
    target = os.path.normpath(target)

    if not os.path.exists(target):
        cache[file_ref] = {}
        return {}

    with open(target, "r", encoding="utf-8") as handle:
        parsed = json.load(handle)

    cache[file_ref] = parsed if isinstance(parsed, dict) else {}
    return cache[file_ref]


def _operation_metadata_from_description(description_map, openapi_path, method):
    route_description = description_map.get(openapi_path)
    if not isinstance(route_description, dict):
        return {}

    # Supports:
    # 1) {"/route": {"summary": "...", ...}} applied to all methods
    # 2) {"/route": {"get": {...}, "post": {...}}}
    # 3) {"/route": {"method": "POST", "tags": [...], ...}}
    method_key = method.lower()
    if method_key in route_description and isinstance(route_description[method_key], dict):
        return dict(route_description[method_key])

    raw_filter = route_description.get("method", route_description.get("methods"))
    if raw_filter is not None:
        allowed_methods = []
        if isinstance(raw_filter, str):
            allowed_methods = [raw_filter.upper()]
        elif isinstance(raw_filter, list):
            for candidate in raw_filter:
                if isinstance(candidate, str):
                    allowed_methods.append(candidate.upper())

        if allowed_methods and method.upper() not in allowed_methods:
            return {}

    metadata = dict(route_description)
    metadata.pop("method", None)
    metadata.pop("methods", None)
    return metadata


def _merge_parameters(existing_parameters, extra_parameters):
    if not extra_parameters:
        return existing_parameters

    merged = list(existing_parameters or [])
    known = {(p.get("name"), p.get("in")) for p in merged if isinstance(p, dict)}
    for param in extra_parameters:
        if not isinstance(param, dict):
            continue
        key = (param.get("name"), param.get("in"))
        if key not in known:
            merged.append(param)
            known.add(key)
    return merged


def _build_paths(routes_root, app_web_root):
    paths = {}
    description_cache = {}

    for file_path in _walk_python_files(routes_root):
        with open(file_path, "r", encoding="utf-8") as source_file:
            source = source_file.read()

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError:
            continue

        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue

            route_defs = []
            json_description_file = None

            for decorator in node.decorator_list:
                route_def = _parse_route_decorator(decorator)
                if route_def is not None:
                    route_defs.append(route_def)

                description_file = _parse_json_description_file(decorator)
                if description_file:
                    json_description_file = description_file

            if not route_defs:
                continue

            description_map = _load_json_description_file(
                app_web_root=app_web_root,
                file_ref=json_description_file,
                cache=description_cache,
            )

            for route_def in route_defs:
                flask_path = route_def["path"]
                if not flask_path.startswith("/api"):
                    continue

                openapi_path = _flask_path_to_openapi(flask_path)
                path_parameters = _extract_path_parameters(flask_path)
                if openapi_path not in paths:
                    paths[openapi_path] = {}

                for method in route_def["methods"]:
                    operation = _default_operation(method, openapi_path, path_parameters)
                    description_operation = _operation_metadata_from_description(
                        description_map=description_map,
                        openapi_path=openapi_path,
                        method=method,
                    )
                    if description_operation:
                        operation.update(description_operation)
                        if path_parameters and "parameters" in description_operation:
                            operation["parameters"] = _merge_parameters(
                                existing_parameters=path_parameters,
                                extra_parameters=description_operation.get("parameters"),
                            )

                    paths[openapi_path][method.lower()] = operation

    return paths


def build_openapi_spec(server_url, routes_root, app_web_root):
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Stellar API",
            "version": "1.0.0",
            "description": "OpenAPI description for the Stellar backend.",
        },
        "servers": [
            {"url": server_url}
        ],
        "components": {
            "securitySchemes": {
                "cookieAuth": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "session",
                }
            }
        },
        "paths": _build_paths(routes_root=routes_root, app_web_root=app_web_root),
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate OpenAPI schema by parsing route files and json_description decorators."
    )
    parser.add_argument(
        "--routes-root",
        default="app/web/api",
        help="Root directory containing Flask route modules to parse.",
    )
    parser.add_argument(
        "--app-web-root",
        default="app/web",
        help="Root directory used to resolve json_description(file=...) paths.",
    )
    parser.add_argument(
        "--server-url",
        default="http://localhost:9000",
        help="Server URL to embed in the generated OpenAPI spec.",
    )
    parser.add_argument(
        "--output",
        default="app/web/api/openapi.generated.json",
        help="Output file path for generated OpenAPI schema.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    routes_root = os.path.abspath(args.routes_root)
    app_web_root = os.path.abspath(args.app_web_root)

    if not os.path.isdir(routes_root):
        raise ValueError("routes-root does not exist or is not a directory: %s" % routes_root)
    if not os.path.isdir(app_web_root):
        raise ValueError("app-web-root does not exist or is not a directory: %s" % app_web_root)

    spec = build_openapi_spec(
        server_url=args.server_url,
        routes_root=routes_root,
        app_web_root=app_web_root,
    )

    output_path = os.path.abspath(args.output)
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(spec, output_file, indent=2, sort_keys=True)
        output_file.write("\n")

    print("OpenAPI schema generated: %s" % output_path)
    print("Paths discovered: %s" % len(spec.get("paths", {})))


if __name__ == "__main__":
    sys.exit(main())
