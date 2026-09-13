#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

python=python3
if [[ -x .venv/bin/python ]]; then
    python=.venv/bin/python
fi

exec "$python" -m uvicorn server.app:app \
    --host 127.0.0.1 \
    --port 8000 \
    --timeout-graceful-shutdown 2 \
    "$@"
