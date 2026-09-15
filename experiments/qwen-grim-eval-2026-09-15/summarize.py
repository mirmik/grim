"""Summarize measured API results; this does not grade the mathematics."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
rows=[]
for directory in sorted((ROOT/'runs').iterdir()):
    result=directory/'result.json'
    if not result.exists():
        continue
    meta=json.loads(result.read_text())
    answer=(directory/'answer.md').read_text()
    usage=meta.get('usage',{})
    timings=meta.get('response_timings',{})
    rows.append({
        'case': directory.name,
        'finish_reason':meta.get('finish_reason'),
        'prompt_tokens':usage.get('prompt_tokens'),
        'completion_tokens_including_reasoning':usage.get('completion_tokens'),
        'elapsed_seconds':round(meta['elapsed_seconds'],2),
        'first_content_seconds':round(meta.get('first_content_seconds',0),2) if 'first_content_seconds' in meta else None,
        'generation_tokens_per_second':round(timings['predicted_per_second'],2) if 'predicted_per_second' in timings else None,
        'answer_characters':len(answer),
        'russian_words':len(re.findall(r'[А-Яа-яЁё]+(?:[-‑][А-Яа-яЁё]+)*',answer)),
        'reasoning_characters':len((directory/'reasoning.txt').read_text()),
    })
(ROOT/'summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print(json.dumps(rows,ensure_ascii=False,indent=2))
