"""Analytical 3D motion graphics with whole-scene speech and aligned captions."""
import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image, ImageDraw
from drawing import W,H,FPS,BG,PANEL,FG,MUTED,GRID,CYAN,GOLD,RED,BLUE,text,wrap,paragraph,arrow,dashed,panel,formula,ease
from geometry import N,A,unit,arc,vertices,transport,cylinder,validate

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output-voxcpm-scenes'
VIEW=unit([1,1,.85]);RIGHT=unit([-1,1,0]);UP=np.cross(VIEW,RIGHT)
CX,CY,R=600,520,270

def project(p,center=(CX,CY),scale=R):
    p=np.asarray(p)
    return (float(center[0]+scale*np.dot(p,RIGHT)),float(center[1]-scale*np.dot(p,UP)))

def line3(d,points,color=CYAN,width=4,visible=False,center=(CX,CY),scale=R):
    segment=[]
    for p in points:
        if not visible or np.dot(p,VIEW)>=-.002:
            segment.append(project(p,center,scale))
        else:
            if len(segment)>1:d.line(segment,fill=color,width=width)
            segment=[]
    if len(segment)>1:d.line(segment,fill=color,width=width)

def sphere_point(lat,lon):
    return np.array([math.cos(lat)*math.cos(lon),math.cos(lat)*math.sin(lon),math.sin(lat)])

@lru_cache(1)
def globe():
    im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
    panel(d,(60,235,1140,850))
    size=2*R+1
    yy,xx=np.mgrid[-R:R+1,-R:R+1]/R
    zz=np.sqrt(np.maximum(0,1-xx*xx-yy*yy))
    shade=np.clip(.35+.48*zz-.14*xx-.2*yy,0,1)
    rgb=np.stack([17+shade*25,31+shade*48,49+shade*63],axis=-1).astype('uint8')
    patch=Image.fromarray(rgb)
    mask=Image.fromarray(((xx*xx+yy*yy<=1)*255).astype('uint8'))
    im.paste(patch,(CX-R,CY-R),mask)
    d=ImageDraw.Draw(im)
    for lat in np.linspace(-math.pi/2,math.pi/2,13)[1:-1]:
        line3(d,[sphere_point(lat,l) for l in np.linspace(0,2*math.pi,180)],'#355574',1,True)
    for lon in np.linspace(0,2*math.pi,24,endpoint=False):
        line3(d,[sphere_point(l,lon) for l in np.linspace(-math.pi/2,math.pi/2,100)],'#355574',1,True)
    d.ellipse((CX-R,CY-R,CX+R,CY+R),outline='#486686',width=2)
    return im

def triangle(im,phi=math.pi/2,progress=3,fill=True,labels=True,angles=False):
    d=ImageDraw.Draw(im)
    vs=vertices(phi)
    allpoints=[]
    for a,b in zip(vs,vs[1:]):allpoints += [arc(a,b,u) for u in np.linspace(0,1,61)]
    if fill:
        overlay=Image.new('RGBA',im.size)
        ImageDraw.Draw(overlay).polygon([project(p) for p in allpoints],fill=(58,195,180,58))
        im.paste(overlay,(0,0),overlay)
        d=ImageDraw.Draw(im)
    colors=[CYAN,GOLD,BLUE]
    for i,(a,b) in enumerate(zip(vs,vs[1:])):
        line3(d,[arc(a,b,u) for u in np.linspace(0,1,61)],'#4b687c',3)
        end=np.clip(progress-i,0,1)
        if end>0:line3(d,[arc(a,b,u) for u in np.linspace(0,end,61)],colors[i],6)
    if labels:
        for j,(p,label,off) in enumerate(zip(vs,['N','A','Б'],[(0,-43),(-40,7),(40,7)])):
            x,y=project(p);d.ellipse((x-6,y-6,x+6,y+6),fill=FG)
            text(d,(x+off[0],y+off[1]),label,29,FG,'ma',True)
    if angles:
        for j,p in enumerate(vs[:3]):
            q=vs[(j+1)%3];r=vs[(j+2)%3]
            e=unit(q-np.dot(p,q)*p);f=unit(r-np.dot(p,r)*p)
            angle=math.acos(np.clip(np.dot(e,f),-1,1))
            side=unit(f-np.dot(e,f)*e)
            line3(d,[p+.13*(math.cos(t)*e+math.sin(t)*side) for t in np.linspace(0,angle,31)],FG,3)

