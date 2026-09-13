#!/usr/bin/env bash
set -euo pipefail
BEAM_VIDEO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QWEN_PYTHON="${QWEN_PYTHON:-$BEAM_VIDEO_ROOT/../qwen-tts/.venv/bin/python}"
VIDEO_PYTHON="${VIDEO_PYTHON:-python3}"
HF_HUB_OFFLINE=1 "$QWEN_PYTHON" "$BEAM_VIDEO_ROOT/synthesize_qwen.py" --chunking scene
"$VIDEO_PYTHON" "$BEAM_VIDEO_ROOT/verify_speech.py" --output-dir "$BEAM_VIDEO_ROOT/output-qwen-scenes"
"$VIDEO_PYTHON" "$BEAM_VIDEO_ROOT/align_scene_cues.py"
"$VIDEO_PYTHON" "$BEAM_VIDEO_ROOT/render.py" --output-dir "$BEAM_VIDEO_ROOT/output-qwen-scenes" --narrator Qwen3-TTS
"$VIDEO_PYTHON" "$BEAM_VIDEO_ROOT/validate.py" --output-dir "$BEAM_VIDEO_ROOT/output-qwen-scenes"
