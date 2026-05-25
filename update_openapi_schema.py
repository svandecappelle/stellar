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


def _is_request_json_get_call(node):
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "get":
        return False
    json_attr = node.func.value
    if not isinstance(json_attr, ast.Attribute) or json_attr.attr != "json":
        return False
    return isinstance(json_attr.value, ast.Name) and json_attr.value.id == "request"


def _request_json_key_from_call(node):
    if not _is_request_json_get_call(node):
        return None
    if node.args:
        return _string_value(node.args[0])
    return None


def _literal_schema(node):
    if hasattr(ast, "Constant") and isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool):
            return {"type": "boolean"}
        if isinstance(value, int):
            return {"type": "integer"}
        if isinstance(value, float):
            return {"type": "number"}
        if isinstance(value, str):
            return {"type": "string"}
        if value is None:
            return {"nullable": True}

    if isinstance(node, ast.Dict):
        properties = {}
        required = []
        for key_node, value_node in zip(node.keys, node.values):
            key = _string_value(key_node)
            if key is None:
                continue
            properties[key] = _literal_schema(value_node)
            required.append(key)

        schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema

    if isinstance(node, (ast.List, ast.Tuple)):
        item_schema = {}
        if node.elts:
            item_schema = _literal_schema(node.elts[0])
        return {
            "type": "array",
            "items": item_schema,
        }

    if isinstance(node, ast.Call):
        # jsonify({...}) or jsonify([...])
        if isinstance(node.func, ast.Name) and node.func.id == "jsonify" and node.args:
            return _literal_schema(node.args[0])

    return {}


def _schema_from_node(node, variable_schemas, model_serialize_schemas):
    if isinstance(node, ast.Name) and node.id in variable_schemas:
        return variable_schemas[node.id]

    if isinstance(node, ast.Attribute):
        if node.attr == "serialize" and isinstance(node.value, ast.Name):
            return variable_schemas.get(node.value.id, {})
        return {}

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "jsonify" and node.args:
            return _schema_from_node(node.args[0], variable_schemas, model_serialize_schemas)

        model_schema = _schema_from_model_call(node, model_serialize_schemas)
        if model_schema:
            return model_schema

    if isinstance(node, ast.Dict):
        properties = {}
        required = []
        for key_node, value_node in zip(node.keys, node.values):
            key = _string_value(key_node)
            if key is None:
                continue
            value_schema = _schema_from_node(value_node, variable_schemas, model_serialize_schemas)
            if not value_schema:
                value_schema = _literal_schema(value_node)
            properties[key] = value_schema
            required.append(key)

        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    if isinstance(node, (ast.List, ast.Tuple)):
        item_schema = {}
        if node.elts:
            item_schema = _schema_from_node(node.elts[0], variable_schemas, model_serialize_schemas)
            if not item_schema:
                item_schema = _literal_schema(node.elts[0])
        return {"type": "array", "items": item_schema}

    return _literal_schema(node)


def _schema_from_model_call(node, model_serialize_schemas):
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Attribute):
        return None
    if not isinstance(node.func.value, ast.Name):
        return None

    class_name = node.func.value.id
    method_name = node.func.attr
    base_schema = model_serialize_schemas.get(class_name)
    if not base_schema:
        return None

    if method_name == "all":
        return {"type": "array", "items": base_schema}
    if method_name in ["get", "create", "new"]:
        return base_schema
    return None


def _find_serialize_function(class_node):
    for member in class_node.body:
        if isinstance(member, ast.FunctionDef) and member.name == "serialize":
            return member
    return None


def _extract_return_schema_from_function(function_node):
    for child in ast.walk(function_node):
        if isinstance(child, ast.Return) and child.value is not None:
            schema = _literal_schema(child.value)
            if schema:
                return schema
    return None


def _build_model_serialize_schema_index(models_root):
    schemas = {}
    if not os.path.isdir(models_root):
        return schemas

    for file_path in _walk_python_files(models_root):
        try:
            with open(file_path, "r", encoding="utf-8") as source_file:
                source = source_file.read()
            tree = ast.parse(source, filename=file_path)
        except (OSError, SyntaxError):
            continue

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            serialize_fn = _find_serialize_function(node)
            if not serialize_fn:
                continue
            schema = _extract_return_schema_from_function(serialize_fn)
            if schema:
                schemas[node.name] = schema

    return schemas


