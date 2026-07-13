import pytest
import ramp_tool_openapi
from ramp_tool_openapi import parse_openapi_operations
from ramp_tool_openapi.parser import (
    _extract_parameters,
    _extract_request_body,
    _extract_response,
)

AGENT_TOOLS_PREFIX = "/developer/v1/agent-tools/"


def test_package_exports_only_initial_public_api() -> None:
    assert ramp_tool_openapi.ParsedOperation is not None
    assert ramp_tool_openapi.ParsedParameter is not None
    assert ramp_tool_openapi.ParsedRequestBody is not None
    assert ramp_tool_openapi.ParsedResponse is not None
    assert ramp_tool_openapi.ParsedSecurityRequirement is not None
    assert ramp_tool_openapi.ParsedSecuritySchemeRequirement is not None
    assert ramp_tool_openapi.parse_openapi_operations is parse_openapi_operations
    assert ramp_tool_openapi.resolve_local_ref is not None
    assert not hasattr(ramp_tool_openapi, "operation_category")
    assert not hasattr(ramp_tool_openapi, "operation_available_on_platform")


def test_parse_openapi_operations_extracts_neutral_operation_facts() -> None:
    spec = {
        "openapi": "3.0.2",
        "components": {
            "schemas": {
                "Request": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["id", "rationale"],
                },
                "Response": {"type": "object"},
            }
        },
        "paths": {
            f"{AGENT_TOOLS_PREFIX}get-transaction-suggested-memos": {
                "post": {
                    "operationId": (
                        "post_agent_tool_api___get_transaction_suggested_memos"
                    ),
                    "summary": "Get suggested memos",
                    "description": "Return memo candidates.",
                    "tags": ["Agent Tool", "transactions"],
                    "x-alias": "memo-suggestions",
                    "x-platforms": ["cli", "mcp"],
                    "security": [{"oauth2": ["memos:read"]}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Request"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Response"}
                                }
                            },
                        }
                    },
                }
            }
        },
    }

    operations = parse_openapi_operations(spec)

    assert len(operations) == 1
    operation = operations[0]
    assert (
        operation.operation_key
        == f"post {AGENT_TOOLS_PREFIX}get-transaction-suggested-memos"
    )
    assert operation.method == "post"
    assert (
        operation.operation_id
        == "post_agent_tool_api___get_transaction_suggested_memos"
    )
    assert operation.tags == ("Agent Tool", "transactions")
    assert operation.platforms == ("cli", "mcp")
    assert operation.alias == "memo-suggestions"
    assert operation.extensions == {
        "x-alias": "memo-suggestions",
        "x-platforms": ["cli", "mcp"],
    }
    assert len(operation.security_requirements) == 1
    assert [
        (scheme.scheme_name, scheme.scopes)
        for scheme in operation.security_requirements[0].schemes
    ] == [("oauth2", ("memos:read",))]
    assert operation.scopes == ("memos:read",)
    assert operation.request_body is not None
    assert operation.request_body.schema_name == "Request"
    assert operation.request_body.required is True
    assert operation.response is not None
    assert operation.response.schema_name == "Response"


def test_parse_openapi_operations_resolves_component_reference_objects() -> None:
    spec = {
        "openapi": "3.0.2",
        "components": {
            "parameters": {
                "BusinessId": {
                    "name": "business_id",
                    "in": "path",
                    "required": True,
                    "description": "Business identifier.",
                    "schema": {"type": "string"},
                },
                "Cursor": {
                    "name": "cursor",
                    "in": "query",
                    "schema": {"type": "string"},
                },
                "RequiredCursor": {
                    "name": "cursor",
                    "in": "query",
                    "required": True,
                    "schema": {"type": "integer"},
                },
            },
            "requestBodies": {
                "CreateMemoRequestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Request"}
                        }
                    },
                }
            },
            "responses": {
                "CreateMemoResponse": {
                    "description": "Created",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Response"}
                        }
                    },
                }
            },
            "schemas": {
                "Request": {"type": "object"},
                "Response": {"type": "object"},
            },
        },
        "paths": {
            f"{AGENT_TOOLS_PREFIX}create-memo/{{business_id}}": {
                "parameters": [
                    {"$ref": "#/components/parameters/BusinessId"},
                    {"$ref": "#/components/parameters/Cursor"},
                ],
                "post": {
                    "operationId": "post_agent_tool_api___create_memo",
                    "summary": "Create memo",
                    "tags": ["Agent Tool", "transactions"],
                    "x-platforms": ["mcp"],
                    "parameters": [{"$ref": "#/components/parameters/RequiredCursor"}],
                    "requestBody": {
                        "$ref": "#/components/requestBodies/CreateMemoRequestBody"
                    },
                    "responses": {
                        "201": {"$ref": "#/components/responses/CreateMemoResponse"}
                    },
                },
            }
        },
    }

    operations = parse_openapi_operations(spec)

    assert len(operations) == 1
    operation = operations[0]
    assert [
        (param.name, param.location, param.required, param.schema)
        for param in operation.parameters
    ] == [
        ("business_id", "path", True, {"type": "string"}),
        ("cursor", "query", True, {"type": "integer"}),
    ]
    assert operation.parameters[0].description == "Business identifier."
    assert operation.request_body is not None
    assert operation.request_body.schema_name == "Request"
    assert operation.request_body.required is True
    assert operation.response is not None
    assert operation.response.status_code == "201"
    assert operation.response.schema_name == "Response"


