import pytest
from ramp_tool_openapi.schema import (
    normalize_schema,
    parse_openapi_schema,
    parse_openapi_schema_models,
    resolve_local_ref,
    schema_ref_name,
)


def test_schema_ref_name_supports_ref_and_all_of() -> None:
    assert schema_ref_name({"$ref": "#/components/schemas/Request"}) == "Request"
    assert (
        schema_ref_name(
            {
                "allOf": [
                    {"$ref": "#/components/schemas/Foo"},
                    {"$ref": "#/components/schemas/Bar"},
                ]
            }
        )
        == "Foo+Bar"
    )
    assert schema_ref_name({"type": "object"}) == ""


def test_resolve_local_ref_resolves_json_pointer_escapes() -> None:
    spec = {"components": {"schemas": {"A/B": {"type": "object"}}}}

    assert resolve_local_ref("#/components/schemas/A~1B", spec) == {"type": "object"}
    assert schema_ref_name({"$ref": "#/components/schemas/A~1B"}) == "A/B"


def test_resolve_local_ref_rejects_remote_refs() -> None:
    with pytest.raises(ValueError):
        resolve_local_ref("https://example.com/schema.json", {})


def test_normalize_schema_stops_at_recursive_reference() -> None:
    schemas = {
        "Node": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "child": {"$ref": "#/components/schemas/Node"},
            },
        }
    }

    assert normalize_schema({"$ref": "#/components/schemas/Node"}, schemas) == {
        "type": "object",
        "properties": {
            "value": {"type": "string"},
            "child": {"type": "object"},
        },
    }


def test_parsed_schema_preserves_nested_component_identity() -> None:
    schemas = {
        "Details": {
            "type": "object",
            "properties": {"memo": {"type": "string"}},
        },
        "Request": {
            "type": "object",
            "properties": {
                "details": {"$ref": "#/components/schemas/Details"},
                "history": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/Details"},
                },
            },
        },
    }

    parsed = parse_openapi_schema({"$ref": "#/components/schemas/Request"}, schemas)

    assert parsed.name == "Request"
    assert parsed.type == "object"
    assert parsed.properties is not None
    assert parsed.properties["details"].name == "Details"
    assert parsed.properties["details"].properties is not None
    assert parsed.properties["details"].properties["memo"].type == "string"
    assert parsed.properties["history"].items is not None
    assert parsed.properties["history"].items.name == "Details"
    assert "$ref" not in repr(parsed.schema)


def test_parsed_schema_marks_recursive_reference_by_name() -> None:
    spec = {
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {"child": {"$ref": "#/components/schemas/Node"}},
                }
            }
        }
    }

    node = parse_openapi_schema_models(spec)["Node"]

    assert node.name == "Node"
    assert node.properties is not None
    child = node.properties["child"]
    assert child.name == "Node"
    assert child.type == "object"
    assert child.recursive is True


def test_named_top_level_reference_is_not_treated_as_recursive() -> None:
    schemas = {
        "Request": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "child": {"$ref": "#/components/schemas/Request"},
            },
        }
    }

    request = parse_openapi_schema(
        {"$ref": "#/components/schemas/Request"},
        schemas,
        name="Request",
        max_reference_depth=1,
    )

    assert request.name == "Request"
    assert request.recursive is False
    assert request.properties is not None
    assert request.properties["value"].type == "string"
    assert request.properties["child"].recursive is True


def test_component_root_does_not_consume_reference_depth_budget() -> None:
    spec = {
        "components": {
            "schemas": {
                "Parent": {
                    "type": "object",
                    "properties": {"child": {"$ref": "#/components/schemas/Child"}},
                },
                "Child": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                },
            }
        }
    }

    parent = parse_openapi_schema_models(spec, max_reference_depth=1)["Parent"]

    assert parent.properties is not None
    assert parent.properties["child"].name == "Child"


