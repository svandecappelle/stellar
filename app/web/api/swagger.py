# -*- coding: utf-8 -*-

import json
import os

from flask import jsonify, render_template_string, request

from app.application import app, json_description

OPENAPI_GENERATED_PATH = os.path.join(
    os.path.dirname(__file__),
    "openapi.generated.json",
)


def _to_openapi_path(rule_text):
    return re.sub(r"<(?:(?:int|float|string|path|uuid):)?([^>]+)>", r"{\1}", rule_text)


def _extract_parameters(rule_text):
    found = re.findall(r"<(?:(int|float|string|path|uuid):)?([^>]+)>", rule_text)
    params = []
    for converter, name in found:
        schema_type = "string"
        if converter == "int":
            schema_type = "integer"
        elif converter == "float":
            schema_type = "number"
        params.append(
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": schema_type},
            }
        )
    return params


def _default_operation(method, path, parameters):
    operation = {
        "summary": "%s %s" % (method, path),
        "responses": {"200": {"description": "Success"}},
    }
    if parameters:
        operation["parameters"] = parameters
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


def _build_paths():
    try:
        with open(OPENAPI_GENERATED_PATH, "r", encoding="utf-8") as handle:
            content = json.load(handle)
    except (OSError, ValueError):
        return {}

    if not isinstance(content, dict):
        return {}

    paths = content.get("paths", {})
    if not isinstance(paths, dict):
        return {}

    return paths


def build_openapi_spec(server_url):
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
        "paths": _build_paths(),
    }


@app.route('/api/openapi.json', methods=['GET'])
@json_description(file='descriptions/documentation.json')
def openapi_spec():
    server_url = request.host_url.rstrip('/')
    return jsonify(build_openapi_spec(server_url=server_url))


@app.route('/api/docs', methods=['GET'])
@json_description(file='descriptions/documentation.json')
def swagger_ui():
    return render_template_string(
        """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Stellar API Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({
      url: '/api/openapi.json',
      dom_id: '#swagger-ui',
      deepLinking: true,
      presets: [SwaggerUIBundle.presets.apis],
      layout: 'BaseLayout'
    });
  </script>
</body>
</html>
        """
    )