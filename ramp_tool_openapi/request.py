"""Prepare transport-neutral requests from parsed operation fields."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from .models import ParsedOperation, PreparedRequest

_BODY_UNSET = object()


def prepare_request(
    operation: ParsedOperation,
    values: Mapping[str, Any],
    *,
    body: Any = _BODY_UNSET,
) -> PreparedRequest:
    """Partition caller values according to the operation's canonical fields."""

    path = operation.path
    query: dict[str, Any] = {}
    headers: dict[str, str] = {}
    cookies: dict[str, str] = {}
    json_body: dict[str, Any] = {}
    form: dict[str, Any] = {}
    files: dict[str, Any] = {}
    body_root_set = False
    json_body_set = False

    for field in operation.fields:
        if field.argument_name not in values:
            continue
        value = values[field.argument_name]
        if field.location == "path":
            path = path.replace(f"{{{field.name}}}", quote(str(value), safe=""))
        elif field.location == "query":
            query[field.name] = value
        elif field.location == "header":
            headers[field.name] = str(value)
        elif field.location == "cookie":
            cookies[field.name] = str(value)
        elif field.location == "form":
            target = files if field.schema.get("format") == "binary" else form
            target[field.name] = value
        elif field.is_body_root:
            json_body = value
            body_root_set = True
            json_body_set = True
        else:
            json_body[field.name] = value
            json_body_set = True

    if body is not _BODY_UNSET:
        if body_root_set:
            raise ValueError("body cannot be supplied with the whole-body field")
        if isinstance(body, Mapping):
            json_body.update(body)
        else:
            json_body = body
        json_body_set = True

    content_type = (
        operation.request_body.content_type
        if operation.request_body is not None
        else None
    )
    if (
        not json_body_set
        and operation.request_body is not None
        and operation.request_body.required
        and content_type == "application/json"
        and (
            operation.request_body.schema.get("type") == "object"
            or isinstance(operation.request_body.schema.get("properties"), Mapping)
        )
    ):
        json_body_set = True
    return PreparedRequest(
        method=operation.method.upper(),
        path=path,
        query=query,
        headers=headers,
        cookies=cookies,
        json=(
            json_body if content_type == "application/json" and json_body_set else None
        ),
        has_json_body=content_type == "application/json" and json_body_set,
        form=form if content_type == "multipart/form-data" else None,
        files=files if content_type == "multipart/form-data" else None,
    )
