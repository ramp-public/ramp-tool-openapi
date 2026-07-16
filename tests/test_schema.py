import pytest
from ramp_tool_openapi.schema import (
    normalize_schema,
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
