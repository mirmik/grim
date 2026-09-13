"""Educational motion graphics driven by analytical beam mechanics and speech cues."""
import argparse
from dataclasses import replace
from functools import lru_cache
import io
import json
import math
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"output"
NARRATOR="XTTS v2"
os.environ.setdefault("MPLCONFIGDIR",str(OUT/"mpl-cache"))
from PIL import Image,ImageDraw,ImageFont,ImageColor
import numpy as np
from matplotlib import mathtext
from matplotlib.font_manager import FontProperties
from mechanics import BASE,validate

W,H,FPS=1920,1080,30
BG,PANEL,FG,MUTED,GRID="#0c1424","#111e32","#eef4ff","#9bafca","#2b405c"
CYAN,GOLD,RED,BLUE="#55dcda","#ffd479","#ff879b","#6bacff"
REG="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

@lru_cache(None)
def font(size,bold=False): return ImageFont.truetype(BOLD if bold else REG,size)
def text(d,xy,s,size=30,color=FG,anchor="la",bold=False):
    d.text(xy,str(s),font=font(size,bold),fill=color,anchor=anchor)
def ease(v):
    v=max(0,min(1,v))
    return v*v*(3-2*v)
def number(v,digits=2): return f"{v:.{digits}f}".replace(".",",")
def wrap(s,size,width):
    lines,line=[],""
    for word in s.split():
        trial=(line+" "+word).strip()
        if line and font(size).getlength(trial)>width: lines.append(line);line=word
        else: line=trial
    return lines+[line]
def paragraph(d,x,y,s,width=580,size=29,color=MUTED):
    for line in wrap(s,size,width):
        text(d,(x,y),line,size,color);y+=size*1.35
    return y
def dashed(d,a,b,color=GRID,width=2):
    dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
    if length<1:return
    for n in range(0,int(length),16):
        e=min(n+8,length)
        d.line((a[0]+dx*n/length,a[1]+dy*n/length,a[0]+dx*e/length,a[1]+dy*e/length),fill=color,width=width)
def arrow(d,a,b,color=GOLD,width=5,head=16):
    d.line((a,b),fill=color,width=width)
    angle=math.atan2(b[1]-a[1],b[0]-a[0])
    d.polygon([b,(b[0]-head*math.cos(angle-.45),b[1]-head*math.sin(angle-.45)),(b[0]-head*math.cos(angle+.45),b[1]-head*math.sin(angle+.45))],fill=color)
def dimension(d,a,b,label,color=MUTED):
    arrow(d,a,b,color,2,10);arrow(d,b,a,color,2,10)
    text(d,((a[0]+b[0])/2,(a[1]+b[1])/2+14),label,25,color,"ma")
@lru_cache(None)
def formula_image(expr,size=28,max_width=570):
    parsed=mathtext.MathTextParser('agg').parse("$"+expr+"$",dpi=155,prop=FontProperties(size=size))
    mask=Image.fromarray(np.asarray(parsed.image).copy())
    im=Image.new('RGBA',mask.size,FG)
    im.putalpha(mask)
    if im.width>max_width:im=im.resize((max_width,round(im.height*max_width/im.width)),Image.Resampling.LANCZOS)
    return im
def formula(im,xy,expr,size=28,max_width=570):
    f=formula_image(expr,size,max_width)
    im.paste(f,xy,f)
def panel(d,box):d.rounded_rectangle(box,radius=24,fill=PANEL)
def right(d,title):text(d,(1220,280),title,27,CYAN,bold=True)

