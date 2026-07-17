"""Canonical input-field extraction from normalized schemas and parameters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import (
    FieldLocation,
    ParsedField,
    ParsedParameter,
    ParsedRequestBody,
    ParsedSchema,
)


def schema_fields(
    schema: Mapping[str, Any],
    *,
    location: FieldLocation = "body",
    parsed_schema: ParsedSchema | None = None,
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
            parsed_schema=(parsed_schema.properties or {}).get(name)
            if parsed_schema is not None
            else None,
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
            parsed_schema=parameter.parsed_schema,
        )
        for parameter in parameters
    )
    if request_body is None:
        return _ensure_unique_argument_names(parameter_fields)

    body_location: FieldLocation = (
        "form" if request_body.content_type == "multipart/form-data" else "body"
    )
    body_fields = schema_fields(
        request_body.schema,
        location=body_location,
        parsed_schema=request_body.parsed_schema,
    )
    if not body_fields and request_body.content_type == "application/json":
        body_fields = (
            ParsedField(
                name="body",
                argument_name="body",
                location="body",
                schema=request_body.schema,
                required=request_body.required,
                description=_string_or_none(request_body.schema.get("description")),
                default=request_body.schema.get("default"),
                has_default="default" in request_body.schema,
                is_body_root=True,
                parsed_schema=request_body.parsed_schema,
            ),
        )

    return _ensure_unique_argument_names(
        (
            *parameter_fields,
            *body_fields,
        )
    )


def _ensure_unique_argument_names(
    fields: tuple[ParsedField, ...],
) -> tuple[ParsedField, ...]:
    fields_by_argument_name: dict[str, ParsedField] = {}
    for field in fields:
        previous = fields_by_argument_name.get(field.argument_name)
        if previous is not None:
            raise ValueError(
                "OpenAPI operation fields normalize to the same argument name "
                f"{field.argument_name!r}: "
                f"{previous.location} {previous.name!r} and "
                f"{field.location} {field.name!r}"
            )
        fields_by_argument_name[field.argument_name] = field
    return fields


def _argument_name(name: str, location: str) -> str:
    if location != "header":
        return name
    argument_name = name.lower()
    argument_name = argument_name.removeprefix("x-")
    return argument_name.replace("-", "_")


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None
