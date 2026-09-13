from scene_support import *
from scenes import draw_visual, DYNAMIC

STATIC_FRAMES={}


def make_frame(t,timeline):
    idx=next((i for i,s in enumerate(timeline) if t<s['end']),len(timeline)-1)
    s=timeline[idx]
    if s['id'] in DYNAMIC:
        im=draw_visual(t,timeline,idx)
    else:
        if idx not in STATIC_FRAMES:STATIC_FRAMES[idx]=draw_visual(t,timeline,idx)
        im=STATIC_FRAMES[idx].copy()
    d=ImageDraw.Draw(im)
    # Keep sentence captions brief; no cuts are made in the actual scene audio.
    current=next((c for c in s['cues'] if c['start']<=t<c['end']),None)
    if current:
        lines=wrap(current['text'],32,1740)
        assert len(lines)<=3,(s['id'],lines)
        for n,line in enumerate(lines):text(d,(960,878+n*43),line,32,FG,'ma')
    text(d,(75,1030),'Геодезические · параллельный перенос · кривизна',22,MUTED)
    text(d,(1845,1030),'Синтетический рассказчик · VoxCPM2',22,MUTED,'ra')
    d.rectangle((0,1075,W*t/timeline[-1]['end'],1080),fill=CYAN)
    return im

def timecode(t):
    ms=round(t*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stills-only',action='store_true');args=parser.parse_args()
    timeline=json.loads((OUT/'timeline.json').read_text())
    (OUT/'geometry-check.json').write_text(json.dumps(validate(),indent=2))
    cues=[c for s in timeline for c in s['cues']]
    (OUT/'subtitles.srt').write_text('\n\n'.join(f"{i+1}\n{timecode(c['start'])} --> {timecode(c['end'])}\n{c['text']}" for i,c in enumerate(cues))+'\n')
    for i,s in enumerate(timeline):
        for label,u in [('start',.12),('middle',.55),('end',.9)]:
            make_frame(s['start']+u*(s['end']-s['start']),timeline).save(OUT/f'preview-{i:02d}-{label}.jpg',quality=93)
    for page in range(math.ceil(len(timeline)/6)):
        sheet=Image.new('RGB',(1280,1080),BG)
        for j in range(6):
            i=page*6+j
            if i>=len(timeline):break
            with Image.open(OUT/f'preview-{i:02d}-middle.jpg') as im:sheet.paste(im.resize((640,360)),((j%2)*640,(j//2)*360))
        sheet.save(OUT/f'storyboard-{page+1}.jpg',quality=94)
    if args.stills_only:return
    count=math.ceil(timeline[-1]['end']*FPS)
    cmd=['ffmpeg','-hide_banner','-loglevel','warning','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-i',str(OUT/'narration.wav'),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','18','-profile:v','baseline','-level:v','4.0','-bf','0','-refs','1','-g','60','-vf','scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709','-color_range','tv','-c:a','aac','-b:a','160k','-af','loudnorm=I=-16:TP=-1.5:LRA=7','-ar','48000','-movflags','+faststart','-shortest',str(OUT/'spherical-geometry-ru.mp4')]
    with subprocess.Popen(cmd,stdin=subprocess.PIPE) as proc:
        try:
            for i in range(count):
                proc.stdin.write(make_frame(i/FPS,timeline).tobytes())
                if i%(FPS*15)==0:print(f'Rendered {i/FPS:.0f}/{count/FPS:.0f}s',flush=True)
        finally:proc.stdin.close()
        if proc.wait():raise RuntimeError('FFmpeg failed')
    print(OUT/'spherical-geometry-ru.mp4',flush=True)

if __name__=='__main__':main()