def beam(d,b=BASE,x0=210,y0=420,scale=.8,exaggeration=35,factor=1,layers=False,load=True,color=CYAN,thickness=None):
    span=b.length*scale
    thick=b.height*scale if thickness is None else thickness
    def point(u,offset=0):
        x=b.length*u
        slope=b.force*x*(2*b.length-x)/(2*b.young*b.inertia)*exaggeration*factor
        norm=math.sqrt(1+slope*slope)
        return x0+x*scale-slope*offset/norm,y0+b.deflection(x)*scale*exaggeration*factor+offset/norm
    d.rectangle((x0-48,y0-76,x0,y0+90),fill=GRID)
    for y in range(int(y0-76),int(y0+90),20):d.line((x0-45,y,x0-4,y+25),fill=MUTED,width=2)
    dashed(d,(x0,y0),(x0+span+35,y0),MUTED)
    top=[point(i/160,-thick/2) for i in range(161)]
    bottom=[point(i/160,thick/2) for i in range(161)]
    d.polygon(top+bottom[::-1],fill="#203a50")
    d.line(top,fill=RED if layers else color,width=4)
    d.line(bottom,fill=BLUE if layers else color,width=4)
    d.line((top[-1],bottom[-1]),fill=color,width=3)
    if layers:
        for off in (-.33,-.16,0,.16,.33):
            pts=[point(i/160,thick*off) for i in range(161)]
            d.line(pts,fill=RED if off<0 else BLUE if off>0 else FG,width=2)
        for i in range(0,17):d.line((point(i/16,-thick/2),point(i/16,thick/2)),fill=GRID,width=2)
    end=point(1)
    if load:
        arrow(d,(end[0],end[1]-thick/2-125),(end[0],end[1]-thick/2-10))
        text(d,(end[0]-18,end[1]-thick/2-135),f"F = {b.force:.0f} Н",28,GOLD,"ra")
    return end,point

def moment_plot(d,u=1,cut=None):
    x0,x1,base,peak=210,1010,765,570
    d.line((x0,base,x1,base),fill=MUTED,width=2)
    d.polygon([(x0,base),(x0,peak),(x1,base)],fill="#2b3943")
    d.line((x0,peak,x1,base),fill=GOLD,width=5)
    text(d,(x0-18,peak-8),"200",27,GOLD,"ra")
    text(d,(x1,base+12),"L",25,MUTED,"ma")
    text(d,(x0,base+12),"0",25,MUTED,"ma")
    text(d,(x0,535),"|M|, Н·м",27,GOLD)
    if cut is not None:
        x=x0+(x1-x0)*cut;y=peak+(base-peak)*cut
        dashed(d,(x,base),(x,y),CYAN,3)
        d.ellipse((x-7,y-7,x+7,y+7),fill=CYAN)

def section_diagram(d,cx=390,cy=510,b=20,h=40,scale=5,stress=False):
    hw,hh=b*scale/2,h*scale/2
    if stress:
        for j in range(round(2*hh)):
            v=(j-hh)/hh
            base=ImageColor.getrgb(BLUE if v>0 else RED)
            neutral=ImageColor.getrgb(PANEL)
            col=tuple(round(neutral[k]+(base[k]-neutral[k])*abs(v)) for k in range(3))
            d.line((cx-hw,cy-hh+j,cx+hw,cy-hh+j),fill=col,width=1)
    else:d.rectangle((cx-hw,cy-hh,cx+hw,cy+hh),fill="#284356")
    d.rectangle((cx-hw,cy-hh,cx+hw,cy+hh),outline=CYAN,width=3)
    dashed(d,(cx-hw-55,cy),(cx+hw+65,cy),FG,2)
    dimension(d,(cx-hw,cy+hh+38),(cx+hw,cy+hh+38),f"b = {b:.0f} мм")
    arrow(d,(cx+hw+40,cy-hh),(cx+hw+40,cy+hh),MUTED,2,10)
    arrow(d,(cx+hw+40,cy+hh),(cx+hw+40,cy-hh),MUTED,2,10)
    text(d,(cx+hw+55,cy-15),f"h = {h:.0f}",25,MUTED)

def card_metrics(d,x,y,b,label):
    text(d,(x,y),label,30,FG,bold=True)
    text(d,(x,y+65),f"σmax = {number(b.max_stress)} МПа",34,RED)
    text(d,(x,y+120),f"δ = {number(b.tip,3)} мм",34,CYAN)

