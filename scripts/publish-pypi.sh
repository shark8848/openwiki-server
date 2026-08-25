#!/usr/bin/env bash
# publish-pypi.sh — Build and upload openwiki-server (engine) + openwiki-server-sdk to PyPI.
#
# Usage:
#   ./scripts/publish-pypi.sh                          # Full build + upload
#   OPENWIKI_VERSION=0.2.0 ./scripts/publish-pypi.sh   # Specify version
#   OPENWIKI_SDK_VERSION=0.1.1 ./scripts/publish-pypi.sh  # Specify SDK version
#   ./scripts/publish-pypi.sh --test                   # Upload to TestPyPI
#   ./scripts/publish-pypi.sh --skip-build             # Reuse existing dist/
#   ./scripts/publish-pypi.sh --no-skip-existing       # Fail if version exists
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$ROOT_DIR/config/pypi.env"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SKIP_BUILD=false
SKIP_EXISTING=true
REPOSITORY_URL=""

# ---------------------------------------------------------------------------
# Parse CLI flags
# ---------------------------------------------------------------------------
for arg in "$@"; do
    case "$arg" in
        --skip-build)      SKIP_BUILD=true ;;
        --no-skip-existing) SKIP_EXISTING=false ;;
        --test)            REPOSITORY_URL="https://test.pypi.org/legacy/" ;;
        -h|--help)
            echo "Usage: $0 [--skip-build] [--no-skip-existing] [--test]"
            echo ""
            echo "  --skip-build        Reuse existing dist/ artifacts"
            echo "  --no-skip-existing  Fail if version already exists on PyPI"
            echo "  --test              Upload to TestPyPI instead of PyPI"
            echo ""
            echo "Environment variables:"
            echo "  OPENWIKI_VERSION  Override package version (default: pyproject.toml)"
            echo "  OPENWIKI_SDK_VERSION  Override SDK version (default: sdk/python/pyproject.toml)"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Load credentials
# ---------------------------------------------------------------------------
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: $CONFIG_FILE not found."
    echo "Copy the template and fill in your PyPI token:"
    echo "  cp config/pypi.env.example config/pypi.env"
    exit 1
fi

# shellcheck source=/dev/null
source "$CONFIG_FILE"

PYPI_USERNAME="${OPENWIKI_PYPI_USERNAME:-__token__}"
PYPI_TOKEN="${OPENWIKI_PYPI_TOKEN:-}"
if [ -z "$PYPI_TOKEN" ] || [ "$PYPI_TOKEN" = "replace_with_your_pypi_api_token" ]; then
    echo "ERROR: OPENWIKI_PYPI_TOKEN not set in $CONFIG_FILE"
    exit 1
fi

if [ -n "$REPOSITORY_URL" ]; then
    # --test flag overrides
    :
elif [ -n "${OPENWIKI_PYPI_REPOSITORY_URL:-}" ]; then
    REPOSITORY_URL="$OPENWIKI_PYPI_REPOSITORY_URL"
else
    REPOSITORY_URL="https://upload.pypi.org/legacy/"
fi

# ---------------------------------------------------------------------------
# Version override
# ---------------------------------------------------------------------------
CURRENT_VERSION=$(grep -m1 '^version' "$ROOT_DIR/pyproject.toml" | sed 's/.*"\(.*\)".*/\1/')
PACKAGE_VERSION="${OPENWIKI_VERSION:-$CURRENT_VERSION}"

SDK_DIR="$ROOT_DIR/sdk/python"
SDK_PYPROJECT="$SDK_DIR/pyproject.toml"
SDK_VERSION_FILE="$SDK_DIR/openwiki_server_sdk/_version.py"
SDK_CURRENT_VERSION=$(grep -m1 '^version' "$SDK_PYPROJECT" | sed 's/.*"\(.*\)".*/\1/')
SDK_PACKAGE_VERSION="${OPENWIKI_SDK_VERSION:-$SDK_CURRENT_VERSION}"