def test_operation_key_is_unique_for_multi_method_agent_tool_paths() -> None:
    path = f"{AGENT_TOOLS_PREFIX}procurement-draft"
    spec = {
        "openapi": "3.0.2",
        "paths": {
            path: {
                "delete": {"operationId": "delete_procurement_draft"},
                "get": {"operationId": "get_procurement_draft"},
                "post": {"operationId": "post_procurement_draft"},
            }
        },
    }

    operations = parse_openapi_operations(spec)

    assert [operation.operation_key for operation in operations] == [
        f"delete {path}",
        f"get {path}",
        f"post {path}",
    ]
    assert len({operation.operation_key for operation in operations}) == 3


def test_security_requirements_preserve_openapi_boolean_structure() -> None:
    spec = {
        "openapi": "3.0.2",
        "components": {
            "securitySchemes": {
                "rampOAuth": {"type": "oauth2", "flows": {}},
                "serviceKey": {"type": "apiKey", "in": "header", "name": "X-Key"},
            }
        },
        "security": [
            {"rampOAuth": ["transactions:read"], "serviceKey": []},
            {"rampOAuth": ["transactions:admin"]},
        ],
        "paths": {
            "/inherited": {"get": {}},
            "/anonymous": {"get": {"security": []}},
        },
    }

    inherited, anonymous = parse_openapi_operations(spec)

    assert [
        [(scheme.scheme_name, scheme.scopes) for scheme in requirement.schemes]
        for requirement in inherited.security_requirements
    ] == [
        [("rampOAuth", ("transactions:read",)), ("serviceKey", ())],
        [("rampOAuth", ("transactions:admin",))],
    ]
    assert inherited.scopes == ("transactions:read", "transactions:admin")
    assert anonymous.security_requirements == ()
    assert anonymous.scopes == ()


def test_explicit_null_security_is_rejected() -> None:
    spec = {
        "openapi": "3.0.2",
        "security": [{"oauth2": ["transactions:read"]}],
        "paths": {
            "/invalid": {"get": {"security": None}},
        },
    }

    with pytest.raises(ValueError, match="security requirements must be an array"):
        parse_openapi_operations(spec)


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/allowed/../admin", id="dot-segment"),
        pytest.param("/allowed/%2e%2e/admin", id="encoded-dot-segment"),
        pytest.param("/allowed\\admin", id="backslash"),
        pytest.param("/allowed//admin", id="empty-segment"),
        pytest.param("/allowed/\x00admin", id="control-character"),
    ],
)
def test_parse_openapi_operations_rejects_noncanonical_paths(path: str) -> None:
    with pytest.raises(ValueError, match="OpenAPI path"):
        parse_openapi_operations({"paths": {path: {"get": {}}}})


def test_path_prefix_matches_a_complete_path_segment() -> None:
    spec = {
        "paths": {
            "/allowed": {"get": {}},
            "/allowed/child": {"get": {}},
            "/allowed-other": {"get": {}},
        }
    }

    operations = parse_openapi_operations(spec, path_prefix="/allowed")

    assert [operation.path for operation in operations] == [
        "/allowed",
        "/allowed/child",
    ]


def test_parse_openapi_operations_rejects_nonlowercase_http_methods() -> None:
    with pytest.raises(ValueError, match="must be lowercase"):
        parse_openapi_operations({"paths": {"/things": {"GET": {}}}})


def test_reference_resolution_has_a_configurable_depth_limit() -> None:
    parameters = {
        "A": {"$ref": "#/components/parameters/B"},
        "B": {"$ref": "#/components/parameters/C"},
        "C": {"$ref": "#/components/parameters/D"},
        "D": {"name": "cursor", "in": "query", "schema": {"type": "string"}},
    }
    spec = {
        "components": {"parameters": parameters},
        "paths": {
            "/things": {
                "get": {
                    "parameters": [{"$ref": "#/components/parameters/A"}],
                }
            }
        },
    }

    with pytest.raises(ValueError, match="configured maximum of 3"):
        parse_openapi_operations(spec, max_reference_depth=3)

    operations = parse_openapi_operations(spec, max_reference_depth=4)
    assert operations[0].parameters[0].name == "cursor"


def test_ref_aware_helpers_raise_for_refs_without_spec() -> None:
    with pytest.raises(ValueError, match="cannot be resolved without a spec"):
        _extract_parameters([{"$ref": "#/components/parameters/BusinessId"}])

    with pytest.raises(ValueError, match="cannot be resolved without a spec"):
        _extract_request_body(
            {"requestBody": {"$ref": "#/components/requestBodies/CreateMemo"}}
        )

    with pytest.raises(ValueError, match="cannot be resolved without a spec"):
        _extract_response(
            {"responses": {"200": {"$ref": "#/components/responses/CreateMemo"}}}
        )
