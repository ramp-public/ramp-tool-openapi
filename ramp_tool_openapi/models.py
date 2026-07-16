"""Neutral OpenAPI operation models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ParameterLocation = Literal["path", "query", "header", "cookie"]
FieldLocation = Literal["body", "form", "path", "query", "header", "cookie"]


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


@dataclass(frozen=True, slots=True)
class ParsedParameter:
    name: str
    location: ParameterLocation
    required: bool
    schema: dict[str, Any]
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedRequestBody:
    content_type: str
    schema: dict[str, Any]
    schema_name: str
    required: bool


@dataclass(frozen=True, slots=True)
class ParsedResponse:
    status_code: str
    content_type: str
    schema: dict[str, Any]
    schema_name: str


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
    json: dict[str, Any] | None
    form: dict[str, Any] | None
    files: dict[str, Any] | None
