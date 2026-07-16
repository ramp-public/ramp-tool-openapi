"""Canonical input-field extraction from normalized schemas and parameters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import FieldLocation, ParsedField, ParsedParameter, ParsedRequestBody


def schema_fields(
    schema: Mapping[str, Any],
    *,
    location: FieldLocation = "body",
) -> tuple[ParsedField, ...]:
    """Return the top-level properties accepted by an object schema."""

    required = set(schema.get("required", ()))
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return ()

    return tuple(
        ParsedField(
            name=name,
            argument_name=name,
            location=location,
            schema=dict(property_schema),
            required=name in required,
            description=_string_or_none(property_schema.get("description")),
            default=property_schema.get("default"),
            has_default="default" in property_schema,
        )
        for name, property_schema in properties.items()
        if isinstance(name, str) and isinstance(property_schema, Mapping)
    )


def operation_fields(
    parameters: tuple[ParsedParameter, ...],
    request_body: ParsedRequestBody | None,
) -> tuple[ParsedField, ...]:
    """Combine operation parameters and request-body properties."""

    parameter_fields = tuple(
        ParsedField(
            name=parameter.name,
            argument_name=_argument_name(parameter.name, parameter.location),
            location=parameter.location,
            schema=parameter.schema,
            required=parameter.required,
            description=parameter.description,
            default=parameter.schema.get("default"),
            has_default="default" in parameter.schema,
        )
        for parameter in parameters
    )
    if request_body is None:
        return parameter_fields

    body_location: FieldLocation = (
        "form" if request_body.content_type == "multipart/form-data" else "body"
    )
    return (
        *parameter_fields,
        *schema_fields(request_body.schema, location=body_location),
    )


def _argument_name(name: str, location: str) -> str:
    if location != "header":
        return name
    argument_name = name.lower()
    if argument_name.startswith("x-"):
        argument_name = argument_name[2:]
    return argument_name.replace("-", "_")


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None
