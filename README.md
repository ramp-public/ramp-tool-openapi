# ramp-tool-openapi

Shared, dependency-free OpenAPI normalization for Ramp tool surfaces.

## Installation

```bash
pip install ramp-tool-openapi
```

The current package requires Python 3.11 or newer.

## What is this?

`ramp-tool-openapi` is the shared normalization boundary between Ramp OpenAPI
specifications and downstream tool adapters. It accepts an already-loaded OpenAPI
document and returns neutral `ParsedOperation` objects that consumers translate
into their own representations.

This gives Ramp tool consumers:

- one implementation of shared OpenAPI parsing rules
- consistent local `$ref`, parameter, request, response, operation-level OAuth
  scope, and extension handling
- stable operation identity for paths that support multiple HTTP methods
- a dependency-free intermediate representation
- freedom to keep product-specific behavior in each downstream adapter

## Core concepts

### Neutral parsed operations

The main entry point returns the package's typed intermediate representation:

```python
from ramp_tool_openapi import (
    ParsedOperation,
    ParsedParameter,
    ParsedRequestBody,
    ParsedResponse,
    parse_openapi_operations,
)

operations: tuple[ParsedOperation, ...] = parse_openapi_operations(
    spec,
    path_prefix="/developer/v1/agent-tools/",
)

operation: ParsedOperation = operations[0]
parameters: tuple[ParsedParameter, ...] = operation.parameters
request_body: ParsedRequestBody | None = operation.request_body
response: ParsedResponse | None = operation.response
```

The intended data flow is:

```text
OpenAPI specification
    -> parse_openapi_operations
    -> tuple[ParsedOperation, ...]
    -> downstream CLI or MCP adapter
    -> consumer-specific tool model
```

### Stable operation identity

`ParsedOperation.operation_key` combines the normalized HTTP method and path:

```text
get /developer/v1/agent-tools/procurement-draft
post /developer/v1/agent-tools/procurement-draft
delete /developer/v1/agent-tools/procurement-draft
```

This prevents operations on the same path from overwriting one another.

### Shared normalization, adapter-owned policy

This package owns OpenAPI facts that must remain consistent across consumers:

- operation enumeration and optional path-prefix filtering
- local reference resolution
- path-level and operation-level parameter merging
- request and response media schema extraction
- operation-level OAuth scope and `x-*` extension preservation
- raw tag and `x-platforms` metadata preservation
- stable `(method, path)` operation identity

Downstream consumers continue to own product and execution policy.

`ramp-cli` owns:

- Click parameter classification
- synthetic commands and registry behavior
- CLI-visible names and aliases
- final category and tag selection
- CLI platform visibility defaults

`ramp-mcp-remote` owns:

- Pydantic model generation
- FastAPI route registration
- MCP-visible names
- path rendering and request execution
- MCP platform visibility defaults

If both consumers need to derive the same fact from `raw_operation`, that fact
should generally become a typed field on `ParsedOperation` instead. This keeps
shared parsing logic from drifting back into the adapters.

## Supported OpenAPI behavior

The parser currently supports:

- `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` operations
- path, query, header, and cookie parameters
- path-level parameter inheritance
- operation-level parameter overrides matched by `(location, name)`
- local component references for parameters, request bodies, and responses
- JSON and multipart request schemas, preferring `application/json`
- the first successful response, in sorted status-code order, with an
  `application/json` schema
- operation-level OAuth scopes declared under each operation's
  `security[*].oauth2`
- raw OpenAPI tags
- string and list forms of `x-platforms`
- `x-alias` and arbitrary operation-level `x-*` extensions

Schemas are preserved as dictionaries. The package does not recursively
dereference schemas or generate Python models from them.

Top-level OpenAPI `security` requirements are not inherited. Consumers that rely
on document-level OAuth requirements must handle that policy before adapting the
parsed operations.

## API reference

The intentionally narrow public API is:

```python
from ramp_tool_openapi import (
    ParameterLocation,
    ParsedOperation,
    ParsedParameter,
    ParsedRequestBody,
    ParsedResponse,
    parse_openapi_operations,
    resolve_local_ref,
)
```

### `parse_openapi_operations`

