"""Deterministic narrated motion graphic; Pillow frames piped directly into FFmpeg."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
W, H, FPS = 1920, 1080, 30
BG, PANEL = "#0c1424", "#111e32"
FG, MUTED, GRID = "#eef4ff", "#94a8c5", "#243550"
CYAN, GOLD, PINK = "#55dcda", "#ffd479", "#fa91bb"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTS = {size: ImageFont.truetype(FONT, size) for size in (23, 25, 28, 30, 34, 36, 40, 44, 50)}
HEAD = ImageFont.truetype(BOLD, 54)
CX, CY, R = 395, 530, 150
GX, GW = 875, 860
TAU = 2 * math.pi

def ease(x):
    x = min(1, max(0, x))
    return x*x*(3-2*x)

def wrapped(text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if font.getlength(trial) > width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line]

def label(draw, xy, text, size=30, color=FG, anchor="la"):
    draw.text(xy, text, font=FONTS[size], fill=color, anchor=anchor)

def dashed(draw, a, b, color, width=2, step=15):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return
    for start in range(0, int(length), step):
        end = min(start + step*.52, length)
        draw.line([(a[0]+dx*start/length,a[1]+dy*start/length), (a[0]+dx*end/length,a[1]+dy*end/length)], fill=color, width=width)

def angle_for(mode, u):
    if mode == "zero": return 0
    if mode == "top": return math.pi/2 * ease((u-.10)/.50)
    if mode == "half": return math.pi/2 + math.pi/2*ease((u-.08)/.50)
    if mode == "bottom":
        return math.pi + math.pi/2*ease(u/.32) + math.pi/2*ease((u-.58)/.30)
    return TAU * u

def subtitle_entries(timeline):
    entries = []
    for scene in timeline:
        sentences = re.split(r"(?<=[.!?])\s+", scene["text"])
        lengths = [len(s.split()) for s in sentences]
        total = sum(lengths)
        cursor = scene["speech_start"]
        for sentence, count in zip(sentences, lengths):
            end = cursor + (scene["speech_end"]-scene["speech_start"])*count/total
            entries.append({"start": cursor, "end": end, "text": sentence})
            cursor = end
    return entries

def timecode(t):
    ms = round(t*1000)
    return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"

def frame(t, timeline, subtitles):
    index = next((i for i,s in enumerate(timeline) if t < s["end"]), len(timeline)-1)
    s = timeline[index]
    u = min(1, max(0, (t-s["speech_start"])/(s["speech_end"]-s["speech_start"])))
    mode = s["mode"]
    angle = angle_for(mode, u)
    amplitude = 1 + .5*ease(u/.45) if mode == "amplitude" else 1
    rad = R*amplitude
    px, py = CX+rad*math.cos(angle), CY-rad*math.sin(angle)
    qx = GX+GW*angle/TAU
    image = Image.new("RGB", (W,H), BG)
    d = ImageDraw.Draw(image)
    label(d, (80, 48), "МАТЕМАТИКА ДВИЖЕНИЯ", 25, CYAN)
    label(d, (1840, 48), f"{index+1:02d} / {len(timeline):02d}", 25, MUTED, "ra")
    d.text((80, 109), s["title"], font=HEAD, fill=FG)
    label(d, (80, 192), "Окружность → проекция → волна", 28, MUTED)
    d.rounded_rectangle((65,265,735,825), radius=24, fill=PANEL)
    d.rounded_rectangle((770,265,1855,825), radius=24, fill=PANEL)
    label(d, (98,285), "ВРАЩЕНИЕ", 23, MUTED)
    label(d, (805,285), "ВЫСОТА В ЗАВИСИМОСТИ ОТ УГЛА", 23, MUTED)
    # Circle coordinates and the signed vertical projection.
    d.line((CX-255,CY,CX+255,CY), fill=GRID, width=2)
    d.line((CX,CY-225,CX,CY+225), fill=GRID, width=2)
    d.ellipse((CX-rad,CY-rad,CX+rad,CY+rad), outline=MUTED, width=3)
    if angle > .03:
        d.arc((CX-45,CY-45,CX+45,CY+45), start=-math.degrees(angle), end=0, fill=GOLD, width=3)
    d.line((CX,CY,px,py), fill=GOLD, width=5)
    label(d, (CX+50,CY+16), "θ", 30, GOLD)
    if mode != "orbit":
        d.line((CX,CY,CX,py), fill=PINK, width=7)
        dashed(d, (CX,py), (px,py), PINK)
        d.ellipse((CX-7,py-7,CX+7,py+7), fill=PINK)
        label(d, (CX-20, (CY+py)/2-16), "y", 30, PINK, "ra")
    d.ellipse((px-10,py-10,px+10,py+10), fill=GOLD)
    d.ellipse((CX-4,CY-4,CX+4,CY+4), fill=FG)
    label(d, (98,775), f"R = {amplitude:.1f}".replace(".",","), 30, GOLD)
    label(d, (690,775), f"θ = {math.degrees(angle):.0f}°", 30, MUTED, "ra")
    # Stable scales: changing radius must actually increase the plotted height.
    for y in (-1,0,1):
        sy = CY-y*R
        d.line((GX,sy,GX+GW,sy), fill=GRID, width=2)
        label(d, (GX-22,sy), str(y).replace("-","−"), 25, MUTED, "rm")
    for degrees in (0,90,180,270,360):
        x = GX+GW*degrees/360
        d.line((x,330,x,755), fill=GRID, width=1)
        label(d, (x,765), f"{degrees}°", 25, MUTED, "ma")
    d.line((GX,CY,GX+GW+12,CY), fill=MUTED, width=2)
    d.line((GX,755,GX,330), fill=MUTED, width=2)
    label(d, (GX-35,325), "y", 28, PINK)
    if mode in ("orbit", "height"):
        label(d, (GX+GW/2,415), "Следим за одной координатой", 34, FG, "ma")
        label(d, (GX+GW/2,610), "Высота плавно меняется", 30, MUTED, "ma")
        # Preview the projection at a fixed column, before drawing the waveform.
        if mode == "height":
            projection_x = GX+GW/2
            dashed(d,(px,py),(projection_x,py),PINK)
            d.ellipse((projection_x-9,py-9,projection_x+9,py+9),fill=PINK)
    else:
        ghost = [(GX+GW*i/400,CY-rad*math.sin(TAU*i/400)) for i in range(401)]
        d.line(ghost, fill=GRID, width=4)
        points = [(GX+GW*(angle*i/400)/TAU,CY-rad*math.sin(angle*i/400)) for i in range(401)]
        d.line(points, fill=CYAN, width=6)
        dashed(d,(px,py),(qx,py),PINK,2)
        d.ellipse((qx-10,py-10,qx+10,py+10),fill=CYAN)
        formula = "y = R · sin θ" if mode == "amplitude" else "y = sin θ"
        label(d, (1810,335), formula, 40, CYAN, "ra")
        if mode in ("zero", "top", "half", "bottom"):
            label(d, (1810,690), f"y = {amplitude*math.sin(angle):+.2f}".replace(".",","), 36, PINK, "ra")
    # Narration captions; sentence timings are estimated within each audio clip.
    current = next((c["text"] for c in subtitles if c["start"] <= t < c["end"]), "")
    if current:
        lines = wrapped(current,FONTS[36],1720)
        for line_no,line in enumerate(lines):
            label(d,(W/2,883+line_no*48),line,36,FG,"ma")
    label(d,(80,1024),"Синтетический рассказчик · XTTS v2",23,MUTED)
    label(d,(1840,1024),"Короткий учебный эксперимент",23,MUTED,"ra")
    d.rectangle((0,H-5,W*t/timeline[-1]["end"],H),fill=CYAN)
    return image

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stills-only", action="store_true")
    args = parser.parse_args()
    timeline = json.loads((OUT/"timeline.json").read_text())
    captions = subtitle_entries(timeline)
    (OUT/"subtitles.srt").write_text("\n\n".join(f"{i+1}\n{timecode(c['start'])} --> {timecode(c['end'])}\n{c['text']}" for i,c in enumerate(captions))+"\n")
    for i,scene in enumerate(timeline):
        frame(scene["start"]+.7*(scene["end"]-scene["start"]),timeline,captions).save(OUT/f"preview-{i:02d}.jpg",quality=92)
    thumbs = Image.new("RGB",(960,5*270),BG)
    for i in range(len(timeline)):
        with Image.open(OUT/f"preview-{i:02d}.jpg") as im:
            thumbs.paste(im.resize((480,270)),((i%2)*480,(i//2)*270))
    thumbs.save(OUT/"storyboard.jpg",quality=95)
    if args.stills_only:
        return
    total_frames = math.ceil(timeline[-1]["end"]*FPS)
    command = ["ffmpeg","-hide_banner","-loglevel","warning","-y", "-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(FPS),"-i","pipe:0", "-i",str(OUT/"narration.wav"),"-map","0:v:0","-map","1:a:0", "-c:v","libx264","-preset","fast","-crf","20","-pix_fmt","yuv420p", "-c:a","aac","-b:a","160k","-af","loudnorm=I=-16:TP=-1.5:LRA=7","-ar","48000", "-movflags","+faststart","-shortest",str(OUT/"sine-explained-ru.mp4")]
    with subprocess.Popen(command,stdin=subprocess.PIPE) as encoder:
        try:
            for i in range(total_frames):
                encoder.stdin.write(frame(i/FPS,timeline,captions).tobytes())
                if i%(FPS*10) == 0:
                    print(f"Rendered {i/FPS:.0f}/{total_frames/FPS:.0f}s",flush=True)
        finally:
            encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError("FFmpeg failed")
    print(OUT/"sine-explained-ru.mp4",flush=True)

if __name__ == "__main__":
    main()