def _infer_variable_schemas(function_node, model_serialize_schemas):
    variable_schemas = {}
    for child in ast.walk(function_node):
        if not isinstance(child, ast.Assign):
            continue
        inferred = _schema_from_model_call(child.value, model_serialize_schemas)
        if not inferred:
            continue
        for target in child.targets:
            if isinstance(target, ast.Name):
                variable_schemas[target.id] = inferred
    return variable_schemas


def _infer_response_schema(function_node, model_serialize_schemas):
    schemas = []
    seen = set()
    variable_schemas = _infer_variable_schemas(function_node, model_serialize_schemas)

    for child in ast.walk(function_node):
        if not isinstance(child, ast.Return) or child.value is None:
            continue

        schema = _schema_from_node(child.value, variable_schemas, model_serialize_schemas)
        if not schema:
            continue

        schema_key = json.dumps(schema, sort_keys=True)
        if schema_key in seen:
            continue
        seen.add(schema_key)
        schemas.append(schema)

    if not schemas:
        return None
    if len(schemas) == 1:
        return schemas[0]
    return {"oneOf": schemas}


def _infer_request_body_schema(function_node):
    properties = {}

    for child in ast.walk(function_node):
        if not isinstance(child, ast.Call):
            continue
        key = _request_json_key_from_call(child)
        if key:
            properties[key] = {"type": "string"}

    if not properties:
        return None

    return {
        "type": "object",
        "properties": properties,
    }


def _infer_function_contract(function_node, model_serialize_schemas):
    return {
        "requestBodySchema": _infer_request_body_schema(function_node),
        "responseSchema": _infer_response_schema(function_node, model_serialize_schemas),
    }


def _merge_responses_with_schema(existing_responses, response_schema):
    if not response_schema:
        return existing_responses

    responses = dict(existing_responses or {})
    success_response = dict(responses.get("200") or {})
    if "description" not in success_response:
        success_response["description"] = "Success"
    if "content" not in success_response:
        success_response["content"] = {
            "application/json": {
                "schema": response_schema
            }
        }
    responses["200"] = success_response
    return responses


def _merge_operation_metadata(operation, metadata):
    merged = dict(operation)
    if not metadata:
        return merged

    metadata_copy = dict(metadata)
    metadata_responses = metadata_copy.pop("responses", None)
    for key, value in metadata_copy.items():
        merged[key] = value

    if metadata_responses is not None:
        combined = dict(merged.get("responses") or {})
        for code, response_value in metadata_responses.items():
            if code in combined and isinstance(combined[code], dict) and isinstance(response_value, dict):
                nested = dict(combined[code])
                nested.update(response_value)
                combined[code] = nested
            else:
                combined[code] = response_value
        merged["responses"] = combined

    return merged


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


def _build_paths(routes_root, app_web_root, models_root):
    paths = {}
    description_cache = {}
    model_serialize_schemas = _build_model_serialize_schema_index(models_root)

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

            function_contract = _infer_function_contract(node, model_serialize_schemas)

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

                    if method in ["POST", "PUT", "PATCH"] and function_contract.get("requestBodySchema"):
                        operation["requestBody"] = {
                            "required": False,
                            "content": {
                                "application/json": {
                                    "schema": function_contract["requestBodySchema"]
                                }
                            },
                        }

                    operation["responses"] = _merge_responses_with_schema(
                        existing_responses=operation.get("responses"),
                        response_schema=function_contract.get("responseSchema"),
                    )

                    description_operation = _operation_metadata_from_description(
                        description_map=description_map,
                        openapi_path=openapi_path,
                        method=method,
                    )
                    if description_operation:
                        operation = _merge_operation_metadata(operation, description_operation)
                        if path_parameters and "parameters" in description_operation:
                            operation["parameters"] = _merge_parameters(
                                existing_parameters=path_parameters,
                                extra_parameters=description_operation.get("parameters"),
                            )

                    paths[openapi_path][method.lower()] = operation

    return paths


def build_openapi_spec(server_url, routes_root, app_web_root):
    project_root = os.path.abspath(os.path.join(app_web_root, os.pardir))
    models_root = os.path.join(project_root, "models")

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
        "paths": _build_paths(
            routes_root=routes_root,
            app_web_root=app_web_root,
            models_root=models_root,
        ),
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
