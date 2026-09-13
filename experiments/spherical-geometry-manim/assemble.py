"""Mux the original narration with frame-counted Manim animation."""
import hashlib
import json
from pathlib import Path
import subprocess
import soundfile as sf

root=Path(__file__).resolve().parent;out=root/'output'
timeline=json.loads((out/'timeline.json').read_text())
clips=[];records=[]
for i,s in enumerate(timeline):
    path=out/f'{i:02d}-{s["id"]}.mp4'
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
        'stream=codec_type,width,height,nb_frames','-of','json',str(path)]))
    v=next(x for x in probe['streams'] if x['codec_type']=='video')
    expected=round(s['end']*30)-round(s['start']*30)
    assert (v['width'],v['height'],int(v['nb_frames']))==(1920,1080,expected),(s['id'],v,expected)
    assert "'" not in str(path)
    clips.append("file '"+str(path)+"'")
    records.append(dict(id=s['id'],frames=expected,start_frame=round(s['start']*30),end_frame=round(s['end']*30)))
(out/'scenes.ffconcat').write_text('\n'.join(clips)+'\n')
video=out/'spherical-geometry-manim-ru.mp4'
subprocess.run(['ffmpeg','-hide_banner','-nostats','-v','error','-y','-f','concat','-safe','0',
    '-i',str(out/'scenes.ffconcat'),'-i',str(out/'narration.wav'),'-map','0:v:0','-map','1:a:0',
    '-vf','setpts=N/(30*TB),scale=in_color_matrix=bt601:out_color_matrix=bt709:in_range=tv:out_range=tv,format=yuv420p',
    '-r','30','-c:v','libx264','-preset','fast','-crf','18','-profile:v','baseline','-level:v','4.0',
    '-bf','0','-refs','1','-g','60','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-color_range','tv',
    '-c:a','aac','-b:a','160k','-ar','48000','-af','loudnorm=I=-16:TP=-1.5:LRA=7','-shortest',
    '-movflags','+faststart',str(video)],check=True)
end=next(s['start'] for s in timeline if s['id']=='area')
subprocess.run(['ffmpeg','-v','error','-y','-i',str(video),'-t',str(end),'-c','copy',
    '-movflags','+faststart',str(out/'opening-manim.mp4')],check=True)
source=root.parent/'spherical-geometry-v6/output-voxcpm-scenes/narration.wav'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(source)==digest(out/'narration.wav')
(out/'assembly-report.json').write_text(json.dumps(dict(scenes=records,
    total_frames=sum(r['frames'] for r in records),narration_seconds=sf.info(out/'narration.wav').duration,
    original_narration_sha256=digest(source),narration='byte-identical to v6; no TTS regeneration',
    frame_timing='CFR 30 fps rebuilt from frame indices, independent of intermediate container timestamps'),indent=2))
print(video)
