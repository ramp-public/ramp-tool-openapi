"""Small schema helpers for OpenAPI parser adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


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
