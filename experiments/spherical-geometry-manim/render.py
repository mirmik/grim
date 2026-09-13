"""Render native Manim scenes; concatenate at frame-aligned voice boundaries."""
import argparse
import json
import math
from pathlib import Path
import subprocess
from manim import tempconfig
from lesson import Lesson,TIMELINE,ROOT

parser=argparse.ArgumentParser()
parser.add_argument('--part',type=int)
parser.add_argument('--stills',action='store_true')
parser.add_argument('--resolution',type=int,default=1080)
args=parser.parse_args()
out=ROOT/'output';out.mkdir(exist_ok=True)
parts=range(len(TIMELINE)) if args.part is None else [args.part]
for part in parts:
    s=TIMELINE[part]
    print('Rendering',part,s['id'],'stills' if args.stills else 'video',flush=True)
    base=dict(pixel_width=round(args.resolution*16/9),pixel_height=args.resolution,
        frame_rate=30,frame_height=8,frame_width=128/9,background_color='#0a111d',
        renderer='cairo',media_dir=str(ROOT/'media' if args.stills else ROOT/'media/parts'/str(part)),disable_caching=True,
        verbosity='WARNING',progress_bar='none',write_to_movie=not args.stills,
        save_last_frame=args.stills,output_file=f'{part:02d}-{s["id"]}')
    if args.stills:
        for label,fraction in [('middle',.5),('end',.92)]:
            with tempconfig({**base,'output_file':f'{part:02d}-{s["id"]}-{label}'}):
                scene=Lesson(part=part,still_time=s['start']+fraction*(s['end']-s['start']))
                scene.render()
    else:
        with tempconfig(base):
            scene=Lesson(part=part);scene.render()
            video=Path(scene.renderer.file_writer.movie_file_path)
            target=out/f'{part:02d}-{s["id"]}.mp4'
            target.write_bytes(video.read_bytes())
        expected=(round(s['end']*30)-round(s['start']*30))/30
        duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(target)]))
        assert abs(duration-expected)<1/30+.002,(part,duration,expected)
        frames=int(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=nb_frames','-of','csv=p=0',str(target)]))
        assert frames==round(expected*30),(part,frames,round(expected*30))
        print(json.dumps(dict(part=part,id=s['id'],duration=duration,path=str(target))),flush=True)
