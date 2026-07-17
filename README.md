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
    ParsedField,
    ParsedOperation,
    parse_openapi_operations,
    prepare_request,
)

operations: tuple[ParsedOperation, ...] = parse_openapi_operations(
    spec,
    path_prefix="/developer/v1/agent-tools/",
)

operation: ParsedOperation = operations[0]
fields: tuple[ParsedField, ...] = operation.fields
request = prepare_request(operation, {"card_id": "card-123", "limit": 10})
```

The intended data flow is:

```text
OpenAPI specification
    -> parse_openapi_operations
    -> tuple[ParsedOperation, ...]
    -> canonical fields + prepared HTTP request parts
    -> thin downstream adapter
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
- recursive local schema normalization, including `$ref` and `allOf`
- canonical operation input fields with normalized argument names
- transport-neutral path, query, header, cookie, JSON, and multipart partitioning
- operation-level OAuth scope and `x-*` extension preservation
- raw tag and `x-platforms` metadata preservation
- stable `(method, path)` operation identity

Downstream consumers continue to own product and execution policy, including
translation into consumer-specific models and behavior.

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
- operation-level OAuth scopes declared by OAuth2 security schemes
- raw OpenAPI tags
- operation-level vendor extensions

Schemas remain dependency-free dictionaries, but local component references and
compositions are recursively normalized before consumers receive them. The
normalizer treats `allOf` as an intersection, preserving constraints contributed
by every branch. Required JSON object bodies are represented as `{}` when callers
omit all optional properties. The package does not generate framework-specific
runtime models.

Operation-level `security` overrides document-level security. When an operation
omits `security`, document-level requirements are inherited; an explicit empty
array opts the operation out of those requirements.

## API reference

The intentionally narrow public API is:

```python
from ramp_tool_openapi import (
    get_openapi_schema,
    ParameterLocation,
    ParsedField,
    ParsedOperation,
    ParsedParameter,
    ParsedRequestBody,
    ParsedResponse,
    ParsedSchema,
    parse_openapi_schema,
    parse_openapi_schema_models,
    parse_openapi_operations,
    parse_openapi_schemas,
    prepare_request,
    resolve_local_ref,
    schema_fields,
)
```

`parse_openapi_schemas()` and `get_openapi_schema()` support consumers that
need normalized named schemas without reading `components.schemas` themselves.
`get_openapi_schema()` also resolves the package's `SchemaA+SchemaB` composition
names.

`parse_openapi_schema()` returns a recursive `ParsedSchema` graph that preserves
component names while exposing fully normalized schema dictionaries. Parsed
parameters, fields, request bodies, and responses include this graph as
`parsed_schema` alongside the dictionary-based `schema` representation.
`parse_openapi_schema_models()` returns the same representation for every named
component.

### `parse_openapi_operations`

```python
def parse_openapi_operations(
    spec: Mapping[str, Any],
    *,
    path_prefix: str | None = None,
    max_reference_depth: int = 100,
) -> tuple[ParsedOperation, ...]
```

Normalizes the supported operations in an already-loaded OpenAPI document.

**Arguments**

- `spec`: OpenAPI document represented as a Python mapping.
- `path_prefix`: Optional prefix used to include only matching paths.
- `max_reference_depth`: Maximum component-reference chain depth.

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

Resolves a mapping-only local OpenAPI reference path against an already-decoded
document. Paths must begin with `#/`; reference tokens support JSON Pointer's
`~0` and `~1` escapes. URI-fragment percent-decoding and array traversal are not
supported.

```python
from ramp_tool_openapi import resolve_local_ref

schema = resolve_local_ref(
    "#/components/schemas/CreateCardRequest",
    spec,
)
```

**Arguments**

- `ref`: Mapping-only local reference path beginning with `#/`.
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
| `ParsedOperation` | One normalized HTTP operation | operation metadata plus canonical `fields`, `parameters`, `request_body`, and `response` |
| `ParsedSchema` | One node in the normalized schema graph | normalized `schema`, component `name`, `properties`, `items`, unions, additional-properties behavior, and recursion metadata |
| `ParsedField` | One ready-to-adapt input | wire `name`, consumer `argument_name`, `location`, normalized `schema`, `parsed_schema`, `required`, `description`, default metadata, and whole-body status |
| `ParsedParameter` | One path, query, header, or cookie parameter | `name`, `location`, `required`, `schema`, `parsed_schema`, `description` |
| `ParsedRequestBody` | The selected request media type and schema | `content_type`, `schema`, `parsed_schema`, `schema_name`, `required` |
| `ParsedResponse` | The selected successful response and schema | `status_code`, `content_type`, `schema`, `parsed_schema`, `schema_name` |
| `PreparedRequest` | Transport-neutral request parts | `method`, `path`, `query`, `headers`, `cookies`, `json`, `has_json_body`, `form`, `files` |
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
- remote `$ref` resolution
- consumer-specific model generation or naming
- HTTP request execution

## Development

Run the package tests with:

```bash
uv run --group test python -m pytest -q
```

## Status

The `0.x` API is provisional and may change as downstream integrations migrate
to the shared normalization layer.
