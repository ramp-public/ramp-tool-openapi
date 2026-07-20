"""Small schema helpers for OpenAPI parser adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeGuard

from .models import ParsedSchema


@dataclass(slots=True)
class _NormalizedSchema:
    schema: dict[str, Any]
    identities: set[str] = field(default_factory=set)
    recursive_identities: set[str] = field(default_factory=set)
    children: dict[tuple[str | int, ...], _NormalizedSchema] = field(
        default_factory=dict
    )


def parse_openapi_schema(
    schema: Mapping[str, Any] | None,
    component_schemas: Mapping[str, Any],
    *,
    name: str | None = None,
    max_reference_depth: int = 100,
) -> ParsedSchema:
    """Build a normalized schema graph while preserving component identities."""

    if max_reference_depth < 1:
        raise ValueError("max_reference_depth must be at least 1")
    if not isinstance(schema, Mapping):
        return ParsedSchema(schema={}, name=name)

    schema_body = _named_schema_body(schema, component_schemas, name)
    normalized = _normalize_schema(
        schema_body,
        component_schemas,
        seen_refs=(name,) if name is not None and name in component_schemas else (),
        reference_depth=0,
        max_reference_depth=max_reference_depth,
    )
    root_name = name or schema_ref_name(schema) or None
    if root_name is not None:
        normalized.identities = {root_name}
    return _parsed_schema_from_normalized(normalized)


def _named_schema_body(
    schema: Mapping[str, Any],
    component_schemas: Mapping[str, Any],
    name: str | None,
) -> Mapping[str, Any]:
    """Unwrap a matching named root ref before activating its recursion guard."""

    ref = schema.get("$ref")
    if not isinstance(ref, str) or name is None or _schema_ref_name(ref) != name:
        return schema

    target = component_schemas.get(name)
    if not isinstance(target, Mapping):
        raise KeyError(f"Unknown OpenAPI schema component {name!r}")
    siblings = {key: value for key, value in schema.items() if key != "$ref"}
    return {"allOf": [target, siblings]} if siblings else target


def parse_openapi_schema_models(
    spec: Mapping[str, Any],
    *,
    max_reference_depth: int = 100,
) -> dict[str, ParsedSchema]:
    """Return every named component as a normalized ``ParsedSchema`` graph."""

    components = spec.get("components")
    if not isinstance(components, Mapping):
        return {}
    component_schemas = components.get("schemas")
    if not isinstance(component_schemas, Mapping):
        return {}
    return {
        name: parse_openapi_schema(
            schema,
            component_schemas,
            name=name,
            max_reference_depth=max_reference_depth,
        )
        for name, schema in component_schemas.items()
        if isinstance(name, str) and isinstance(schema, Mapping)
    }


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
        return _schema_ref_name(ref)
    refs = [
        _schema_ref_name(item["$ref"])
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
        reference_depth=0,
        max_reference_depth=max_reference_depth,
    ).schema


def _parsed_schema_from_normalized(
    normalized: _NormalizedSchema,
) -> ParsedSchema:
    schema = normalized.schema
    properties_value = schema.get("properties")
    properties = (
        {
            name: _parsed_schema_from_normalized(
                normalized.children[("properties", name)],
            )
            for name, property_schema in properties_value.items()
            if isinstance(name, str)
            and isinstance(property_schema, dict)
            and ("properties", name) in normalized.children
        }
        if isinstance(properties_value, Mapping)
        else None
    )

    def child(key: str) -> ParsedSchema | None:
        normalized_child = normalized.children.get((key,))
        if normalized_child is None:
            return None
        return _parsed_schema_from_normalized(normalized_child)

    def branches(key: str) -> tuple[ParsedSchema, ...]:
        value = schema.get(key)
        if not isinstance(value, list):
            return ()
        return tuple(
            _parsed_schema_from_normalized(
                normalized.children[(key, index)],
            )
            for index, branch in enumerate(value)
            if isinstance(branch, dict) and (key, index) in normalized.children
        )

    additional_value = schema.get("additionalProperties")
    additional_properties: bool | ParsedSchema | None
    if isinstance(additional_value, bool):
        additional_properties = additional_value
    else:
        additional_properties = child("additionalProperties")

    identity_candidates = normalized.identities
    identity = (
        next(iter(identity_candidates)) if len(identity_candidates) == 1 else None
    )
    return ParsedSchema(
        schema=schema,
        name=identity,
        properties=properties,
        items=child("items"),
        one_of=branches("oneOf"),
        any_of=branches("anyOf"),
        additional_properties=additional_properties,
        recursive=(
            identity is not None and identity in normalized.recursive_identities
        ),
    )


def _normalize_schema(
    schema: Mapping[str, Any],
    component_schemas: Mapping[str, Any],
    *,
    seen_refs: tuple[str, ...],
    reference_depth: int,
    max_reference_depth: int,
) -> _NormalizedSchema:
    ref = schema.get("$ref")
    if isinstance(ref, str):
        name = _schema_ref_name(ref)
        if name in seen_refs:
            target = component_schemas.get(name)
            schema_type = target.get("type") if isinstance(target, Mapping) else None
            normalized_schema: dict[str, Any] = {}
            if isinstance(schema_type, str):
                normalized_schema["type"] = schema_type
            normalized = _NormalizedSchema(
                schema=normalized_schema,
                identities={name},
                recursive_identities={name},
            )
        else:
            if reference_depth >= max_reference_depth:
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
                reference_depth=reference_depth + 1,
                max_reference_depth=max_reference_depth,
            )
        siblings = {key: value for key, value in schema.items() if key != "$ref"}
        if siblings:
            normalized = _merge_normalized_schema(
                normalized,
                _normalize_schema(
                    siblings,
                    component_schemas,
                    seen_refs=seen_refs,
                    reference_depth=reference_depth,
                    max_reference_depth=max_reference_depth,
                ),
            )
        normalized.identities = {name}
        return normalized

    composed = _NormalizedSchema(schema={})
    all_of = schema.get("allOf")
    if _is_sequence(all_of):
        for branch in all_of:
            if isinstance(branch, Mapping):
                composed = _merge_normalized_schema(
                    composed,
                    _normalize_schema(
                        branch,
                        component_schemas,
                        seen_refs=seen_refs,
                        reference_depth=reference_depth,
                        max_reference_depth=max_reference_depth,
                    ),
                )
        composed_name = schema_ref_name(schema)
        if composed_name:
            composed.identities = {composed_name}

    direct_schema: dict[str, Any] = {}
    direct_children: dict[tuple[str | int, ...], _NormalizedSchema] = {}
    for key, value in schema.items():
        if key in {"$ref", "allOf"}:
            continue
        if key == "properties" and isinstance(value, Mapping):
            normalized_properties: dict[str, Any] = {}
            for name, property_schema in value.items():
                if not isinstance(name, str) or not isinstance(
                    property_schema, Mapping
                ):
                    continue
                normalized_property = _normalize_schema(
                    property_schema,
                    component_schemas,
                    seen_refs=seen_refs,
                    reference_depth=reference_depth,
                    max_reference_depth=max_reference_depth,
                )
                normalized_properties[name] = normalized_property.schema
                direct_children[("properties", name)] = normalized_property
            direct_schema[key] = normalized_properties
        elif key in {"items", "additionalProperties", "not"} and isinstance(
            value, Mapping
        ):
            normalized_child = _normalize_schema(
                value,
                component_schemas,
                seen_refs=seen_refs,
                reference_depth=reference_depth,
                max_reference_depth=max_reference_depth,
            )
            direct_schema[key] = normalized_child.schema
            direct_children[(key,)] = normalized_child
        elif key in {"oneOf", "anyOf"} and _is_sequence(value):
            normalized_branches: list[dict[str, Any]] = []
            for branch in value:
                if not isinstance(branch, Mapping):
                    continue
                normalized_branch = _normalize_schema(
                    branch,
                    component_schemas,
                    seen_refs=seen_refs,
                    reference_depth=reference_depth,
                    max_reference_depth=max_reference_depth,
                )
                index = len(normalized_branches)
                normalized_branches.append(normalized_branch.schema)
                direct_children[(key, index)] = normalized_branch
            direct_schema[key] = normalized_branches
        else:
            direct_schema[key] = value
    direct = _NormalizedSchema(schema=direct_schema, children=direct_children)
    return _merge_normalized_schema(composed, direct)


def _merge_normalized_schema(
    base: _NormalizedSchema, overlay: _NormalizedSchema
) -> _NormalizedSchema:
    """Merge schema values and their parsed metadata with identical semantics."""

    merged_schema = _merge_schema(base.schema, overlay.schema)
    children = dict(base.children)

    overlay_properties = overlay.schema.get("properties")
    if "properties" in overlay.schema and not isinstance(overlay_properties, Mapping):
        children = {
            path: child for path, child in children.items() if path[0] != "properties"
        }
    elif isinstance(overlay_properties, Mapping):
        for property_name in overlay_properties:
            path = ("properties", property_name)
            overlay_child = overlay.children.get(path)
            if overlay_child is None:
                children.pop(path, None)
                continue
            base_child = base.children.get(path)
            if base_child is not None:
                children[path] = _merge_normalized_schema(base_child, overlay_child)
            else:
                children[path] = overlay_child

    for key in ("items", "oneOf", "anyOf", "not"):
        if key not in overlay.schema:
            continue
        children = {path: child for path, child in children.items() if path[0] != key}
        children.update(
            {path: child for path, child in overlay.children.items() if path[0] == key}
        )

    if "additionalProperties" in overlay.schema:
        key = "additionalProperties"
        children = {path: child for path, child in children.items() if path[0] != key}
        if merged_schema.get(key) is not False:
            overlay_child = overlay.children.get((key,))
            if overlay_child is not None:
                children[(key,)] = overlay_child

    return _NormalizedSchema(
        schema=merged_schema,
        identities=base.identities | overlay.identities,
        recursive_identities=(base.recursive_identities | overlay.recursive_identities),
        children=children,
    )


def _merge_schema(
    base: Mapping[str, Any], overlay: Mapping[str, Any]
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if key == "properties" and isinstance(value, Mapping):
            properties = dict(merged.get("properties", {}))
            for property_name, property_schema in value.items():
                existing_schema = properties.get(property_name)
                if isinstance(existing_schema, Mapping) and isinstance(
                    property_schema, Mapping
                ):
                    properties[property_name] = _merge_schema(
                        existing_schema, property_schema
                    )
                else:
                    properties[property_name] = property_schema
            merged[key] = properties
        elif key == "required" and _is_sequence(value):
            required = list(merged.get("required", []))
            required.extend(item for item in value if item not in required)
            merged[key] = required
        elif key == "enum" and _is_sequence(merged.get(key)) and _is_sequence(value):
            merged[key] = [item for item in merged[key] if item in value]
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


def _is_sequence(value: Any) -> TypeGuard[Sequence[Any]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))
