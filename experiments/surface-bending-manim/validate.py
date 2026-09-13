"""Check actual encoded frames, animated geometry, timing and uninterrupted audio."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import numpy as np
import soundfile as sf
from PIL import Image,ImageDraw
from geometry import validate as geometry_checks

root=Path(__file__).resolve().parent;out=root/'output';video=out/'normal-and-curvature.mp4'
timeline=json.loads((out/'timeline.json').read_text());fps=30
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
    'stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,pix_fmt,profile,has_b_frames,color_space:format=duration,size','-of','json',str(video)]))
v=next(s for s in probe['streams'] if s['codec_type']=='video');a=next(s for s in probe['streams'] if s['codec_type']=='audio')
assert (v['width'],v['height'],v['r_frame_rate'],v['pix_fmt'])==(1920,1080,'30/1','yuv420p')
assert v['profile']=='Constrained Baseline' and v['has_b_frames']==0 and v['color_space']=='bt709'
assert a['codec_name']=='aac'
assert abs(float(probe['format']['duration'])-timeline[-1]['end'])<.08
assert int(v['nb_frames'])==round(timeline[-1]['end']*fps)
full,sr=sf.read(out/'narration.wav',dtype='float32');assert sr==48000
for s in timeline:
    files={c['file'] for c in s['cues']};assert len(files)==1
    wav,rate=sf.read(root/'output-voxcpm-scenes'/files.pop(),dtype='float32');assert rate==sr
    start=round(s['audio_start']*sr)
    assert np.array_equal(full[start:start+len(wav)],wav),s['id']
for x,y in zip(timeline,timeline[1:]):assert abs(y['audio_start']-x['cues'][-1]['end']-.35)<1e-6
samples=[];motions={}
for i,s in enumerate(timeline):
    for label,f in [('middle',.5),('end',.92)]:
        samples.append((round((s['start']+f*(s['end']-s['start']))*fps),i,label))
    windows={'normals':(2,3),'section':(3,3),'principal':(0,1),'saddle':(2,2),'cylinder':(4,4),'sphere':(3,3)}
    if s['id'] in windows:
        lo,hi=windows[s['id']];start=s['cues'][lo]['start'];end=s['cues'][hi]['end']
        motions[s['id']]=[round((start+f*(end-start))*fps) for f in [.1,.5,.9]]
indices=sorted(set(n+d for n,_,_ in samples for d in [-1,0,1])|{n for ns in motions.values() for n in ns})
decoded=out/'decoded';decoded.mkdir(exist_ok=True)
select='select='+'+'.join(f'eq(n\\,{n})' for n in indices)
subprocess.run(['ffmpeg','-v','error','-xerror','-y','-i',str(video),'-vf',select,'-fps_mode','vfr',str(decoded/'%03d.png')],check=True)
def actual(n):return np.asarray(Image.open(decoded/f'{indices.index(n)+1:03d}.png').convert('RGB'),dtype=float)
references=[]
for n,i,label in samples:
    target=np.asarray(Image.open(root/'media/images'/f'{i:02d}-{timeline[i]["id"]}-{label}.png').convert('RGB'),dtype=float)
    mse=min(float(np.mean((actual(n+d)-target)**2)) for d in [-1,0,1])
    psnr=10*math.log10(255**2/max(mse,1e-12));assert psnr>30,(i,label,psnr)
    references.append(dict(scene=timeline[i]['id'],label=label,psnr=round(psnr,2)))
motion_report={}
for name,ns in motions.items():
    frames=[actual(n)[180:900,100:960] for n in ns]
    changes=[int(np.sum(np.max(np.abs(a-b),axis=-1)>25)) for a,b in zip(frames,frames[1:])]
    assert min(changes)>500,(name,changes)
    motion_report[name]=changes
subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True)
for j in range(0,len(timeline),6):
    selected=samples[2*j:2*min(j+6,len(timeline)):2]
    sheet=Image.new('RGB',(1280,386*((len(selected)+1)//2)), '#0a111d');draw=ImageDraw.Draw(sheet)
    for k,(n,i,label) in enumerate(selected):
        x=k%2*640;y=k//2*386;im=Image.fromarray(actual(n).astype('uint8')).resize((640,360))
        sheet.paste(im,(x,y+26));draw.text((x+8,y+7),timeline[i]['id'],fill='white')
    sheet.save(out/f'storyboard-{j//6+1}.jpg')
report=dict(status='passed',media=probe,geometry=geometry_checks(),reference_frames=references,
    moving_geometry=motion_report,narration='Each scene waveform preserved exactly; 0.35s joins',
    full_decode='passed',video_sha256=hashlib.sha256(video.read_bytes()).hexdigest())
(out/'validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