def test_parsed_schema_merges_all_of_without_losing_property_names() -> None:
    schemas = {
        "Base": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
        "Details": {
            "type": "object",
            "properties": {"memo": {"type": "string"}},
        },
    }

    parsed = parse_openapi_schema(
        {
            "allOf": [
                {"$ref": "#/components/schemas/Base"},
                {
                    "type": "object",
                    "properties": {"details": {"$ref": "#/components/schemas/Details"}},
                },
            ]
        },
        schemas,
    )

    assert parsed.name == "Base"
    assert parsed.required == frozenset({"id"})
    assert parsed.properties is not None
    assert set(parsed.properties) == {"id", "details"}
    assert parsed.properties["details"].name == "Details"


def test_overlapping_all_of_clears_ambiguous_property_identity() -> None:
    schemas = {
        "X": {
            "type": "object",
            "properties": {"from_x": {"type": "string"}},
        },
        "Y": {
            "type": "object",
            "properties": {"from_y": {"type": "integer"}},
        },
    }
    parsed = parse_openapi_schema(
        {
            "allOf": [
                {
                    "type": "object",
                    "properties": {"p": {"$ref": "#/components/schemas/X"}},
                },
                {
                    "type": "object",
                    "properties": {"p": {"$ref": "#/components/schemas/Y"}},
                },
            ]
        },
        schemas,
    )

    assert parsed.properties is not None
    property_schema = parsed.properties["p"]
    assert property_schema.name is None
    assert property_schema.recursive is False
    assert property_schema.properties is not None
    assert set(property_schema.properties) == {"from_x", "from_y"}


def test_overlapping_all_of_replaces_array_item_identity_with_schema() -> None:
    schemas = {
        "X": {
            "type": "object",
            "properties": {"from_x": {"type": "string"}},
        },
        "Y": {
            "type": "object",
            "properties": {"from_y": {"type": "integer"}},
        },
    }
    parsed = parse_openapi_schema(
        {
            "allOf": [
                {
                    "type": "object",
                    "properties": {
                        "p": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/X"},
                        }
                    },
                },
                {
                    "type": "object",
                    "properties": {
                        "p": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Y"},
                        }
                    },
                },
            ]
        },
        schemas,
    )

    assert parsed.properties is not None
    array_schema = parsed.properties["p"]
    assert array_schema.items is not None
    assert array_schema.items.name == "Y"
    assert array_schema.items.properties is not None
    assert set(array_schema.items.properties) == {"from_y"}
    assert array_schema.items.schema == {
        "type": "object",
        "properties": {"from_y": {"type": "integer"}},
    }


def test_overlapping_all_of_clears_ambiguous_recursion_metadata() -> None:
    recursive_schema = {
        "type": "object",
        "allOf": [
            {"properties": {"p": {"$ref": "#/components/schemas/Recursive"}}},
            {"properties": {"p": {"$ref": "#/components/schemas/Y"}}},
        ],
    }
    schemas = {
        "Recursive": recursive_schema,
        "Y": {
            "type": "object",
            "properties": {"from_y": {"type": "string"}},
        },
    }

    parsed = parse_openapi_schema(recursive_schema, schemas, name="Recursive")

    assert parsed.properties is not None
    property_schema = parsed.properties["p"]
    assert property_schema.name is None
    assert property_schema.recursive is False
    assert property_schema.properties is not None
    assert set(property_schema.properties) == {"from_y"}


def test_normalize_schema_preserves_overlapping_property_constraints() -> None:
    schema = {
        "allOf": [
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 5},
                    "status": {"type": "string", "enum": ["a", "b"]},
                },
            },
            {
                "type": "object",
                "properties": {
                    "name": {"maxLength": 10},
                    "status": {"enum": ["b", "c"]},
                },
            },
        ]
    }

    normalized = normalize_schema(schema, {})

    assert normalized["properties"]["name"] == {
        "type": "string",
        "minLength": 5,
        "maxLength": 10,
    }
    assert normalized["properties"]["status"] == {
        "type": "string",
        "enum": ["b"],
    }
