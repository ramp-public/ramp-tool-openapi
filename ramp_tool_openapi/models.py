"""Neutral OpenAPI operation models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ParameterLocation = Literal["path", "query", "header", "cookie"]


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
