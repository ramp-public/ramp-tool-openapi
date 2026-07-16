"""Prepare transport-neutral requests from parsed operation fields."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from .models import ParsedOperation, PreparedRequest


def prepare_request(
    operation: ParsedOperation,
    values: Mapping[str, Any],
    *,
    body: Mapping[str, Any] | None = None,
) -> PreparedRequest:
    """Partition caller values according to the operation's canonical fields."""

    path = operation.path
    query: dict[str, Any] = {}
    headers: dict[str, str] = {}
    cookies: dict[str, str] = {}
    json_body: dict[str, Any] = {}
    form: dict[str, Any] = {}
    files: dict[str, Any] = {}

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
        else:
            json_body[field.name] = value

    if body is not None:
        json_body.update(body)

    content_type = (
        operation.request_body.content_type
        if operation.request_body is not None
        else None
    )
    return PreparedRequest(
        method=operation.method.upper(),
        path=path,
        query=query,
        headers=headers,
        cookies=cookies,
        json=json_body if content_type == "application/json" else None,
        form=form if content_type == "multipart/form-data" else None,
        files=files if content_type == "multipart/form-data" else None,
    )
