#!/usr/bin/env bash
set -euo pipefail
OMNI_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -x "$OMNI_ROOT/.venv/bin/python" ]; then
  UV_CACHE_DIR=/tmp/grim-qwen-uv uv venv --python 3.12 "$OMNI_ROOT/.venv"
fi
# Read the established PyTorch/audio stack without changing the VoxCPM2 venv.
# The Omni-specific packages below shadow the shared copies.
"$OMNI_ROOT/.venv/bin/python" - "$OMNI_ROOT" <<'PY'
from pathlib import Path
import sys,sysconfig
root=Path(sys.argv[1]);shared=root.parent/'voxcpm2/.venv/lib/python3.12/site-packages'
assert shared.is_dir()
Path(sysconfig.get_path('purelib'),'shared-tts-runtime.pth').write_text(str(shared)+'\n')
PY
UV_CACHE_DIR=/tmp/grim-qwen-uv uv pip install --link-mode=copy --python "$OMNI_ROOT/.venv/bin/python" --no-deps \
  'bitsandbytes==0.49.2' 'accelerate==1.15.0' 'transformers==5.2.0' \
  'huggingface-hub==1.31.0' 'safetensors==0.7.0' 'tokenizers==0.22.2' 'typer==0.27.2'
"$OMNI_ROOT/.venv/bin/python" - <<'PY'
import torch,transformers,accelerate,bitsandbytes
print('torch',torch.__version__,'transformers',transformers.__version__,'accelerate',accelerate.__version__,'bitsandbytes',bitsandbytes.__version__)
PY
