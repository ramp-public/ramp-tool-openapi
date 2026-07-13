#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${1:-/tmp/ramp_tool_openapi_dist}"
BUILD_DIST="$(mktemp -d)"

cleanup() {
    rm -rf "$BUILD_DIST"
}
trap cleanup EXIT

echo "Building ramp-tool-openapi into $DIST_DIR"
UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}" uv build --no-config "$PROJECT_ROOT" \
    --out-dir "$BUILD_DIST"

WHEEL_PATH="$(find "$BUILD_DIST" -name 'ramp_tool_openapi-*.whl' | head -n 1)"
if [ -z "$WHEEL_PATH" ]; then
    echo "Error: no ramp-tool-openapi wheel found"
    exit 1
fi

if ! unzip -Z1 "$WHEEL_PATH" | grep -q '/licenses/LICENSE$'; then
    echo "Error: wheel does not contain the declared MIT license"
    exit 1
fi

"$PROJECT_ROOT/scripts/library_smoke_tests.sh" "$PROJECT_ROOT" "$WHEEL_PATH"

mkdir -p "$DIST_DIR"
cp "$BUILD_DIST"/ramp_tool_openapi-* "$DIST_DIR"/
