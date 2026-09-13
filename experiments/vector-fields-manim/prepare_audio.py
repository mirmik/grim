"""Keep scene WAVs intact; use short joins, with no pauses for empty title cards."""
import json
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parent
out=ROOT/'output-voxcpm-scenes'
script=json.loads((ROOT/'script.json').read_text())
rate=48000;clips=[];timeline=[];total=0
def add(audio):
    global total
    clips.append(audio);total+=len(audio)
def silence(seconds):add(np.zeros(round(seconds*rate),dtype='float32'))
for i,scene in enumerate(script):
    file=f'{i:02d}-{scene["id"]}-0.wav';audio,sr=sf.read(out/file,dtype='float32');assert sr==rate
    entry={**scene,'start':total/rate};silence(.2);entry['audio_start']=total/rate
    add(audio)
    entry['cues']=[dict(text=' '.join(scene['speech']),file=file,start=entry['audio_start'],end=total/rate)]
    silence(.15 if i<len(script)-1 else .45);entry['end']=total/rate;timeline.append(entry)
sf.write(out/'narration.wav',np.concatenate(clips),rate,subtype='FLOAT')
(out/'timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2))
print(f'{total/rate:.2f}s; {len(script)} intact recordings; 0.35s inserted between scenes')
