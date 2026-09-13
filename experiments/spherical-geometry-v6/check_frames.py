"""Compare actual software-decoded MP4 frames with the corresponding source frames."""
import json
import argparse
import math
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image
import render

out=render.OUT
parser=argparse.ArgumentParser()
parser.add_argument('--rgb',action='store_true')
args=parser.parse_args()
video=out/('spherical-geometry-rgb.webm' if args.rgb else 'spherical-geometry-ru.mp4')
timeline=json.loads((out/'timeline.json').read_text())
indices=[round((s['start']+q*(s['end']-s['start']))*render.FPS) for s in timeline for q in (.25,.8)]
motion=next(s for s in timeline if s['id']=='transport_fast')
motion_indices=[round((motion['cues'][a]['start']+motion['cues'][b]['end'])/2*render.FPS) for a,b in motion['motion_sections']]
indices=sorted(set(indices+motion_indices))
target=out/('decoded-check-rgb' if args.rgb else 'decoded-check');target.mkdir(exist_ok=True)
select='select='+ '+'.join(f'eq(n\\,{i})' for i in indices)
subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(video),
                '-vf',select,'-fps_mode','vfr','-y',str(target/'%03d.png')],check=True)
reports=[]
motion_images=[]
for j,i in enumerate(indices):
    expected=np.asarray(render.make_frame(i/render.FPS,timeline),dtype=float)
    actual=np.asarray(Image.open(target/f'{j+1:03d}.png').convert('RGB'),dtype=float)
    if i in motion_indices:motion_images.append(actual[235:850,60:1140].copy())
    delta=actual-expected
    mse=float(np.mean(delta**2));psnr=10*math.log10(255**2/max(mse,1e-12))
    # Compare compression against an uncompressed BT.709 YUV420 round trip.
    # Thin colored strokes lose chroma detail even without a lossy codec.
    conversion='scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p,scale=in_range=tv:out_range=full:in_color_matrix=bt709,'
    conversion+=('format=gbrp,format=rgb24' if args.rgb else 'format=rgb24')
    raw=subprocess.check_output(['ffmpeg','-v','error','-f','rawvideo','-pix_fmt','rgb24',
        '-s','1920x1080','-i','pipe:0','-vf',
        conversion,
        '-frames:v','1','-f','rawvideo','pipe:1'],input=expected.astype('uint8').tobytes())
    reference=np.frombuffer(raw,dtype='uint8').reshape(expected.shape).astype(float)
    delta=actual-reference
    reference_psnr=10*math.log10(255**2/max(float(np.mean(delta**2)),1e-12))
    colored=np.ptp(expected,axis=-1)>60
    cmse=float(np.mean(delta[colored]**2))
    cpsnr=10*math.log10(255**2/max(cmse,1e-12))
    reports.append(dict(frame=i,seconds=i/render.FPS,rgb_psnr=psnr,yuv420_reference_psnr=reference_psnr,colored_pixel_psnr=cpsnr))
    print(f'{j+1:02d}: {i/render.FPS:.2f}s RGB {psnr:.1f}; YUV reference {reference_psnr:.1f}; color {cpsnr:.1f} dB',flush=True)
    # The raw RGB PSNR is diagnostic only: YUV420 subsampling dominates it
    # on dense saturated meshes. Gate errors beyond that expected conversion.
    assert reference_psnr>38 and cpsnr>35,(i,psnr,reference_psnr,cpsnr)
changes=[int(np.sum(np.max(np.abs(a-b),axis=-1)>25)) for a,b in zip(motion_images,motion_images[1:])]
assert len(changes)==2 and min(changes)>500,('Arrow must move visibly in the actual video',changes)
(out/('frame-comparison-rgb.json' if args.rgb else 'frame-comparison.json')).write_text(json.dumps(dict(decoder='FFmpeg software',samples=reports,
    arrow_motion=dict(frame_indices=motion_indices,changed_pixels=changes,status='passed'),
    status='passed',scope='Encoded frames match the renderer within lossy YUV420 tolerances; this does not test the user player/GPU'),indent=2))
