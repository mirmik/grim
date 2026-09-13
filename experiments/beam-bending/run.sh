#!/usr/bin/env bash
set -euo pipefail
BEAM_VIDEO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
XTTS_PYTHON="${XTTS_PYTHON:-$HOME/project/for-tts-xtts/venv/bin/python}"
VIDEO_PYTHON="${VIDEO_PYTHON:-python3}"
PYTHONDONTWRITEBYTECODE=1 "$XTTS_PYTHON" "$BEAM_VIDEO_ROOT/synthesize.py"
"$VIDEO_PYTHON" "$BEAM_VIDEO_ROOT/render.py"
