#!/usr/bin/env bash
set -euo pipefail
GEOMETRY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOX_PYTHON="${VOX_PYTHON:-$GEOMETRY_ROOT/../voxcpm2/.venv/bin/python}"
VIDEO_PYTHON="${VIDEO_PYTHON:-python3}"
GEOMETRY_OUT="$GEOMETRY_ROOT/output-voxcpm-scenes"
HF_HUB_OFFLINE=1 "$VOX_PYTHON" "$GEOMETRY_ROOT/synthesize.py"
"$VIDEO_PYTHON" "$GEOMETRY_ROOT/pace.py"
"$VIDEO_PYTHON" "$GEOMETRY_ROOT/../beam-bending/verify_speech.py" --output-dir "$GEOMETRY_OUT"
"$VIDEO_PYTHON" "$GEOMETRY_ROOT/../beam-bending/align_scene_cues.py" --output-dir "$GEOMETRY_OUT"
"$VIDEO_PYTHON" "$GEOMETRY_ROOT/render.py"
"$VIDEO_PYTHON" "$GEOMETRY_ROOT/validate.py"
"$VIDEO_PYTHON" "$GEOMETRY_ROOT/check_frames.py"
ffmpeg -v error -y -i "$GEOMETRY_OUT/spherical-geometry-ru.mp4" -c:v libvpx-vp9 -pix_fmt gbrp -colorspace rgb -profile:v 1 -lossless 1 -deadline realtime -cpu-used 8 -threads 12 -row-mt 1 -tile-columns 2 -c:a libopus -b:a 160k "$GEOMETRY_OUT/spherical-geometry-rgb.webm"
"$VIDEO_PYTHON" "$GEOMETRY_ROOT/check_frames.py" --rgb