```python
def parse_openapi_operations(
    spec: Mapping[str, Any],
    *,
    path_prefix: str | None = None,
) -> tuple[ParsedOperation, ...]
```

Normalizes the supported operations in an already-loaded OpenAPI document.

**Arguments**

- `spec`: OpenAPI document represented as a Python mapping.
- `path_prefix`: Optional prefix used to include only matching paths.

**Returns**

A tuple of `ParsedOperation` objects in document order. An empty tuple is
returned when the document does not contain a valid `paths` mapping or no paths
match `path_prefix`.

**Raises**

- `ValueError` when a parameter, request-body, or response reference is remote or cyclic.
- `KeyError` when a local reference cannot be resolved.
- `TypeError` when a reference does not resolve to an OpenAPI object.

### `resolve_local_ref`

```python
def resolve_local_ref(
    ref: str,
    spec: Mapping[str, Any],
) -> Mapping[str, Any]
```

Resolves a local OpenAPI JSON Pointer against an OpenAPI document:

```python
from ramp_tool_openapi import resolve_local_ref

schema = resolve_local_ref(
    "#/components/schemas/CreateCardRequest",
    spec,
)
```

**Arguments**

- `ref`: Local reference beginning with `#/`.
- `spec`: OpenAPI document containing the referenced object.

**Returns**

The referenced OpenAPI object as a mapping.

**Raises**

- `ValueError` when `ref` is not local.
- `KeyError` when `ref` cannot be resolved.
- `TypeError` when `ref` does not resolve to an OpenAPI object.

Remote references are not supported.

### Returned models

The parser returns frozen dataclass models. Their schema and extension values
remain dictionaries so downstream adapters can consume the original OpenAPI
data without taking a dependency on another schema library.

| Model | Purpose | Fields |
| --- | --- | --- |
| `ParsedOperation` | One normalized HTTP operation | `operation_key`, `path`, `method`, `operation_id`, `summary`, `description`, `tags`, `platforms`, `alias`, `scopes`, `extensions`, `parameters`, `request_body`, `response`, `raw_operation` |
| `ParsedParameter` | One path, query, header, or cookie parameter | `name`, `location`, `required`, `schema`, `description` |
| `ParsedRequestBody` | The selected request media type and schema | `content_type`, `schema`, `schema_name`, `required` |
| `ParsedResponse` | The selected successful response and schema | `status_code`, `content_type`, `schema`, `schema_name` |
| `ParameterLocation` | Supported parameter location type | `"path"`, `"query"`, `"header"`, or `"cookie"` |

Internal parser helpers, including underscore-prefixed functions, are
implementation details and should not be imported by downstream consumers.

## Security model

This library accepts an already-decoded OpenAPI mapping. It does not parse YAML,
read files, fetch remote references, execute requests, or enforce authorization.
Only local references beginning with `#/` are supported.

`ParsedOperation.security_requirements` preserves OpenAPI's boolean structure: the
outer tuple contains alternatives, while every scheme inside one alternative must
be satisfied. `ParsedOperation.scopes` is a convenience union of scopes from OAuth2
schemes and must not be used as an authorization decision.

Operation paths must be absolute and canonical. Percent-encoded paths, backslashes,
control characters, and `.` or `..` path segments are rejected. `path_prefix`
selects operations but is not a replacement for authorization in a caller.

Reference-object traversal is bounded by `max_reference_depth`, which defaults to
100. Applications accepting untrusted documents should also enforce an input-size
limit before decoding JSON.

## Non-goals

This package is not a general-purpose OpenAPI framework. It does not own:

- OpenAPI document loading or full-spec validation
- remote `$ref` resolution or recursive schema dereferencing
- CLI command or Pydantic model generation
- CLI- or MCP-visible naming
- platform visibility defaults
- category or tag selection
- route or command registration
- request serialization or execution

## Development

Run the package tests with:

```bash
uv run --project pkgs/ramp_tool_openapi --group test pytest -q
```

## Status

The initial `0.x` API is provisional until both `ramp-cli` and
`ramp-mcp-remote` have migrated to the shared normalization layer. Add links to
both consumer migration PRs here before treating the API as stable.
