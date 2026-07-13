#!/bin/bash

set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Error: expected package path and wheel path"
    echo "Usage: $0 <relative_path_to_package> <path_to_wheel>"
    exit 1
fi

PACKAGE_PATH="$1"
WHEEL_PATH="$2"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"

WHEEL_PATH="$(
    python -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$WHEEL_PATH"
)"

if [ ! -f "$WHEEL_PATH" ]; then
    echo "Error: wheel does not exist: $WHEEL_PATH"
    exit 1
fi

echo "Starting ramp-tool-openapi smoke tests"
echo "Package path: $PACKAGE_PATH"
echo "Using wheel: $WHEEL_PATH"
echo "========================================="

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
cd "$WORKDIR"

UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/tool_openapi_uv_cache}" uv run --no-project \
    --python "$PYTHON_VERSION" \
    --with "$WHEEL_PATH" \
    python - <<'PY'
from ramp_tool_openapi import (
    ParsedOperation,
    parse_openapi_operations,
)

AGENT_TOOLS_PREFIX = "/developer/v1/agent-tools/"

spec = {
    "openapi": "3.0.2",
    "components": {
        "schemas": {
            "GetFundsRequest": {
                "type": "object",
                "description": "Fetch funds.",
                "properties": {"business_id": {"type": "string"}},
                "required": ["business_id"],
            },
            "GetFundsResponse": {"type": "object"},
        }
    },
    "paths": {
        f"{AGENT_TOOLS_PREFIX}get-funds": {
            "parameters": [
                {
                    "name": "business_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
            ],
            "post": {
                "operationId": "post_agent_tool_api___get_funds",
                "summary": "Get funds",
                "description": "Return available funds.",
                "tags": ["Agent Tool", "finance"],
                "x-alias": "list",
                "x-platforms": ["cli", "mcp"],
                "security": [{"oauth2": ["funds:read"]}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/GetFundsRequest"
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/GetFundsResponse"
                                }
                            }
                        },
                    }
                },
            },
        }
    },
}

operations = parse_openapi_operations(spec)
assert len(operations) == 1

operation = operations[0]
assert isinstance(operation, ParsedOperation)
assert operation.operation_key == f"post {AGENT_TOOLS_PREFIX}get-funds"
assert operation.path == f"{AGENT_TOOLS_PREFIX}get-funds"
assert operation.method == "post"
assert operation.operation_id == "post_agent_tool_api___get_funds"
assert operation.summary == "Get funds"
assert operation.description == "Return available funds."
assert operation.tags == ("Agent Tool", "finance")
assert operation.platforms == ("cli", "mcp")
assert operation.alias == "list"
assert operation.scopes == ("funds:read",)
assert operation.extensions == {"x-alias": "list", "x-platforms": ["cli", "mcp"]}
assert len(operation.parameters) == 1
assert operation.parameters[0].name == "business_id"
assert operation.parameters[0].location == "path"
assert operation.request_body is not None
assert operation.request_body.schema_name == "GetFundsRequest"
assert operation.request_body.required is True
assert operation.response is not None
assert operation.response.schema_name == "GetFundsResponse"

print("tool_openapi wheel smoke test passed")
PY

echo "========================================="
echo "ramp-tool-openapi smoke tests passed"
