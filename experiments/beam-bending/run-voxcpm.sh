#!/usr/bin/env bash
set -euo pipefail
BEAM_VIDEO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOX_PYTHON="${VOX_PYTHON:-$BEAM_VIDEO_ROOT/../voxcpm2/.venv/bin/python}"
VIDEO_PYTHON="${VIDEO_PYTHON:-python3}"
HF_HUB_OFFLINE=1 "$VOX_PYTHON" "$BEAM_VIDEO_ROOT/synthesize_voxcpm.py"
for VOX_VARIANT in scenes sentences; do
  VOX_OUT="$BEAM_VIDEO_ROOT/output-voxcpm-$VOX_VARIANT"
  "$VIDEO_PYTHON" "$BEAM_VIDEO_ROOT/verify_speech.py" --output-dir "$VOX_OUT"
  if [[ "$VOX_VARIANT" == scenes ]]; then
    "$VIDEO_PYTHON" "$BEAM_VIDEO_ROOT/align_scene_cues.py" --output-dir "$VOX_OUT"
  fi
  "$VIDEO_PYTHON" "$BEAM_VIDEO_ROOT/render.py" --output-dir "$VOX_OUT" --narrator VoxCPM2
  "$VIDEO_PYTHON" "$BEAM_VIDEO_ROOT/validate.py" --output-dir "$VOX_OUT"
done
