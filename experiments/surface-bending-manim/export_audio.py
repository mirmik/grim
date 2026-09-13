"""Export the aligned narration, accessible WebVTT captions and chapter markers."""
import json
from pathlib import Path
import shutil
import textwrap

root=Path(__file__).resolve().parent;src=root/'output-voxcpm-scenes';out=root/'output'
out.mkdir(exist_ok=True)
timeline=json.loads((src/'timeline.json').read_text())
for name in ['timeline.json','narration.wav']:shutil.copyfile(src/name,out/name)
def stamp(t):
    ms=round(t*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f'{h:02d}:{m:02d}:{s:02d}.{ms:03d}'
vtt=['WEBVTT',''];srt=[];chapters=['WEBVTT',''];n=1
for scene in timeline:
    chapters.extend([f'{stamp(scene["start"])} --> {stamp(scene["end"])}',scene['title'],''])
    for cue in scene['cues']:
        text=cue['text'].replace('дэбл-ю','w').replace('зэт','z')
        caption='\n'.join(textwrap.wrap(text,88))
        times=f'{stamp(cue["start"])} --> {stamp(cue["end"])}'
        vtt.extend([str(n),times,caption,'']);srt.extend([str(n),times.replace('.',','),caption,'']);n+=1
(out/'subtitles.vtt').write_text('\n'.join(vtt),encoding='utf-8')
(out/'subtitles.srt').write_text('\n'.join(srt),encoding='utf-8')
(out/'chapters.vtt').write_text('\n'.join(chapters),encoding='utf-8')
(out/'narration.md').write_text('# Как поверхность изгибается\n\n'+'\n\n'.join('## '+s['title']+'\n\n'+' '.join(s['speech']) for s in timeline)+'\n')
print(f'Exported narration and {n-1} caption cues')
