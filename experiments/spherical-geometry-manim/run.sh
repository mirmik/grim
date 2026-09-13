#!/usr/bin/env bash
set -euo pipefail
MANIM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIM_PYTHON="$MANIM_ROOT/.venv/bin/python"
MANIM_OUT="$MANIM_ROOT/output"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
mkdir -p "$MANIM_OUT"
cp "$MANIM_ROOT/../spherical-geometry-v6/output-voxcpm-scenes/"{narration.wav,timeline.json,subtitles.srt} "$MANIM_OUT/"
"$MANIM_PYTHON" "$MANIM_ROOT/render.py" --stills
"$MANIM_PYTHON" "$MANIM_ROOT/build_all.py"
"$MANIM_PYTHON" "$MANIM_ROOT/assemble.py"
"$MANIM_PYTHON" "$MANIM_ROOT/validate.py"
ffmpeg -v error -y -i "$MANIM_OUT/spherical-geometry-manim-ru.mp4" -c:v libvpx-vp9 -pix_fmt gbrp -colorspace rgb -profile:v 1 -lossless 1 -deadline realtime -cpu-used 8 -threads 12 -row-mt 1 -tile-columns 2 -c:a libopus -b:a 160k "$MANIM_OUT/spherical-geometry-manim-rgb.webm"
"$MANIM_PYTHON" "$MANIM_ROOT/validate.py" --rgb
