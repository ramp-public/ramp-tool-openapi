"""Small schema helpers for OpenAPI parser adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def parse_openapi_schemas(spec: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return component schemas in the package's normalized form."""

    components = spec.get("components")
    if not isinstance(components, Mapping):
        return {}
    component_schemas = components.get("schemas")
    if not isinstance(component_schemas, Mapping):
        return {}

    parsed: dict[str, dict[str, Any]] = {}
    for name, schema in component_schemas.items():
        if not isinstance(name, str) or not isinstance(schema, Mapping):
            continue
        parsed[name] = normalize_schema(schema, component_schemas)
    return parsed


def get_openapi_schema(spec: Mapping[str, Any], schema_name: str) -> dict[str, Any]:
    """Return one normalized schema, including a ``+`` composition name."""

    schemas = parse_openapi_schemas(spec)
    names = schema_name.split("+")
    if len(names) == 1:
        try:
            return schemas[schema_name]
        except KeyError as exc:
            raise KeyError(f"Unknown OpenAPI schema component {schema_name!r}") from exc

    merged: dict[str, Any] = {}
    for name in names:
        try:
            merged = _merge_schema(merged, schemas[name])
        except KeyError as exc:
            raise KeyError(f"Unknown OpenAPI schema component {name!r}") from exc
    return merged


def schema_ref_name(schema: Mapping[str, Any] | None) -> str:
    if not schema:
        return ""
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    refs = [
        item["$ref"].rsplit("/", 1)[-1]
        for item in schema.get("allOf", [])
        if isinstance(item, Mapping) and isinstance(item.get("$ref"), str)
    ]
    return "+".join(refs)


def resolve_local_ref(ref: str, spec: Mapping[str, Any]) -> Mapping[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"Only local OpenAPI refs are supported, got {ref!r}")

    value: Any = spec
    for part in ref.removeprefix("#/").split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, Mapping) or key not in value:
            raise KeyError(f"OpenAPI ref {ref!r} could not be resolved")
        value = value[key]
    if not isinstance(value, Mapping):
        raise TypeError(f"OpenAPI ref {ref!r} did not resolve to an object")
    return value


def normalize_schema(
    schema: Mapping[str, Any] | None,
    component_schemas: Mapping[str, Any],
    *,
    max_reference_depth: int = 100,
) -> dict[str, Any]:
    """Resolve local schema references and composition recursively."""

    if max_reference_depth < 1:
        raise ValueError("max_reference_depth must be at least 1")
    if not isinstance(schema, Mapping):
        return {}
    return _normalize_schema(
        schema,
        component_schemas,
        seen_refs=(),
        max_reference_depth=max_reference_depth,
    )


def _normalize_schema(
    schema: Mapping[str, Any],
    component_schemas: Mapping[str, Any],
    *,
    seen_refs: tuple[str, ...],
    max_reference_depth: int,
) -> dict[str, Any]:
    ref = schema.get("$ref")
    if isinstance(ref, str):
        name = _schema_ref_name(ref)
        if name in seen_refs:
            target = component_schemas.get(name)
            schema_type = target.get("type") if isinstance(target, Mapping) else None
            normalized = {}
            if isinstance(schema_type, str):
                normalized["type"] = schema_type
        else:
            if len(seen_refs) >= max_reference_depth:
                raise ValueError(
                    "OpenAPI schema reference depth exceeds "
                    f"the configured maximum of {max_reference_depth}"
                )
            target = component_schemas.get(name)
            if not isinstance(target, Mapping):
                raise KeyError(f"Unknown OpenAPI schema component {name!r}")
            normalized = _normalize_schema(
                target,
                component_schemas,
                seen_refs=(*seen_refs, name),
                max_reference_depth=max_reference_depth,
            )
        siblings = {key: value for key, value in schema.items() if key != "$ref"}
        if siblings:
            normalized = _merge_schema(
                normalized,
                _normalize_schema(
                    siblings,
                    component_schemas,
                    seen_refs=seen_refs,
                    max_reference_depth=max_reference_depth,
                ),
            )
        return normalized

    normalized: dict[str, Any] = {}
    all_of = schema.get("allOf")
    if _is_sequence(all_of):
        for branch in all_of:
            if isinstance(branch, Mapping):
                normalized = _merge_schema(
                    normalized,
                    _normalize_schema(
                        branch,
                        component_schemas,
                        seen_refs=seen_refs,
                        max_reference_depth=max_reference_depth,
                    ),
                )

    direct: dict[str, Any] = {}
    for key, value in schema.items():
        if key in {"$ref", "allOf"}:
            continue
        if key == "properties" and isinstance(value, Mapping):
            direct[key] = {
                name: _normalize_schema(
                    property_schema,
                    component_schemas,
                    seen_refs=seen_refs,
                    max_reference_depth=max_reference_depth,
                )
                for name, property_schema in value.items()
                if isinstance(name, str) and isinstance(property_schema, Mapping)
            }
        elif key in {"items", "additionalProperties", "not"} and isinstance(
            value, Mapping
        ):
            direct[key] = _normalize_schema(
                value,
                component_schemas,
                seen_refs=seen_refs,
                max_reference_depth=max_reference_depth,
            )
        elif key in {"oneOf", "anyOf"} and _is_sequence(value):
            direct[key] = [
                _normalize_schema(
                    branch,
                    component_schemas,
                    seen_refs=seen_refs,
                    max_reference_depth=max_reference_depth,
                )
                for branch in value
                if isinstance(branch, Mapping)
            ]
        else:
            direct[key] = value
    return _merge_schema(normalized, direct)


def _merge_schema(
    base: Mapping[str, Any], overlay: Mapping[str, Any]
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if key == "properties" and isinstance(value, Mapping):
            properties = dict(merged.get("properties", {}))
            properties.update(value)
            merged[key] = properties
        elif key == "required" and _is_sequence(value):
            required = list(merged.get("required", []))
            required.extend(item for item in value if item not in required)
            merged[key] = required
        elif key == "additionalProperties" and (
            merged.get(key) is False or value is False
        ):
            merged[key] = False
        else:
            merged[key] = value
    return merged


def _schema_ref_name(ref: str) -> str:
    prefix = "#/components/schemas/"
    if not ref.startswith(prefix):
        raise ValueError(
            f"Only local OpenAPI component schema refs are supported, got {ref!r}"
        )
    name = ref.removeprefix(prefix)
    if not name or "/" in name:
        raise ValueError(f"Invalid OpenAPI component schema ref {ref!r}")
    return name.replace("~1", "/").replace("~0", "~")


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))
