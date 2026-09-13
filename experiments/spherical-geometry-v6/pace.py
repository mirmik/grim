"""Assemble intact scene recordings, allowing a direct join after the experiment."""
import json
from pathlib import Path
import numpy as np
import soundfile as sf

OUT=Path(__file__).resolve().parent/'output-voxcpm-scenes'
timeline=json.loads((OUT/'timeline.json').read_text())
rate=48000
clips=[]
total=0
def append(x):
    global total
    clips.append(x);total+=len(x)
def silence(seconds):append(np.zeros(round(seconds*rate),dtype='float32'))
for s in timeline:
    files={c['file'] for c in s['cues']};assert len(files)==1
    file=files.pop();audio,sr=sf.read(OUT/file,dtype='float32');assert sr==rate
    s['start']=total/rate;silence(s.get('lead',.35));s['audio_start']=total/rate
    start=total/rate;append(audio)
    s['cues']=[dict(start=start,end=total/rate,text=' '.join(s['speech']),file=file)]
    silence(s.get('outro',.8));s['end']=total/rate
silence(1);timeline[-1]['end']=total/rate
sf.write(OUT/'narration.wav',np.concatenate(clips),rate,subtype='FLOAT')
(OUT/'timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2))
(OUT/'pacing-report.json').write_text(json.dumps(dict(duration=total/rate,
    joins=[dict(after=a['id'],before=b['id'],inserted_silence=b['audio_start']-a['cues'][-1]['end'])
           for a,b in zip(timeline,timeline[1:])],
    scene_audio='Intact original recordings; no speed changes or internal edits'),indent=2))
print('Paced duration:',total/rate)
