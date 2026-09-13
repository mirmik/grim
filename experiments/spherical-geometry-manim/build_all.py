"""Render independent Manim scenes in separate processes and media directories."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parent
timeline=json.loads((root/'output/timeline.json').read_text())
logs=root/'output/logs';logs.mkdir(exist_ok=True)
def render(part):
    started=time.monotonic()
    with (logs/f'{part:02d}.log').open('w') as log:
        subprocess.run([sys.executable,str(root/'render.py'),'--part',str(part)],stdout=log,stderr=subprocess.STDOUT,check=True)
    return dict(part=part,id=timeline[part]['id'],render_seconds=round(time.monotonic()-started,1))
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    jobs={pool.submit(render,i):i for i in range(len(timeline))}
    for job in concurrent.futures.as_completed(jobs):
        r=job.result();results.append(r);print(json.dumps(r),flush=True)
(root/'output/render-report.json').write_text(json.dumps(sorted(results,key=lambda r:r['part']),indent=2))
