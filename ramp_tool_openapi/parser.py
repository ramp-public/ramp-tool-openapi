"""Dependency-free OpenAPI operation parsing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import unquote

from .models import (
    ParsedOperation,
    ParsedParameter,
    ParsedRequestBody,
    ParsedResponse,
    ParsedSecurityRequirement,
    ParsedSecuritySchemeRequirement,
)
from .fields import operation_fields
from .schema import normalize_schema, resolve_local_ref, schema_ref_name

_DEFAULT_REQUEST_CONTENT_TYPES = ("application/json", "multipart/form-data")
_DEFAULT_RESPONSE_CONTENT_TYPES = ("application/json",)
_DEFAULT_MAX_REFERENCE_DEPTH = 100
_HTTP_METHODS = frozenset({"delete", "get", "patch", "post", "put"})
_PARAMETER_LOCATIONS = frozenset({"cookie", "header", "path", "query"})


def _is_http_method(method: str) -> bool:
    return method in _HTTP_METHODS


def _validate_path(path: str, *, field_name: str = "path") -> None:
    if not path.startswith("/"):
        raise ValueError(f"OpenAPI {field_name} must start with '/': {path!r}")
    if any(ord(character) < 32 or ord(character) == 127 for character in path):
        raise ValueError(f"OpenAPI {field_name} contains control characters: {path!r}")
    if "\\" in path:
        raise ValueError(f"OpenAPI {field_name} contains a backslash: {path!r}")
    if unquote(path) != path:
        raise ValueError(
            f"OpenAPI {field_name} must not contain percent-encoding: {path!r}"
        )
    path_parts = path.split("/")
    if "" in path_parts[1:-1]:
        raise ValueError(f"OpenAPI {field_name} contains an empty segment: {path!r}")
    if any(part in {".", ".."} for part in path_parts):
        raise ValueError(f"OpenAPI {field_name} contains a dot segment: {path!r}")


def _path_matches_prefix(path: str, path_prefix: str) -> bool:
    if path_prefix == "/":
        return True
    normalized_prefix = path_prefix.rstrip("/")
    return path == normalized_prefix or path.startswith(f"{normalized_prefix}/")


def _operation_tags(operation: Mapping[str, Any]) -> tuple[str, ...]:
    tags = operation.get("tags")
    if not isinstance(tags, Sequence) or isinstance(tags, (str, bytes)):
        return ()
    return tuple(tag for tag in tags if isinstance(tag, str))


def _operation_platforms(operation: Mapping[str, Any]) -> tuple[str, ...]:
    platforms = operation.get("x-platforms")
    if isinstance(platforms, str):
        return (platforms,)
    if isinstance(platforms, Sequence) and not isinstance(platforms, (str, bytes)):
        return tuple(item for item in platforms if isinstance(item, str))
    return ()


def _extract_security_requirements(
    operation: Mapping[str, Any],
    spec: Mapping[str, Any],
) -> tuple[ParsedSecurityRequirement, ...]:
    security_source = operation if "security" in operation else spec
    if "security" not in security_source:
        return ()
    security = security_source["security"]
    if not isinstance(security, Sequence) or isinstance(security, (str, bytes)):
        raise ValueError("OpenAPI security requirements must be an array")

    parsed_requirements: list[ParsedSecurityRequirement] = []
    for requirement in security:
        if not isinstance(requirement, Mapping):
            raise ValueError("Each OpenAPI security requirement must be an object")
        schemes: list[ParsedSecuritySchemeRequirement] = []
        for scheme_name, raw_scopes in requirement.items():
            if not isinstance(scheme_name, str) or not scheme_name:
                raise ValueError(
                    "OpenAPI security scheme names must be non-empty strings"
                )
            if not isinstance(raw_scopes, Sequence) or isinstance(
                raw_scopes, (str, bytes)
            ):
                raise ValueError(
                    f"OpenAPI security scopes for {scheme_name!r} must be an array"
                )
            if not all(isinstance(scope, str) for scope in raw_scopes):
                raise ValueError(
                    f"OpenAPI security scopes for {scheme_name!r} must be strings"
                )
            schemes.append(
                ParsedSecuritySchemeRequirement(
                    scheme_name=scheme_name,
                    scopes=tuple(raw_scopes),
                )
            )
        parsed_requirements.append(ParsedSecurityRequirement(schemes=tuple(schemes)))
    return tuple(parsed_requirements)


def _oauth_scheme_names(
    spec: Mapping[str, Any],
    *,
    max_reference_depth: int,
) -> frozenset[str]:
    components = spec.get("components")
    if not isinstance(components, Mapping):
        return frozenset({"oauth2"})
    security_schemes = components.get("securitySchemes")
    if not isinstance(security_schemes, Mapping):
        return frozenset({"oauth2"})
    oauth_scheme_names: set[str] = set()
    for name, scheme in security_schemes.items():
        if not isinstance(name, str) or not isinstance(scheme, Mapping):
            continue
        resolved_scheme = _resolve_reference_object(
            scheme,
            spec,
            max_reference_depth=max_reference_depth,
        )
        if resolved_scheme.get("type") == "oauth2":
            oauth_scheme_names.add(name)
    return frozenset(oauth_scheme_names)


def _extract_oauth_scopes(
    security_requirements: tuple[ParsedSecurityRequirement, ...],
    oauth_scheme_names: frozenset[str],
) -> tuple[str, ...]:
    scopes: dict[str, None] = {}
    for requirement in security_requirements:
        for scheme in requirement.schemes:
            if scheme.scheme_name in oauth_scheme_names:
                for scope in scheme.scopes:
                    scopes[scope] = None
    return tuple(scopes)


def _operation_alias(operation: Mapping[str, Any]) -> str | None:
    alias = operation.get("x-alias")
    return alias if isinstance(alias, str) and alias else None


def _operation_extensions(operation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in operation.items()
        if isinstance(key, str) and key.startswith("x-")
    }


def _combine_parameters(
    path_parameters: Any,
    operation_parameters: Any,
    *,
    spec: Mapping[str, Any] | None = None,
    max_reference_depth: int = _DEFAULT_MAX_REFERENCE_DEPTH,
) -> tuple[Mapping[str, Any], ...]:
    by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for raw_parameter in _iter_parameter_mappings(
        path_parameters,
        spec=spec,
        max_reference_depth=max_reference_depth,
    ):
        key = _parameter_key(raw_parameter)
        if key is not None:
            by_key[key] = raw_parameter
    for raw_parameter in _iter_parameter_mappings(
        operation_parameters,
        spec=spec,
        max_reference_depth=max_reference_depth,
    ):
        key = _parameter_key(raw_parameter)
        if key is not None:
            by_key[key] = raw_parameter
    return tuple(by_key.values())


def _extract_parameters(
    raw_parameters: Any,
    *,
    spec: Mapping[str, Any] | None = None,
    component_schemas: Mapping[str, Any] | None = None,
    max_reference_depth: int = _DEFAULT_MAX_REFERENCE_DEPTH,
) -> tuple[ParsedParameter, ...]:
    parameters: list[ParsedParameter] = []
    for raw_parameter in _iter_parameter_mappings(
        raw_parameters,
        spec=spec,
        max_reference_depth=max_reference_depth,
    ):
        name = raw_parameter.get("name")
        location = raw_parameter.get("in")
        if not isinstance(name, str) or location not in _PARAMETER_LOCATIONS:
            continue
        raw_schema = raw_parameter.get("schema")
        schema = normalize_schema(
            raw_schema if isinstance(raw_schema, Mapping) else {},
            component_schemas or {},
            max_reference_depth=max_reference_depth,
        )
        description = raw_parameter.get("description")
        parameters.append(
            ParsedParameter(
                name=name,
                location=location,
                required=bool(raw_parameter.get("required")),
                schema=schema,
                description=description if isinstance(description, str) else None,
            )
        )
    return tuple(parameters)


def _extract_request_body(
    operation: Mapping[str, Any],
    *,
    spec: Mapping[str, Any] | None = None,
    component_schemas: Mapping[str, Any] | None = None,
    content_types: tuple[str, ...] = _DEFAULT_REQUEST_CONTENT_TYPES,
    max_reference_depth: int = _DEFAULT_MAX_REFERENCE_DEPTH,
) -> ParsedRequestBody | None:
    request_body = operation.get("requestBody")
    if not isinstance(request_body, Mapping):
        return None
    request_body = _resolve_reference_object(
        request_body,
        spec,
        max_reference_depth=max_reference_depth,
    )
    content = request_body.get("content")
    if not isinstance(content, Mapping):
        return None
    for content_type in content_types:
        media_type = content.get(content_type)
        if not isinstance(media_type, Mapping):
            continue
        schema = media_type.get("schema")
        if isinstance(schema, Mapping):
            return ParsedRequestBody(
                content_type=content_type,
                schema=normalize_schema(
                    schema,
                    component_schemas or {},
                    max_reference_depth=max_reference_depth,
                ),
                schema_name=schema_ref_name(schema),
                required=bool(request_body.get("required")),
            )
    return None


def _extract_response(
    operation: Mapping[str, Any],
    *,
    spec: Mapping[str, Any] | None = None,
    component_schemas: Mapping[str, Any] | None = None,
    content_types: tuple[str, ...] = _DEFAULT_RESPONSE_CONTENT_TYPES,
    max_reference_depth: int = _DEFAULT_MAX_REFERENCE_DEPTH,
) -> ParsedResponse | None:
    responses = operation.get("responses")
    if not isinstance(responses, Mapping):
        return None
    for status_code in sorted(responses, key=str):
        if not str(status_code).startswith("2"):
            continue
        response = responses[status_code]
        if not isinstance(response, Mapping):
            continue
        response = _resolve_reference_object(
            response,
            spec,
            max_reference_depth=max_reference_depth,
        )
        content = response.get("content")
        if not isinstance(content, Mapping):
            continue
        for content_type in content_types:
            media_type = content.get(content_type)
            if not isinstance(media_type, Mapping):
                continue
            schema = media_type.get("schema")
            if isinstance(schema, Mapping):
                return ParsedResponse(
                    status_code=str(status_code),
                    content_type=content_type,
                    schema=normalize_schema(
                        schema,
                        component_schemas or {},
                        max_reference_depth=max_reference_depth,
                    ),
                    schema_name=schema_ref_name(schema),
                )
    return None


def parse_openapi_operations(
    spec: Mapping[str, Any],
    *,
    path_prefix: str | None = None,
    max_reference_depth: int = _DEFAULT_MAX_REFERENCE_DEPTH,
) -> tuple[ParsedOperation, ...]:
    if max_reference_depth < 1:
        raise ValueError("max_reference_depth must be at least 1")
    if path_prefix is not None:
        _validate_path(path_prefix, field_name="path prefix")

    operations: list[ParsedOperation] = []
    operation_keys: set[str] = set()
    paths = spec.get("paths")
    if not isinstance(paths, Mapping):
        return ()
    oauth_scheme_names = _oauth_scheme_names(
        spec,
        max_reference_depth=max_reference_depth,
    )
    component_schemas = _component_schemas(spec)

    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, Mapping):
            continue
        _validate_path(path)
        if path_prefix is not None and not _path_matches_prefix(path, path_prefix):
            continue
        path_parameters = path_item.get("parameters", ())
        for method, operation in path_item.items():
            if not isinstance(method, str):
                continue
            if method.lower() in _HTTP_METHODS and not _is_http_method(method):
                raise ValueError(
                    f"OpenAPI HTTP method keys must be lowercase: {method!r}"
                )
            if not _is_http_method(method):
                continue
            if not isinstance(operation, Mapping):
                continue
            normalized_method = method
            operation_key = _operation_key(normalized_method, path)
            if operation_key in operation_keys:
                raise ValueError(f"Duplicate OpenAPI operation key: {operation_key!r}")
            operation_keys.add(operation_key)
            parameters = _combine_parameters(
                path_parameters,
                operation.get("parameters", ()),
                spec=spec,
                max_reference_depth=max_reference_depth,
            )
            security_requirements = _extract_security_requirements(operation, spec)
            parsed_parameters = _extract_parameters(
                parameters,
                component_schemas=component_schemas,
                max_reference_depth=max_reference_depth,
            )
            request_body = _extract_request_body(
                operation,
                spec=spec,
                component_schemas=component_schemas,
                max_reference_depth=max_reference_depth,
            )
            operations.append(
                ParsedOperation(
                    operation_key=operation_key,
                    path=path,
                    method=normalized_method,
                    operation_id=_string_or_none(operation.get("operationId")),
                    summary=_string_or_none(operation.get("summary")),
                    description=_string_or_none(operation.get("description")),
                    tags=_operation_tags(operation),
                    platforms=_operation_platforms(operation),
                    alias=_operation_alias(operation),
                    security_requirements=security_requirements,
                    scopes=_extract_oauth_scopes(
                        security_requirements,
                        oauth_scheme_names,
                    ),
                    extensions=_operation_extensions(operation),
                    parameters=parsed_parameters,
                    request_body=request_body,
                    response=_extract_response(
                        operation,
                        spec=spec,
                        component_schemas=component_schemas,
                        max_reference_depth=max_reference_depth,
                    ),
                    raw_operation=dict(operation),
                    fields=operation_fields(parsed_parameters, request_body),
                    platforms_declared="x-platforms" in operation,
                )
            )
    return tuple(operations)


def _operation_key(method: str, path: str) -> str:
    return f"{method.lower()} {path}"


def _component_schemas(spec: Mapping[str, Any]) -> Mapping[str, Any]:
    components = spec.get("components")
    if not isinstance(components, Mapping):
        return {}
    schemas = components.get("schemas")
    return schemas if isinstance(schemas, Mapping) else {}


def _iter_parameter_mappings(
    raw_parameters: Any,
    *,
    spec: Mapping[str, Any] | None = None,
    max_reference_depth: int = _DEFAULT_MAX_REFERENCE_DEPTH,
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(raw_parameters, Sequence) or isinstance(
        raw_parameters, (str, bytes)
    ):
        return ()
    return tuple(
        _resolve_reference_object(
            item,
            spec,
            max_reference_depth=max_reference_depth,
        )
        for item in raw_parameters
        if isinstance(item, Mapping)
    )


def _resolve_reference_object(
    raw_object: Mapping[str, Any],
    spec: Mapping[str, Any] | None,
    *,
    max_reference_depth: int = _DEFAULT_MAX_REFERENCE_DEPTH,
) -> Mapping[str, Any]:
    if max_reference_depth < 1:
        raise ValueError("max_reference_depth must be at least 1")

    current = raw_object
    seen_refs: set[str] = set()
    while True:
        ref = current.get("$ref")
        if not isinstance(ref, str):
            return current
        if spec is None:
            raise ValueError(f"OpenAPI ref {ref!r} cannot be resolved without a spec")
        if ref in seen_refs:
            raise ValueError(f"OpenAPI ref cycle detected for {ref!r}")
        if len(seen_refs) >= max_reference_depth:
            raise ValueError(
                "OpenAPI reference depth exceeds "
                f"the configured maximum of {max_reference_depth}"
            )
        seen_refs.add(ref)
        current = resolve_local_ref(ref, spec)


def _parameter_key(parameter: Mapping[str, Any]) -> tuple[str, str] | None:
    name = parameter.get("name")
    location = parameter.get("in")
    if isinstance(name, str) and isinstance(location, str):
        return (location, name)
    return None


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None