echo "========================================"
echo " openwiki-server publish"
echo " Version:    $PACKAGE_VERSION"
echo " SDK:        $SDK_PACKAGE_VERSION"
echo " Repository: $REPOSITORY_URL"
echo "========================================"

cd "$ROOT_DIR"

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
if [ "$SKIP_BUILD" = false ]; then
    echo ""
    echo ">>> Cleaning old artifacts..."
    rm -rf dist/ build/ *.egg-info sdk/python/*.egg-info sdk/python/build sdk/python/dist

    # Temporarily override version if OPENWIKI_VERSION is set
    if [ -n "${OPENWIKI_VERSION:-}" ] && [ "$OPENWIKI_VERSION" != "$CURRENT_VERSION" ]; then
        echo ">>> Overriding version: $CURRENT_VERSION → $OPENWIKI_VERSION"
        sed -i "s/^version = \".*\"/version = \"$OPENWIKI_VERSION\"/" pyproject.toml
        RESTORE_VERSION=true
    fi

    # Temporarily override SDK version if OPENWIKI_SDK_VERSION is set
    if [ -n "${OPENWIKI_SDK_VERSION:-}" ] && [ "$OPENWIKI_SDK_VERSION" != "$SDK_CURRENT_VERSION" ]; then
        echo ">>> Overriding SDK version: $SDK_CURRENT_VERSION → $OPENWIKI_SDK_VERSION"
        sed -i "s/^version = \".*\"/version = \"$OPENWIKI_SDK_VERSION\"/" "$SDK_PYPROJECT"
        sed -i "s/__version__ = \".*\"/__version__ = \"$OPENWIKI_SDK_VERSION\"/" "$SDK_VERSION_FILE"
        RESTORE_SDK_VERSION=true
    fi

    echo ">>> Installing build tools..."
    python -m pip install --upgrade build twine --quiet

    echo ">>> Building openwiki-server wheel + sdist..."
    python -m build

    echo ">>> Building openwiki-server-sdk wheel + sdist..."
    (cd "$SDK_DIR" && python -m build --outdir "$ROOT_DIR/dist")

    # Restore original version if we changed it
    if [ "${RESTORE_VERSION:-}" = true ]; then
        sed -i "s/^version = \".*\"/version = \"$CURRENT_VERSION\"/" pyproject.toml
    fi
    if [ "${RESTORE_SDK_VERSION:-}" = true ]; then
        sed -i "s/^version = \".*\"/version = \"$SDK_CURRENT_VERSION\"/" "$SDK_PYPROJECT"
        sed -i "s/__version__ = \".*\"/__version__ = \"$SDK_CURRENT_VERSION\"/" "$SDK_VERSION_FILE"
    fi
else
    echo ""
    echo ">>> Skipping build (--skip-build), using existing dist/"
    if [ ! -d dist ] \
        || [ -z "$(ls -A dist/openwiki_server-*.whl 2>/dev/null)" ] \
        || [ -z "$(ls -A dist/openwiki_server_sdk-*.whl 2>/dev/null)" ]; then
        echo "ERROR: Missing openwiki-server or openwiki-server-sdk .whl in dist/. Run without --skip-build first."
        exit 1
    fi
fi

echo ""
echo ">>> Artifacts:"
ls -lh dist/

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
echo ""
echo ">>> Uploading to $REPOSITORY_URL ..."

TWINE_ARGS=(
    upload
    --username "$PYPI_USERNAME"
    --password "$PYPI_TOKEN"
    --repository-url "$REPOSITORY_URL"
)

if [ "$SKIP_EXISTING" = true ]; then
    TWINE_ARGS+=(--skip-existing)
fi

TWINE_ARGS+=(dist/*)

python -m twine "${TWINE_ARGS[@]}"

echo ""
echo "✅ Published openwiki-server $PACKAGE_VERSION + openwiki-server-sdk $SDK_PACKAGE_VERSION to $REPOSITORY_URL"