def make_frame(t,timeline):
    idx=next((i for i,s in enumerate(timeline) if t<s['end']),len(timeline)-1)
    scene=timeline[idx];mode=scene['id']
    first,last=scene['cues'][0],scene['cues'][-1]
    u=max(0,min(1,(t-first['start'])/(last['end']-first['start'])))
    a=ease((t-first['start'])/(first['end']-first['start']))
    im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
    text(d,(75,42),"СОПРОМАТ · ИЗГИБ КОНСОЛЬНОЙ БАЛКИ",24,CYAN)
    text(d,(1845,42),f"{idx+1:02d} / {len(timeline):02d}",24,MUTED,'ra')
    text(d,(75,102),scene['title'],51,FG,bold=True)
    text(d,(75,182),scene['chapter'],27,MUTED)
    panel(d,(60,250,1155,850));panel(d,(1180,250,1860,850))
    if mode in ('question','model','fibres','stress_number','deflection','limits','summary'):
        end,p=beam(d,factor=a if mode in ('question','fibres') else 1,layers=mode in ('fibres','summary'),thickness=75 if mode=='fibres' else None)
        text(d,(100,805),'Прогиб показан с увеличением ×35',24,MUTED)
        if mode=='question':
            d.rounded_rectangle((185,380,260,470),radius=10,outline=RED,width=4)
            text(d,(230,625),'Максимум напряжений',30,RED)
            text(d,(850,690),'Максимум прогиба',28,CYAN,'ma')
            right(d,'ДВА РАЗНЫХ МАКСИМУМА')
            paragraph(d,1220,365,'Большое перемещение ещё не означает большое напряжение.',size=34)
            paragraph(d,1220,560,'Разберём путь от внешней силы к тому, что происходит внутри материала.',size=30)
        elif mode=='model':
            dimension(d,(210,660),(1010,660),'L = 1 000 мм = 1 м')
            right(d,'ИСХОДНЫЕ ДАННЫЕ')
            for j,line in enumerate(['F = 200 Н','L = 1 000 мм','b × h = 20 × 40 мм','E = 200 000 МПа']):text(d,(1220,355+j*80),line,34,FG)
            paragraph(d,1220,700,'Постоянное прямоугольное сечение. Жёсткое закрепление слева.',size=27)
        elif mode=='fibres':
            text(d,(260,645),'Верхние слои: растяжение',30,RED)
            text(d,(260,705),'Нижние слои: сжатие',30,BLUE)
            right(d,'НЕЙТРАЛЬНЫЙ СЛОЙ')
            paragraph(d,1220,360,'Середина по высоте не удлиняется и не укорачивается.',size=33)
            paragraph(d,1220,535,'Это справедливо для однородного симметричного сечения при изгибе без продольной силы.',size=28)
        elif mode=='stress_number':
            text(d,(200,635),'У закрепления · на внешней поверхности',29,RED)
            formula(im,(215,705),r'|M|_{max}=FL=200\,\mathrm{N\,m}',25,860)
            right(d,'ЧИСЛЕННЫЙ РЕЗУЛЬТАТ')
            formula(im,(1230,355),r'\sigma_{max}=\frac{6FL}{bh^2}',30)
            text(d,(1230,505),'37,5 МПа',64,RED,bold=True)
            paragraph(d,1230,625,'Номинальное напряжение от изгиба. Местная концентрация напряжений здесь не моделируется.',size=28)
        elif mode=='deflection':
            arrow(d,(end[0]+60,420),(end[0]+60,end[1]),CYAN,3,12)
            text(d,(220,675),'Фактический прогиб: 3,125 мм',38,CYAN)
            right(d,'ЖЁСТКОСТЬ ПРИ ИЗГИБЕ')
            formula(im,(1230,350),r'\delta=\frac{FL^3}{3EI}',34)
            text(d,(1230,520),'E — модуль упругости',29,FG)
            text(d,(1230,575),'I — момент инерции площади',27,FG)
            paragraph(d,1230,670,'Материал и геометрия вместе задают жёсткость EI.',size=29)
        elif mode=='limits':
            text(d,(210,675),'δ / L = 0,003125',36,CYAN)
            right(d,'ДОПУЩЕНИЯ МОДЕЛИ')
            for j,line in enumerate(['Тонкая прямая балка','Малые деформации','Линейная упругость','Без собственного веса','Без потери устойчивости']):text(d,(1220,350+j*77),'• '+line,29,FG)
        else:
            text(d,(210,650),'Нагрузка → момент → напряжения',34,GOLD)
            text(d,(210,720),'Жёсткость EI → прогиб',34,CYAN)
            right(d,'ДВЕ НЕЗАВИСИМЫЕ ПРОВЕРКИ')
            text(d,(1220,365),'Прочность',43,RED,bold=True)
            formula(im,(1230,440),r'\sigma_{max}\leq[\sigma]',28)
            text(d,(1220,565),'Жёсткость',43,CYAN,bold=True)
            formula(im,(1230,640),r'\delta\leq[\delta]',28)
            text(d,(1220,760),'[ ] — допустимые значения',27,MUTED)
    elif mode in ('cut','moment'):
        cut=1-a if mode=='moment' else .72-.42*a
        beam(d,y0=410,factor=0)
        x=210+800*cut
        dashed(d,(x,325),(x,505),RED,4)
        dimension(d,(x,305),(1010,305),'плечо L − x',GOLD)
        if mode=='cut':
            arrow(d,(x+15,490),(x+15,425),CYAN,4)
            text(d,(x+34,475),'Q = F',27,CYAN)
            points=[(x+64*math.cos(math.radians(v)),420-64*math.sin(math.radians(v))) for v in range(-40,231,4)]
            d.line(points,fill=RED,width=4);arrow(d,points[-2],points[-1],RED,4,14)
            text(d,(x-85,460),'M',30,RED)
        moment_plot(d,cut=cut)
        right(d,'РАВНОВЕСИЕ ПРАВОЙ ЧАСТИ')
        formula(im,(1225,370),r'|M(x)|=F(L-x)',27)
        text(d,(1225,505),f'x = {number(cut,2)} м',35,MUTED)
        text(d,(1225,575),f'|M| = {200*(1-cut):.0f} Н·м',40,GOLD)
        paragraph(d,1225,690,'Эпюра показывает величину момента. По принятому знаку: M(x) = −F(L − x).',size=26)
    elif mode in ('stress','formula','section'):
        section_diagram(d,cx=365,cy=490,scale=4.7 if mode=='section' else 6,stress=mode!='section')
        if mode in ('stress','formula'):
            cx,cy=820,490
            d.line((cx,cy-150,cx,cy+150),fill=MUTED,width=2)
            d.polygon([(cx,cy-120),(cx+160,cy-120),(cx,cy)],fill='#683b49')
            d.polygon([(cx,cy),(cx-160,cy+120),(cx,cy+120)],fill='#284e77')
            d.line((cx+160,cy-120,cx-160,cy+120),fill=FG,width=4)
            text(d,(cx,cy-180),'σx по высоте',28,FG,'ma')
            text(d,(cx+170,cy-125),'+',30,RED)
            text(d,(cx-175,cy+105),'−',30,BLUE,'ra')
            text(d,(cx+22,cy),'0',25,MUTED)
            if mode=='stress':
                level=math.cos(math.pi*u)
                sy=cy-120*level
                d.line((305,sy,425,sy),fill=FG,width=3)
                sx=cx+160*level
                d.ellipse((sx-7,sy-7,sx+7,sy+7),fill=GOLD)
                text(d,(640,680),f'σx = {number(37.5*level)} МПа',29,GOLD)
            text(d,(200,750),'Нормальные напряжения вдоль балки',28,MUTED)
        else:
            section_diagram(d,cx=850,cy=490,h=40*(1+a),scale=4.7)
            text(d,(365,765),'I',38,CYAN,'ma')
            text(d,(850,765),f'{number((1+a)**3,1)}I',38,GOLD,'ma')
        if mode=='stress':
            right(d,'ЛИНЕЙНОЕ РАСПРЕДЕЛЕНИЕ')
            paragraph(d,1220,355,'У нейтральной оси: ноль. На внешних слоях: максимум.',size=34)
            text(d,(1220,550),'Растяжение: σx > 0',31,RED)
            text(d,(1220,620),'Сжатие: σx < 0',31,BLUE)
            paragraph(d,1220,720,'Речь о нормальных напряжениях от изгиба, не о касательных.',size=25)
        elif mode=='formula':
            right(d,'ФОРМУЛА ИЗГИБА')
            formula(im,(1230,350),r'\sigma_x=-\frac{My}{I}',34)
            for j,line in enumerate(['M — изгибающий момент','y — высота от нейтральной оси','I — момент инерции площади']):text(d,(1220,520+j*65),line,27,FG)
            paragraph(d,1220,735,'y направлена вверх; при нашей нагрузке M < 0.',size=26)
        else:
            right(d,'ПРЯМОУГОЛЬНОЕ СЕЧЕНИЕ')
            formula(im,(1230,345),r'I=\frac{bh^3}{12}',36)
            formula(im,(1230,505),r'h\times2\quad\Rightarrow\quad I\times8',26)
            paragraph(d,1220,660,'Это геометрическая характеристика площади, не массовый момент инерции.',size=29)
    elif mode in ('force','length','height'):
        field={'force':'force','length':'length','height':'height'}[mode]
        b=replace(BASE,**{field:getattr(BASE,field)*(1+a)})
        scale=.4 if mode=='length' else .76
        exagg=10 if mode=='length' else 18
        beam(d,y0=385,scale=scale,exaggeration=exagg)
        beam(d,b=b,y0=630,scale=scale,exaggeration=exagg,color=GOLD)
        text(d,(100,275),'Исходная балка',28,CYAN)
        text(d,(100,540),'После изменения',28,GOLD)
        text(d,(100,805),f'Общий масштаб прогиба для обеих балок: ×{exagg}',24,MUTED)
        right(d,{'force':'МЕНЯЕТСЯ ТОЛЬКО СИЛА','length':'МЕНЯЕТСЯ ТОЛЬКО ДЛИНА','height':'МЕНЯЕТСЯ ТОЛЬКО ВЫСОТА'}[mode])
        card_metrics(d,1220,350,BASE,'Было')
        card_metrics(d,1220,575,b,'Стало')
    elif mode=='compare':
        d.rectangle((60,250,1860,850),fill=BG)
        variants=[(BASE,'Исходное сечение','1× масса'),(replace(BASE,width=40),'Ширина ×2','2× масса'),(replace(BASE,height=80),'Высота ×2','2× масса')]
        for k,(b,title,mass) in enumerate(variants):
            x=60+k*610;panel(d,(x,250,x+585,850))
            text(d,(x+292,290),title,31,FG,'ma',True)
            section_diagram(d,cx=x+250,cy=510,b=b.width,h=b.height,scale=3)
            text(d,(x+35,705),f'δ = {number(b.tip,3)} мм',36,CYAN)
            text(d,(x+35,775),mass,29,GOLD)
    current=next((c for c in scene['cues'] if c['start']<=t<c['end']),None)
    if current:
        for n,line in enumerate(wrap(current['text'],33,1750)):
            text(d,(960,885+n*44),line,33,FG,'ma')
    text(d,(75,1028),'Учебная модель · теория Эйлера — Бернулли',22,MUTED)
    text(d,(1845,1028),f'Синтетический рассказчик · {NARRATOR}',22,MUTED,'ra')
    d.rectangle((0,1075,W*t/timeline[-1]['end'],1080),fill=CYAN)
    return im

