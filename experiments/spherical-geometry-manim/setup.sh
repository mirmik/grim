#!/usr/bin/env bash
set -euo pipefail
MANIM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/grim-manim-uv-cache}"
if ! pkg-config --exists pangocairo; then
    python3 "$MANIM_ROOT/bootstrap_native.py"
    export PKG_CONFIG_PATH="$MANIM_ROOT/.native/usr/lib/x86_64-linux-gnu/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
fi
if [ ! -x "$MANIM_ROOT/.venv/bin/python" ]; then
    uv venv --python 3.12 "$MANIM_ROOT/.venv"
fi
uv pip install --python "$MANIM_ROOT/.venv/bin/python" -r "$MANIM_ROOT/requirements.lock.txt"
