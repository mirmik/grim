"""Download the pinned official checkpoint to this experiment's local cache."""
import json
import os
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parent
os.environ['HF_HOME']=str(ROOT/'models')
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['HF_HUB_DOWNLOAD_TIMEOUT']='120'
from huggingface_hub import snapshot_download

spec=json.loads((ROOT/'model.json').read_text())
started=time.monotonic()
print(f'Downloading {spec["model_id"]} @ {spec["revision"]}; weights {spec["weight_bytes"]/1e9:.2f} GB',flush=True)
path=snapshot_download(spec['model_id'],revision=spec['revision'],
    allow_patterns=['*.safetensors','*.json','*.txt','*.jinja'],max_workers=3)
print(json.dumps(dict(path=path,download_seconds=round(time.monotonic()-started,1))),flush=True)