def timecode(t):
    ms=round(t*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

def main():
    global OUT,NARRATOR
    parser=argparse.ArgumentParser()
    parser.add_argument('--stills-only',action='store_true')
    parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--narrator',default=NARRATOR)
    args=parser.parse_args()
    OUT=args.output_dir.resolve();NARRATOR=args.narrator
    (OUT/'mechanics-check.json').write_text(json.dumps(validate(),indent=2))
    timeline=json.loads((OUT/'timeline.json').read_text())
    cues=[c for s in timeline for c in s['cues']]
    (OUT/'subtitles.srt').write_text('\n\n'.join(f"{i+1}\n{timecode(c['start'])} --> {timecode(c['end'])}\n{c['text']}" for i,c in enumerate(cues))+'\n')
    for i,s in enumerate(timeline):make_frame(s['start']+.67*(s['end']-s['start']),timeline).save(OUT/f'preview-{i:02}.jpg',quality=94)
    for page in range(2):
        sheet=Image.new('RGB',(1280,4*360),BG)
        for j in range(8):
            with Image.open(OUT/f'preview-{page*8+j:02}.jpg') as im:sheet.paste(im.resize((640,360)),((j%2)*640,(j//2)*360))
        sheet.save(OUT/f'storyboard-{page+1}.jpg',quality=95)
    if args.stills_only:return
    count=math.ceil(timeline[-1]['end']*FPS)
    cmd=['ffmpeg','-hide_banner','-loglevel','warning','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-i',str(OUT/'narration.wav'),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-af','loudnorm=I=-16:TP=-1.5:LRA=7','-ar','48000','-movflags','+faststart','-shortest',str(OUT/'beam-bending-ru.mp4')]
    with subprocess.Popen(cmd,stdin=subprocess.PIPE) as proc:
        try:
            for i in range(count):
                proc.stdin.write(make_frame(i/FPS,timeline).tobytes())
                if i%(FPS*15)==0:print(f'Rendered {i/FPS:.0f}/{count/FPS:.0f}s',flush=True)
        finally:proc.stdin.close()
        if proc.wait():raise RuntimeError('FFmpeg failed')
    print(OUT/'beam-bending-ru.mp4',flush=True)

if __name__=='__main__':main()