def vector(d,p,v,color=GOLD,size=.37):
    x,y=project(p)
    d.ellipse((x-7,y-7,x+7,y+7),fill=FG)
    arrow(d,project(p),project(p+v*size),color,7,19)

def local_plane(im,p):
    e=unit(np.cross(p,[0,0,1])) if abs(p[2])<.95 else A
    f=np.cross(p,e)
    points=[project(p+.24*(a*e+b*f)) for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    overlay=Image.new('RGBA',im.size);d=ImageDraw.Draw(overlay)
    d.polygon(points,fill=(130,174,227,35),outline=(151,193,247,170),width=2)
    im.paste(overlay,(0,0),overlay)

def tangent_inset(d):
    d.rounded_rectangle((88,315,300,562),radius=15,fill=BG,outline=GRID,width=2)
    text(d,(105,330),'Вид сверху на N',19,MUTED)
    o=(135,493)
    arrow(d,o,(267,493),BLUE,5,14)
    arrow(d,o,(135,380),GOLD,5,14)
    d.line((135,471,157,471,157,493),fill=FG,width=2)
    text(d,(176,423),'90°',30,FG)
    text(d,(105,530),'Касательная плоскость',15,MUTED)

def info(d,title,body=None,y=285,color=CYAN):
    for j,line in enumerate(wrap(title,27,600)):
        text(d,(1200,y+j*34),line,27,color,bold=True)
    if body:paragraph(d,1200,y+70,body,width=600,size=31)

def phase(scene,t,first=0,last=1):
    cues=scene['cues']
    a=cues[min(first,len(cues)-1)]['start'];b=cues[min(last,len(cues)-1)]['end']
    return ease((t-a)/max(.01,b-a))

def flat_diagram(d,u):
    a=np.array([230.,710.]);b=np.array([970.,710.]);c=np.array([535.,355.])
    d.polygon([tuple(a),tuple(b),tuple(c)],fill='#1c3a4b')
    d.line([tuple(a),tuple(b),tuple(c),tuple(a)],fill=CYAN,width=5)
    dashed(d,(160,355),(1040,355),GOLD,3)
    text(d,(1040,310),'∥ основанию',25,GOLD,'ra')
    # Circular arcs come from the actual planar triangle, not hand-drawn angles.
    for p,q,r,col in [(a,b,c,RED),(b,c,a,BLUE),(c,a,b,GOLD)]:
        v=q-p;w=r-p
        ang1=math.atan2(v[1],v[0]);ang2=math.atan2(w[1],w[0])
        delta=(ang2-ang1+math.pi)%(2*math.pi)-math.pi
        pts=[tuple(p+65*np.array([math.cos(th),math.sin(th)])) for th in np.linspace(ang1,ang1+delta,40)]
        d.line(pts,fill=col,width=5)
    text(d,(335,664),'α',35,RED);text(d,(815,660),'β',35,BLUE);text(d,(526,433),'γ',35,GOLD)
    if u>.25:
        text(d,(435,361),'α',34,RED);text(d,(630,361),'β',34,BLUE)
    text(d,(600,780),'α + β + γ = 180°',39,FG,'ma',True)

def surface_mesh(d,kind,center,scale=170,bend=0):
    # View along (1,1,.85) supports both the saddle and isometric cylinder strip.
    def point(x,y):
        if kind=='saddle':return np.array([x,y,.36*(x*x-y*y)])
        return cylinder(x,y,bend)
    vals=np.linspace(-1.35,1.35,15)
    cells=[]
    for a,b in zip(vals,vals[1:]):
        for c,e in zip(vals,vals[1:]):
            pts=[point(a,c),point(b,c),point(b,e),point(a,e)]
            cells.append((np.dot(np.mean(pts,axis=0),VIEW),pts,a,c))
    for depth,pts,a,c in sorted(cells,key=lambda v:v[0]):
        col='#243f59' if (round((a+1.35)/.193)+round((c+1.35)/.193))%2 else '#1b3148'
        d.polygon([project(p,center,scale) for p in pts],fill=col)
    for val in vals:
        line3(d,[point(val,y) for y in np.linspace(-1.35,1.35,50)],'#55748d',2,center=center,scale=scale)
        line3(d,[point(x,val) for x in np.linspace(-1.35,1.35,50)],'#55748d',2,center=center,scale=scale)
    if kind=='saddle':
        line3(d,[point(x,0) for x in np.linspace(-1.35,1.35,70)],GOLD,5,center=center,scale=scale)
        line3(d,[point(0,y) for y in np.linspace(-1.35,1.35,70)],RED,5,center=center,scale=scale)
    else:
        xy=[(-.85,-.8),(.95,-.8),(.15,.85),(-.85,-.8)]
        for (x,y),(xx,yy) in zip(xy,xy[1:]):
            line3(d,[point(x+(xx-x)*u,y+(yy-y)*u) for u in np.linspace(0,1,70)],GOLD,5,center=center,scale=scale)

def draw_visual(t,timeline,idx):
    s=timeline[idx];mode=s['id'];u=phase(s,t,0,len(s['cues'])-1)
    im=globe().copy();d=ImageDraw.Draw(im)
    panel(d,(1165,235,1860,850))
    text(d,(75,40),'ДИФФЕРЕНЦИАЛЬНАЯ ГЕОМЕТРИЯ · ПЕРВЫЙ ВЗГЛЯД',23,CYAN)
    text(d,(1845,40),f'{idx+1:02d} / {len(timeline):02d}',24,MUTED,'ra')
    text(d,(75,100),s['title'],49,FG,bold=True)
    text(d,(75,175),s['chapter'],27,MUTED)
    if mode=='flat':
        panel(d,(60,235,1140,850));flat_diagram(d,u)
        info(d,'ПЛОСКОСТЬ','Параллельная прямая собирает три угла в один развёрнутый угол.')
        formula(im,(1200,545),r'\alpha+\beta+\gamma=\pi',31,600)
        paragraph(d,1200,680,'Доказательство опирается на геометрию плоскости.',600,29)
    elif mode=='geodesic':
        line3(d,[sphere_point(0,l) for l in np.linspace(0,2*math.pi,240)],GOLD,5,True)
        line3(d,[sphere_point(l,0) for l in np.linspace(-math.pi,math.pi,240)],CYAN,5,True)
        line3(d,[sphere_point(math.pi/4,l) for l in np.linspace(0,2*math.pi,240)],RED,5,True)
        text(d,(170,770),'Большая окружность: центр совпадает с центром сферы',25,MUTED)
        info(d,'БОЛЬШИЕ ОКРУЖНОСТИ')
        text(d,(1200,370),'Экватор',35,GOLD);text(d,(1200,435),'Меридианы',35,CYAN)
        text(d,(1200,555),'Параллель 45°',35,RED)
        paragraph(d,1200,620,'Не геодезическая: путь поворачивает внутри поверхности.',600,29)
    elif mode in ('transport_rule','transport_a','transport_b','transport_c','holonomy'):
        progress={'transport_rule':.38,'transport_a':phase(s,t,0,2),'transport_b':1+phase(s,t,0,2),'transport_c':2+phase(s,t,0,2),'holonomy':3}[mode]
        triangle(im,progress=3)
        p,v=transport(progress);local_plane(im,p);d=ImageDraw.Draw(im)
        vector(d,N,A,BLUE);vector(d,p,v)
        text(d,(135,796),'Голубая метка — исходное направление',26,BLUE)
        if mode=='transport_rule':
            info(d,'ДВА ПРАВИЛА')
            paragraph(d,1200,365,'На стороне: постоянный угол с геодезической.',600,34,FG)
            paragraph(d,1200,535,'В вершине: стрелка сохраняет направление, маршрут поворачивает.',600,32)
            text(d,(1200,755),'Стрелка касательна к сфере',27,GOLD)
        elif mode=='holonomy':
            tangent_inset(d)
            info(d,'ГОЛОНОМИЯ')
            text(d,(1200,373),'Δθ = 90°',65,GOLD,bold=True)
            paragraph(d,1200,493,'Поворот после замкнутого маршрута',600,31)
            text(d,(1200,620),'270° − 180° = 90°',42,CYAN)
            text(d,(1200,718),'Тот же угловой избыток',28,MUTED)
        else:
            info(d,{'transport_a':'N → A','transport_b':'A → Б','transport_c':'Б → N'}[mode])
            texts={'transport_a':('Стрелка смотрит вперёд','Угол с движением: 0°'), 'transport_b':('Стрелка смотрит поперёк','Угол с движением: 90°'), 'transport_c':('Стрелка смотрит назад','Угол с движением: 180°')}
            paragraph(d,1200,390,texts[mode][0],600,40,FG)
            text(d,(1200,555),texts[mode][1],30,GOLD)
            if mode=='transport_c' and progress>2.98:text(d,(1200,695),'Итоговый поворот: 90°',35,CYAN)
            else:paragraph(d,1200,675,'Собственный поворот внутри поверхности отсутствует.',600,28)
    elif mode=='saddle':
        panel(d,(60,235,1140,850));surface_mesh(d,'saddle',(600,530),220)
        text(d,(600,780),'Два главных направления изгибаются по-разному',26,MUTED,'ma')
        info(d,'ОТРИЦАТЕЛЬНАЯ КРИВИЗНА')
        formula(im,(1200,370),r'K=k_1 k_2<0',33,600)
        formula(im,(1200,530),r'\alpha+\beta+\gamma<\pi',30,600)
        paragraph(d,1200,665,'Если K < 0 во всей области геодезического треугольника.',600,30)
    elif mode=='cylinder':
        panel(d,(60,235,1140,850));bend=1.15*phase(s,t,1,3)
        surface_mesh(d,'cylinder',(600,635),225,bend)
        text(d,(600,790),'Лист сворачивается без растяжения',28,MUTED,'ma')
        info(d,'ИЗГИБ ЕСТЬ, ГАУССОВА КРИВИЗНА — 0')
        formula(im,(1200,390),r'K=k_1 k_2=\frac{1}{r}\cdot0=0',30,600)
        paragraph(d,1200,560,'Длины и внутренние углы треугольника сохраняются.',600,32)
        text(d,(1200,725),'α + β + γ = 180°',40,GOLD)
    else:
        phi=math.pi/2
        if mode=='vary':phi=math.pi/2-math.pi/3*phase(s,t,0,2)
        progress=sum(phase(s,t,i,i) for i in (1,2,3)) if mode=='route' else 3
        triangle(im,phi=phi,progress=progress,angles=mode in ('hook','angles','vary','summary'))
        d=ImageDraw.Draw(im)
        if mode=='route':
            p,_=transport(progress);x,y=project(p);d.ellipse((x-10,y-10,x+10,y+10),fill=FG)
            info(d,'ТРИ ДУГИ БОЛЬШИХ ОКРУЖНОСТЕЙ')
            for j,(label,col) in enumerate([('N → A · меридиан',CYAN),('A → Б · экватор',GOLD),('Б → N · меридиан',BLUE)]):text(d,(1200,390+j*100),label,33,col)
            text(d,(1200,755),'Каждая дуга: четверть окружности',26,MUTED)
        elif mode in ('hook','angles'):
            info(d,'УГЛЫ НА ПОВЕРХНОСТИ')
            text(d,(1200,395),'90° + 90° + 90°',44,CYAN)
            text(d,(1200,480),'= 270°',76,GOLD,bold=True)
            paragraph(d,1200,660,'Измеряем углы между касательными, а не на проекции.',600,31)
            if mode=='angles':text(d,(600,795),'Белые дуги отмечают внутренние углы',26,MUTED,'ma')
        elif mode=='area':
            # Highlight the boundary great circles dividing the sphere into octants.
            for axis in range(3):
                pts=[]
                for q in np.linspace(0,2*math.pi,241):
                    p=np.zeros(3);p[(axis+1)%3]=math.cos(q);p[(axis+2)%3]=math.sin(q);pts.append(p)
                line3(d,pts,'#84a1bd',2,True)
            info(d,'ОДНА ВОСЬМАЯ СФЕРЫ')
            formula(im,(1200,385),r'A=\frac{4\pi R^2}{8}=\frac{\pi R^2}{2}',31,600)
            formula(im,(1200,580),r'\frac{A}{R^2}=\frac{\pi}{2}=90^\circ',34,600)
            text(d,(600,795),'Три плоскости → восемь равных областей',26,MUTED,'ma')
        elif mode=='vary':
            info(d,'УГОЛ У ПОЛЮСА')
            deg=math.degrees(phi)
            text(d,(1200,365),f'φ = {deg:.0f}°',63,GOLD,bold=True)
            text(d,(1200,480),f'Сумма: {180+deg:.0f}°',41,FG)
            text(d,(1200,570),f'Избыток: {deg:.0f}°',41,CYAN)
            formula(im,(1200,705),r'A=R^2\varphi',31,600)
        elif mode=='curvature':
            info(d,'ДЛЯ ЛЮБОГО СФЕРИЧЕСКОГО ТРЕУГОЛЬНИКА')
            formula(im,(1200,380),r'E=\alpha+\beta+\gamma-\pi',28,600)
            formula(im,(1200,500),r'E=KA,\qquad K=\frac{1}{R^2}',32,600)
            paragraph(d,1200,685,'Углы — в радианах. Кривизна K — в единицах 1 / длина².',600,29)
            text(d,(600,795),'При фиксированной площади: R ↑ → избыток ↓',27,MUTED,'ma')
        elif mode=='bonnet':
            info(d,'ТРЕУГОЛЬНАЯ ФОРМА ТЕОРЕМЫ')
            formula(im,(1195,380),r'\alpha+\beta+\gamma-\pi=\int_T K\,dA',32,630)
            paragraph(d,1200,535,'T — область без дыр. Все три стороны — геодезические.',600,32,FG)
            paragraph(d,1200,710,'Интеграл складывает кривизну по всей области.',600,29)
            # Subdivision indicates the integration region, not different curvature on this sphere.
            for lat in np.linspace(.15,1.4,7):line3(d,[sphere_point(lat,l) for l in np.linspace(0,math.pi/2,65)],'#71bbb7',2)
            for lon in np.linspace(.15,1.4,7):line3(d,[sphere_point(l,lon) for l in np.linspace(0,math.pi/2,65)],'#71bbb7',2)
            text(d,(600,795),'На сфере K постоянно; в общем случае K = K(p)',25,MUTED,'ma')
        elif mode=='intrinsic':
            info(d,'ИЗМЕРЕНИЯ ВНУТРИ ПОВЕРХНОСТИ')
            for j,label in enumerate(['Длины','Углы','Перенос направлений']):text(d,(1200,375+80*j),label,37,[FG,CYAN,GOLD][j])
            paragraph(d,1200,680,'Сферическую карту нельзя сделать без искажений всех длин.',600,30)
        elif mode=='summary':
            vector(d,N,A,BLUE);vector(d,*transport(3))
            info(d,'ОДНА ГЕОМЕТРИЯ — ДВА ОПЫТА')
            text(d,(1200,380),'Сумма углов: 270°',40,CYAN)
            text(d,(1200,485),'Поворот стрелки: 90°',37,GOLD)
            formula(im,(1200,600),r'E=\int_T K\,dA',38,600)
            text(d,(1200,765),'Кривизну можно обнаружить изнутри',25,MUTED)
    return im


STATIC_FRAMES={}
DYNAMIC={'flat','route','transport_a','transport_b','transport_c','vary','cylinder'}

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
    cmd=['ffmpeg','-hide_banner','-loglevel','warning','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-i',str(OUT/'narration.wav'),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-af','loudnorm=I=-16:TP=-1.5:LRA=7','-ar','48000','-movflags','+faststart','-shortest',str(OUT/'spherical-geometry-ru.mp4')]
    with subprocess.Popen(cmd,stdin=subprocess.PIPE) as proc:
        try:
            for i in range(count):
                proc.stdin.write(make_frame(i/FPS,timeline).tobytes())
                if i%(FPS*15)==0:print(f'Rendered {i/FPS:.0f}/{count/FPS:.0f}s',flush=True)
        finally:proc.stdin.close()
        if proc.wait():raise RuntimeError('FFmpeg failed')
    print(OUT/'spherical-geometry-ru.mp4',flush=True)

if __name__=='__main__':main()
