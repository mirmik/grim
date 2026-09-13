"""Preview/apply narrowly selected trailing TTS artefact cuts using ASR word times."""
import argparse
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import shutil
import numpy as np
import soundfile as sf

OUT=Path(__file__).resolve().parent/'output'
def normalize(s):
    value=re.sub(r'[^а-яa-z0-9]','',s.lower().replace('ё','е'))
    return 'миллиметр' if value=='мм' or value.startswith('миллиметр') else value
parser=argparse.ArgumentParser()
parser.add_argument('files',nargs='+')
parser.add_argument('--apply',action='store_true')
args=parser.parse_args()
records=json.loads((OUT/'speech-check.json').read_text())
edits=[]
for r in records:
    if r['file'] not in args.files:continue
    target=normalize(r['expected'].split()[-1])
    words=r['words']
    matches=[i for i,w in enumerate(words[:-1]) if len(target)>=4 and (SequenceMatcher(None,normalize(w['word']),target).ratio()>=.9 or (i>0 and normalize(words[i-1]['word']+w['word'])==target))]
    if not matches:
        print('No confident trailing boundary:',r['file']);continue
    i=matches[-1]
    path=OUT/r['file'];audio,sr=sf.read(path,dtype='float32')
    end=min(len(audio),round((words[i]['end']+.035)*sr))
    if len(audio)-end<.12*sr:continue
    edit={'file':r['file'],'last_kept_word':words[i]['word'],'removed_transcript':' '.join(w['word'] for w in words[i+1:]),'old_duration':len(audio)/sr,'new_duration':end/sr}
    edits.append(edit)
    if args.apply:
        archive=OUT/'before-tail-trim';archive.mkdir(exist_ok=True)
        if not (archive/path.name).exists():shutil.copy2(path,archive/path.name)
        audio=audio[:end].copy();audio[-240:]*=np.linspace(1,0,240)
        sf.write(path,audio,sr,subtype='PCM_16')
print(json.dumps(edits,ensure_ascii=False,indent=2))
if args.apply:
    log=OUT/'tail-edits.json'
    previous=json.loads(log.read_text()) if log.exists() else []
    combined={e['file']:e for e in previous+edits}
    log.write_text(json.dumps(list(combined.values()),ensure_ascii=False,indent=2))
