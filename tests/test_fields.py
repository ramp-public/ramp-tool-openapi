import pytest
from ramp_tool_openapi import (
    get_openapi_schema,
    parse_openapi_operations,
    parse_openapi_schemas,
    prepare_request,
)


def test_operation_fields_are_ready_for_adapters_and_request_preparation() -> None:
    spec = {
        "components": {
            "schemas": {
                "BaseRequest": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Display name",
                        }
                    },
                    "required": ["name"],
                },
                "Request": {
                    "allOf": [
                        {"$ref": "#/components/schemas/BaseRequest"},
                        {
                            "type": "object",
                            "properties": {"count": {"type": "integer", "default": 1}},
                        },
                    ]
                },
            }
        },
        "paths": {
            "/things/{thing_id}": {
                "post": {
                    "x-platforms": ["mcp", "cli"],
                    "parameters": [
                        {
                            "name": "thing_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "verbose",
                            "in": "query",
                            "schema": {"type": "boolean"},
                        },
                        {
                            "name": "X-Idempotency-Key",
                            "in": "header",
                            "schema": {"type": "string"},
                        },
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Request"}
                            }
                        }
                    },
                }
            }
        },
    }

    operation = parse_openapi_operations(spec)[0]

    assert operation.supports_platform("mcp") is True
    assert [
        (
            field.name,
            field.argument_name,
            field.location,
            field.required,
            field.has_default,
        )
        for field in operation.fields
    ] == [
        ("thing_id", "thing_id", "path", True, False),
        ("verbose", "verbose", "query", False, False),
        ("X-Idempotency-Key", "idempotency_key", "header", False, False),
        ("name", "name", "body", True, False),
        ("count", "count", "body", False, True),
    ]
    assert operation.fields[3].description == "Display name"
    assert operation.request_body.parsed_schema is not None
    assert operation.request_body.parsed_schema.name == "Request"
    assert operation.fields[3].parsed_schema is not None
    assert operation.fields[3].parsed_schema.type == "string"
    assert "$ref" not in repr(operation.request_body.schema)
    assert "allOf" not in repr(operation.request_body.schema)

    request = prepare_request(
        operation,
        {
            "thing_id": "abc/123",
            "verbose": True,
            "idempotency_key": "idem-1",
            "name": "Example",
            "count": 2,
            "rationale": "local-only value",
        },
    )

    assert request.method == "POST"
    assert request.path == "/things/abc%2F123"
    assert request.query == {"verbose": True}
    assert request.headers == {"X-Idempotency-Key": "idem-1"}
    assert request.json == {"name": "Example", "count": 2}


def test_missing_platform_metadata_uses_caller_default() -> None:
    operation = parse_openapi_operations({"paths": {"/things": {"get": {}}}})[0]

    assert operation.supports_platform("mcp") is False
    assert operation.supports_platform("mcp", default=True) is True


def test_prepare_request_preserves_raw_json_body_values() -> None:
    spec = {
        "paths": {
            "/things": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"amount": {"type": "integer"}},
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    operation = parse_openapi_operations(spec)[0]

    prepared = prepare_request(
        operation,
        {"amount": 10},
        body={"amount": 20, "additional_field": "kept"},
    )

    assert prepared.json == {"amount": 20, "additional_field": "kept"}


def test_parse_openapi_schemas_returns_normalized_named_schemas() -> None:
    spec = {
        "components": {
            "schemas": {
                "Details": {
                    "type": "object",
                    "properties": {"memo": {"type": "string"}},
                },
                "Request": {
                    "type": "object",
                    "properties": {"details": {"$ref": "#/components/schemas/Details"}},
                },
            }
        }
    }

    schemas = parse_openapi_schemas(spec)

    assert schemas["Request"]["properties"]["details"] == {
        "type": "object",
        "properties": {"memo": {"type": "string"}},
    }

    combined = get_openapi_schema(spec, "Details+Request")
    assert set(combined["properties"]) == {"memo", "details"}


def test_prepare_multipart_request_separates_fields_files_and_cookies() -> None:
    spec = {
        "paths": {
            "/documents": {
                "post": {
                    "parameters": [
                        {
                            "name": "session",
                            "in": "cookie",
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "document": {
                                            "type": "string",
                                            "format": "binary",
                                        },
                                    },
                                }
                            }
                        }
                    },
                }
            }
        }
    }
    operation = parse_openapi_operations(spec)[0]

    prepared = prepare_request(
        operation,
        {"session": "session-1", "label": "Receipt", "document": "/tmp/a.pdf"},
    )

    assert prepared.cookies == {"session": "session-1"}
    assert prepared.form == {"label": "Receipt"}
    assert prepared.files == {"document": "/tmp/a.pdf"}
    assert prepared.json is None


def test_operation_fields_reject_colliding_argument_names() -> None:
    spec = {
        "paths": {
            "/things": {
                "post": {
                    "parameters": [
                        {
                            "name": "X-Foo",
                            "in": "header",
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"foo": {"type": "string"}},
                                }
                            }
                        }
                    },
                }
            }
        }
    }

    with pytest.raises(ValueError, match="same argument name 'foo'"):
        parse_openapi_operations(spec)


def test_prepare_request_supports_a_whole_json_body() -> None:
    spec = {
        "paths": {
            "/things": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                }
                            }
                        },
                    }
                }
            }
        }
    }
    operation = parse_openapi_operations(spec)[0]

    assert len(operation.fields) == 1
    assert operation.fields[0].argument_name == "body"
    assert operation.fields[0].is_body_root is True

    prepared = prepare_request(operation, {"body": ["one", "two"]})

    assert prepared.json == ["one", "two"]
    assert prepared.has_json_body is True


def test_prepare_request_distinguishes_json_null_from_no_json_body() -> None:
    spec = {
        "paths": {
            "/things": {
                "post": {
                    "requestBody": {
                        "content": {"application/json": {"schema": {"nullable": True}}}
                    }
                }
            }
        }
    }
    operation = parse_openapi_operations(spec)[0]

    prepared = prepare_request(operation, {}, body=None)

    assert prepared.json is None
    assert prepared.has_json_body is True

    omitted = prepare_request(operation, {})

    assert omitted.json is None
    assert omitted.has_json_body is False


def test_prepare_request_emits_empty_required_json_object() -> None:
    spec = {
        "paths": {
            "/things": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"note": {"type": "string"}},
                                }
                            }
                        },
                    }
                }
            }
        }
    }
    operation = parse_openapi_operations(spec)[0]

    prepared = prepare_request(operation, {})

    assert prepared.json == {}
    assert prepared.has_json_body is True
