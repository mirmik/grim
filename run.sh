#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

python=python3
if [[ -x .venv/bin/python ]]; then
    python=.venv/bin/python
fi

host=${GRIM_HOST:-127.0.0.1}
port=${GRIM_PORT:-8000}

exec "$python" -m uvicorn server.app:app \
    --host "$host" \
    --port "$port" \
    --timeout-graceful-shutdown 2 \
    "$@"
