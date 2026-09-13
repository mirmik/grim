"""Check the encoded animation, source narration, scene timing and visible motion."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image,ImageDraw
from geometry import validate as geometry_checks

parser=argparse.ArgumentParser();parser.add_argument('--rgb',action='store_true');args=parser.parse_args()
root=Path(__file__).resolve().parent;out=root/'output'
video=out/('spherical-geometry-manim-rgb.webm' if args.rgb else 'spherical-geometry-manim-ru.mp4')
timeline=json.loads((out/'timeline.json').read_text())
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
    'stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,duration,pix_fmt,profile,has_b_frames,color_space:format=duration,size','-of','json',str(video)]))
v=next(s for s in probe['streams'] if s['codec_type']=='video')
assert (v['width'],v['height'],v['r_frame_rate'])==(1920,1080,'30/1')
assert abs(float(probe['format']['duration'])-timeline[-1]['end'])<.08
if not args.rgb:
    assert v['profile']=='Constrained Baseline' and v['has_b_frames']==0 and v['color_space']=='bt709'
    assert int(v['nb_frames'])==round(timeline[-1]['end']*30)
source=root.parent/'spherical-geometry-v6/output-voxcpm-scenes/narration.wav'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(source)==sha(out/'narration.wav')
motion=next(s for s in timeline if s['id']=='transport_fast')
result=next(s for s in timeline if s['id']=='excess')
assert motion['cues'][-1]['end']==result['audio_start']
sample_times=[]
for i,s in enumerate(timeline):
    for label,f in [('middle',.5),('end',.92)]:
        sample_times.append((round((s['start']+f*(s['end']-s['start']))*30),i,label))
motion_indices=[round((motion['cues'][a]['start']+motion['cues'][b]['end'])/2*30) for a,b in motion['motion_sections']]
indices=sorted(set([n for n,_,_ in sample_times]+motion_indices))
folder=out/('decoded-rgb' if args.rgb else 'decoded');folder.mkdir(exist_ok=True)
select='select='+'+'.join(f'eq(n\\,{i})' for i in indices)
subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(video),'-vf',select,'-fps_mode','vfr','-y',str(folder/'%03d.png')],check=True)
def actual(n):return np.asarray(Image.open(folder/f'{indices.index(n)+1:03d}.png').convert('RGB'),dtype=float)
reports=[]
for n,i,label in sample_times:
    expected=np.asarray(Image.open(root/'media/images'/f'{i:02d}-{timeline[i]["id"]}-{label}.png').convert('RGB'),dtype=float)
    delta=actual(n)-expected;mse=float(np.mean(delta**2));psnr=10*math.log10(255**2/max(mse,1e-12))
    # Adjacent frame sampling and two YUV420 encodes can affect moving edges.
    assert psnr>30,(timeline[i]['id'],label,psnr)
    reports.append(dict(id=timeline[i]['id'],label=label,seconds=n/30,psnr=round(psnr,2)))
    print(timeline[i]['id'],label,round(psnr,2),flush=True)
arrow=[actual(n)[245:860,130:930] for n in motion_indices]
changes=[int(np.sum(np.max(np.abs(a-b),axis=-1)>25)) for a,b in zip(arrow,arrow[1:])]
assert min(changes)>1000,changes
subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True)
if not args.rgb:
    sheet=Image.new('RGB',(1440,405),'#0a111d')
    for j,n in enumerate(motion_indices):
        im=Image.open(folder/f'{indices.index(n)+1:03d}.png').crop((100,200,990,890)).resize((480,372))
        sheet.paste(im,(480*j,33));ImageDraw.Draw(sheet).text((480*j+15,10),f'{n/30:.2f} s',fill='white')
    sheet.save(out/'arrow-motion-check.jpg')
report=dict(status='passed',media=probe,geometry=geometry_checks(),narration_sha256=sha(source),
    narration='Original v6 narration reused byte-for-byte; unchanged scene order and timings',
    experiment_join='No inserted pause',reference_frames=reports,arrow_changed_pixels=changes,
    full_decode='passed',scope='Software decode and renderer comparison; the user VLC/GPU path is not tested')
(out/('validation-rgb.json' if args.rgb else 'validation.json')).write_text(json.dumps(report,indent=2))
