"""Frame-counted H.264/AAC MP4, ready for progressive playback and seeking."""
import json
from pathlib import Path
import subprocess
from PIL import Image

root=Path(__file__).resolve().parent;out=root/'output'
timeline=json.loads((out/'timeline.json').read_text());clips=[];records=[]
for i,s in enumerate(timeline):
    path=out/f'{i:02d}-{s["id"]}.mp4'
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
        'stream=codec_type,width,height,nb_frames','-of','json',str(path)]))
    v=next(x for x in probe['streams'] if x['codec_type']=='video')
    frames=round(s['end']*30)-round(s['start']*30)
    assert (v['width'],v['height'],int(v['nb_frames']))==(1920,1080,frames)
    assert "'" not in str(path)
    clips.append("file '"+str(path)+"'")
    records.append(dict(id=s['id'],frames=frames))
(out/'concat.txt').write_text('\n'.join(clips)+'\n')
video=out/'vector-fields-and-comparison.mp4'
subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(out/'concat.txt'),
    '-i',str(out/'narration.wav'),'-map','0:v:0','-map','1:a:0',
    '-vf','setpts=N/(30*TB),scale=in_color_matrix=bt601:out_color_matrix=bt709:in_range=tv:out_range=tv,format=yuv420p',
    '-r','30','-c:v','libx264','-preset','fast','-crf','18','-profile:v','baseline','-level:v','4.0',
    '-bf','0','-refs','1','-g','60','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-color_range','tv',
    '-c:a','aac','-b:a','160k','-ar','48000','-af','loudnorm=I=-16:TP=-1.5:LRA=7','-shortest',
    '-movflags','+faststart',str(video)],check=True)
Image.open(root/'media/images/06-transport-middle.png').convert('RGB').save(out/'vector-fields-and-comparison.jpg',quality=93)
(out/'assembly-report.json').write_text(json.dumps(dict(scenes=records,total_frames=sum(r['frames'] for r in records),
    duration=timeline[-1]['end'],narration='Intact VoxCPM2 recordings, one per scene',captions='Optional external WebVTT'),indent=2))
print(video,flush=True)
