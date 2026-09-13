#!/usr/bin/env bash
set -euo pipefail
CHAPTER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHAPTER_PYTHON="$CHAPTER_ROOT/../spherical-geometry-manim/.venv/bin/python"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$CHAPTER_ROOT/../voxcpm2/.venv/bin/python" "$CHAPTER_ROOT/synthesize.py"
python3 "$CHAPTER_ROOT/prepare_audio.py"
python3 "$CHAPTER_ROOT/../beam-bending/verify_speech.py" --output-dir "$CHAPTER_ROOT/output-voxcpm-scenes"
python3 "$CHAPTER_ROOT/../beam-bending/align_scene_cues.py" --output-dir "$CHAPTER_ROOT/output-voxcpm-scenes"
python3 "$CHAPTER_ROOT/export_audio.py"
"$CHAPTER_PYTHON" "$CHAPTER_ROOT/render.py" --stills
"$CHAPTER_PYTHON" "$CHAPTER_ROOT/build_all.py"
"$CHAPTER_PYTHON" "$CHAPTER_ROOT/assemble.py"
python3 "$CHAPTER_ROOT/validate.py"
