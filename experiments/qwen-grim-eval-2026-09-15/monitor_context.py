"""Stop our experiment if a request consumes one full runtime context.

This is a context bound, not a time/thinking budget. It does not change or stop
the model server. The only signalled process is our run.py found at startup.
"""
import json
import os
import signal
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
runner_pids=[]
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        argv=(proc/'cmdline').read_bytes().split(b'\0')
        if len(argv)>1 and argv[1] == b'experiments/qwen-grim-eval-2026-09-15/run.py':
            runner_pids.append(int(proc.name))
    except OSError:
        pass
if len(runner_pids) != 1:
    raise SystemExit(f'Expected one experiment runner, found {runner_pids}')
pid=runner_pids[0]
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
print('Monitoring context for experiment runner',pid,flush=True)
while Path(f'/proc/{pid}').exists():
    active=[p.parent for p in (ROOT/'runs').glob('0*/request.json') if not (p.parent/'result.json').exists()]
    if active:
        current=max(active,key=lambda p:(p/'request.json').stat().st_mtime)
        events=current/'events.jsonl'
        # Only inspect a slot while our own request is actively receiving data.
        if events.exists() and time.time()-events.stat().st_mtime<15:
            try:
                with opener.open('http://192.168.0.173:8096/slots',timeout=10) as response:
                    slots=json.load(response)
                for slot in slots:
                    if not slot.get('is_processing'):
                        continue
                    prompt=slot.get('n_prompt_tokens_processed',0)+slot.get('n_prompt_tokens_cache',0)
                    decoded=max((x.get('n_decoded',0) for x in slot.get('next_token',[])),default=0)
                    capacity=slot.get('n_ctx',131072)
                    progress={'case':current.name,'prompt_tokens':prompt,'decoded_tokens':decoded,'context_capacity':capacity,'observed_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
                    (ROOT/'context-progress.json').write_text(json.dumps(progress,indent=2))
                    if prompt+decoded>=capacity:
                        progress.update(complete=False,finish_reason='context_exhausted',elapsed_seconds=time.time()-(current/'request.json').stat().st_mtime,usage={'prompt_tokens':prompt,'completion_tokens':decoded,'total_tokens':prompt+decoded},usage_is_slot_observation=True)
                        (current/'context-exhausted.json').write_text(json.dumps(progress,indent=2))
                        os.kill(pid,signal.SIGINT)
                        (current/'result.json').write_text(json.dumps(progress,indent=2))
                        print('Context exhausted:',json.dumps(progress),flush=True)
                        raise SystemExit(0)
            except (OSError,ValueError) as exc:
                print('Monitor read failed:',type(exc).__name__,flush=True)
    time.sleep(10)
print('Experiment runner ended',flush=True)
