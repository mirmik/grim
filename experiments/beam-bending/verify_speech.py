"""Independent local recognition; this does not evaluate prosody or stress placement."""
import argparse
import json
from pathlib import Path
from faster_whisper import WhisperModel

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
parser=argparse.ArgumentParser()
parser.add_argument('--files',nargs='+')
parser.add_argument('--output-dir',type=Path,default=OUT)
args=parser.parse_args()
OUT=args.output_dir.resolve()
model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=6,download_root='/tmp/grim-video-whisper',local_files_only=True)
timeline=json.loads((OUT/'timeline.json').read_text())
results=json.loads((OUT/'speech-check.json').read_text()) if args.files and (OUT/'speech-check.json').exists() else []
for scene in timeline:
    grouped={}
    for c in scene['cues']:
        grouped.setdefault(c['file'],[]).append(c['text'])
    for file,texts in grouped.items():
        cue={'file':file,'text':' '.join(texts)}
        if args.files and cue['file'] not in args.files:continue
        segments,_=model.transcribe(str(OUT/cue['file']),language='ru',beam_size=5,word_timestamps=True)
        segments=list(segments)
        recognized=' '.join(s.text.strip() for s in segments)
        words=[{'word':w.word,'start':w.start,'end':w.end} for s in segments for w in (s.words or [])]
        results=[r for r in results if r['file']!=cue['file']]
        results.append({'file':cue['file'],'expected':cue['text'],'recognized':recognized,'words':words})
        print(cue['file']+': '+recognized,flush=True)
(OUT/'speech-check.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
