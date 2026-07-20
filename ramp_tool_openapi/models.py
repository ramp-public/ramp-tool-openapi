"""Neutral OpenAPI operation models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ParameterLocation = Literal["path", "query", "header", "cookie"]
FieldLocation = Literal["body", "form", "path", "query", "header", "cookie"]


@dataclass(frozen=True, slots=True)
class ParsedSchema:
    """One normalized schema node with its OpenAPI component identity preserved.

    ``schema`` retains the complete normalized JSON-schema-compatible mapping so
    adapters can continue to honor constraints that are not modeled explicitly.
    The recursive fields provide a transport-neutral graph, allowing consumers
    to traverse schemas without resolving ``$ref`` or ``allOf`` themselves.
    """

    schema: dict[str, Any]
    name: str | None = None
    properties: dict[str, ParsedSchema] | None = None
    items: ParsedSchema | None = None
    one_of: tuple[ParsedSchema, ...] = ()
    any_of: tuple[ParsedSchema, ...] = ()
    additional_properties: bool | ParsedSchema | None = None
    recursive: bool = False

    @property
    def type(self) -> str | None:
        value = self.schema.get("type")
        return value if isinstance(value, str) else None

    @property
    def required(self) -> frozenset[str]:
        value = self.schema.get("required")
        if not isinstance(value, (list, tuple)):
            return frozenset()
        return frozenset(item for item in value if isinstance(item, str))


@dataclass(frozen=True, slots=True)
class ParsedField:
    """One ready-to-adapt operation input."""

    name: str
    argument_name: str
    location: FieldLocation
    schema: dict[str, Any]
    required: bool
    description: str | None = None
    default: Any = None
    has_default: bool = False
    is_body_root: bool = False
    parsed_schema: ParsedSchema | None = None


@dataclass(frozen=True, slots=True)
class ParsedParameter:
    name: str
    location: ParameterLocation
    required: bool
    schema: dict[str, Any]
    description: str | None = None
    parsed_schema: ParsedSchema | None = None


@dataclass(frozen=True, slots=True)
class ParsedRequestBody:
    content_type: str
    schema: dict[str, Any]
    schema_name: str
    required: bool
    parsed_schema: ParsedSchema | None = None


@dataclass(frozen=True, slots=True)
class ParsedResponse:
    status_code: str
    content_type: str
    schema: dict[str, Any]
    schema_name: str
    parsed_schema: ParsedSchema | None = None


@dataclass(frozen=True, slots=True)
class ParsedSecuritySchemeRequirement:
    """One security scheme within an OpenAPI security requirement."""

    scheme_name: str
    scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedSecurityRequirement:
    """Schemes that must all be satisfied for one security alternative."""

    schemes: tuple[ParsedSecuritySchemeRequirement, ...]


@dataclass(frozen=True, slots=True)
class ParsedOperation:
    operation_key: str
    path: str
    method: str
    operation_id: str | None
    summary: str | None
    description: str | None
    tags: tuple[str, ...]
    platforms: tuple[str, ...]
    alias: str | None
    security_requirements: tuple[ParsedSecurityRequirement, ...]
    scopes: tuple[str, ...]
    extensions: dict[str, Any]
    parameters: tuple[ParsedParameter, ...]
    request_body: ParsedRequestBody | None
    response: ParsedResponse | None
    raw_operation: dict[str, Any]
    fields: tuple[ParsedField, ...] = ()
    platforms_declared: bool = False

    def supports_platform(self, platform: str, *, default: bool = False) -> bool:
        if not self.platforms_declared:
            return default
        return platform in self.platforms


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    """Transport-neutral HTTP request parts derived from parsed fields."""

    method: str
    path: str
    query: dict[str, Any]
    headers: dict[str, str]
    cookies: dict[str, str]
    json: Any
    has_json_body: bool
    form: dict[str, Any] | None
    files: dict[str, Any] | None
