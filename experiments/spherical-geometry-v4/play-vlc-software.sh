#!/usr/bin/env bash
set -euo pipefail
GEOMETRY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# One launch with software decoding and X11 output. Does not edit vlcrc.
exec vlc --no-one-instance --avcodec-hw=none --vout=xcb_x11 "${1:-$GEOMETRY_ROOT/output-voxcpm-scenes/spherical-geometry-ru.mp4}"
