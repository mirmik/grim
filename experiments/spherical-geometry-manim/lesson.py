"""Native Manim scenes synchronized to the accepted v6 whole-scene narration."""
import json
import math
from pathlib import Path
import textwrap
import numpy as np
from manim import *
from tqdm import tqdm
import geometry as geo

ROOT=Path(__file__).resolve().parent
TIMELINE=json.loads((ROOT/'output/timeline.json').read_text())
BG='#0a111d'; INK='#ecf2fa'; MUTED='#99acc3'; GRID='#314a63'
TEAL='#53d8c5'; GOLD='#ffc768'; BLUE='#72aaff'; RED='#ed7f9d'
FONT='DejaVu Sans'
CAM_PHI=58*DEGREES; CAM_THETA=45*DEGREES
SCREEN_RIGHT=np.array([-math.sin(CAM_THETA),math.cos(CAM_THETA),0.])
SCREEN_UP=np.array([-math.cos(CAM_PHI)*math.cos(CAM_THETA),-math.cos(CAM_PHI)*math.sin(CAM_THETA),math.sin(CAM_PHI)])
CENTER=-3.05*SCREEN_RIGHT-.05*SCREEN_UP
RADIUS=2.23

def txt(s,size=27,color=INK,width=None):
    lines=s.split('\n')
    m=Text(s,font=FONT,font_size=size,color=color) if len(lines)==1 else VGroup(
        *[Text(line,font=FONT,font_size=size,color=color) for line in lines]
    ).arrange(DOWN,aligned_edge=LEFT,buff=.13)
    if width and m.width>width:m.scale_to_fit_width(width)
    return m

def para(s,size=27,width=5.55,color=INK):
    return txt('\n'.join(textwrap.wrap(s,width=round(width*7))),size,color,width)

def eq(s,size=43,color=INK,width=5.65):
    m=MathTypst(s,font_size=size,color=color)
    if m.width>width:m.scale_to_fit_width(width)
    return m

def at(m,x,y):
    return m.move_to(np.array([x,y,0.]),aligned_edge=UL)

def phase(s,t,a,b=None):
    if b is None:b=a
    left=s['cues'][a]['start'];right=s['cues'][b]['end']
    q=float(np.clip((t-left)/max(.001,right-left),0,1))
    return q*q*(3-2*q)

def world(p):return CENTER+RADIUS*np.asarray(p)

def morph(dst,a,b,u):
    for d,x,y in zip(dst.get_family(),a.get_family(),b.get_family()):
        d.interpolate(x,y,u)

def curve(points,color=TEAL,width=4):
    m=VMobject(stroke_color=color,stroke_width=width)
    m.set_points_smoothly(np.asarray(points));return m

def side(a,b,color=TEAL,end=1):
    return curve([world(geo.arc(a,b,u)*1.008) for u in np.linspace(0,max(.00001,end),45)],color)

def sphere(highlight=False):
    obj=Surface(lambda u,v:world([math.sin(u)*math.cos(v),math.sin(u)*math.sin(v),math.cos(u)]),
        u_range=[.001,PI-.001],v_range=[0,TAU],resolution=(14,28),
        checkerboard_colors=False,fill_color='#183f52',fill_opacity=.68,
        stroke_color='#50748a',stroke_width=.35)
    if highlight:
        for face in obj:
            p=(face.get_center()-CENTER)/RADIUS
            if p[2]>0 and p[0]>0 and p[1]>0:face.set_fill(TEAL,opacity=.76)
    return obj

def octant(phi=PI/2,color=TEAL):
    return Surface(lambda u,v:world(1.012*np.array([math.sin(u)*math.cos(v),math.sin(u)*math.sin(v),math.cos(u)])),
        u_range=[.001,PI/2],v_range=[0,phi],resolution=(10,10),
        checkerboard_colors=False,fill_color=color,fill_opacity=.34,stroke_width=0)

def route(phi=PI/2,progress=3,muted=False):
    vs=geo.vertices(phi);g=VGroup()
    for i,(a,b) in enumerate(zip(vs,vs[1:])):
        g.add(side(a,b,GRID))
        q=float(np.clip(progress-i,0,1))
        if q>1e-5 and not muted:g.add(side(a,b,[TEAL,GOLD,BLUE][i],q))
    return g

def moving_arrow(p,v,color=GOLD,length=.38):
    return Arrow3D(world(p*1.025),world(p*1.025+length*v),color=color,
        thickness=.025,height=.16,base_radius=.065,resolution=8)

def tangent(p):
    a=geo.unit(np.cross(p,[0,0,1])) if abs(p[2])<.95 else geo.A
    b=np.cross(p,a)
    return Polygon(*[world(p+.19*(x*a+y*b)) for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]],
        fill_color=BLUE,fill_opacity=.16,stroke_color=BLUE,stroke_opacity=.65,stroke_width=1)

def angles(phi=PI/2):
    vs=geo.vertices(phi)[:3];g=VGroup()
    for j,p in enumerate(vs):
        a=geo.unit(vs[(j+1)%3]-p*np.dot(p,vs[(j+1)%3]))
        b=geo.unit(vs[(j+2)%3]-p*np.dot(p,vs[(j+2)%3]))
        theta=math.acos(np.clip(np.dot(a,b),-1,1));b=geo.unit(b-a*np.dot(a,b))
        g.add(curve([world(p*1.02+.12*(math.cos(u)*a+math.sin(u)*b)) for u in np.linspace(0,theta,25)],INK,2.4))
    return g

class Lesson(ThreeDScene):
    def __init__(self,part=0,still_time=None,**kwargs):
        self.part=part;self.data=TIMELINE[part];self.still_time=still_time
        self.layout=[]
        super().__init__(**kwargs)

    def get_time_progression(self,run_time,description,n_iterations=None,override_skip_animations=False):
        # All intervals are integer frame counts. Floating arange(stop=seconds)
        # can include an extra endpoint; index frames explicitly instead.
        if self.renderer.skip_animations and not override_skip_animations:times=[run_time]
        else:times=np.arange(round(run_time*config.frame_rate))/config.frame_rate
        return tqdm(times,desc=description,total=n_iterations,disable=config.progress_bar=='none',leave=False)

    def fixed(self,*mobs):
        self.add_fixed_in_frame_mobjects(*mobs)
        return mobs[0] if len(mobs)==1 else VGroup(*mobs)

    def labels(self,phi=PI/2):
        vs=geo.vertices(phi)
        for p,label,offset in zip(vs,['N','A','Б'],[SCREEN_UP*.24,-SCREEN_RIGHT*.23-SCREEN_UP*.1,SCREEN_RIGHT*.23-SCREEN_UP*.1]):
            dot=Dot3D(world(p*1.012),radius=.04,color=INK,resolution=(4,8));self.add(dot)
            m=txt(label,24).move_to(world(p)+offset)
            self.add_fixed_orientation_mobjects(m)

    def globe(self,fill=False,labels=True,progress=3):
        self.add(sphere(highlight=fill))
        self.add(route(progress=progress))
        if labels:self.labels()

    def panel(self,title,items):
        g=VGroup(at(txt(title,21,TEAL,width=5.7),.6,2.15))
        body=VGroup()
        for kind,s,color in items:
            m=eq(s,color=color) if kind=='eq' else para(s,color=color)
            body.add(m)
        if len(body):
            body.arrange(DOWN,aligned_edge=LEFT,buff=.38)
            if body.height>3.8:body.scale_to_fit_height(3.8)
            at(body,.6,1.43);g.add(body)
            assert body.get_bottom()[1]>=-2.4
        return g

    def header(self):
        s=self.data
        self.fixed(at(txt(s['chapter'].upper(),18,TEAL,width=11.8),-6.6,3.8),
            at(txt(s['title'],34,INK,width=13.0),-6.6,3.32),
            at(txt(f'{self.part+1:02d} / {len(TIMELINE):02d}',17,MUTED),5.55,3.8),
            Line([-6.6,2.7,0],[6.6,2.7,0],color=GRID,stroke_width=1),
            at(txt('КРИВИЗНА ИЗНУТРИ',15,MUTED),-6.6,-3.65))

    def build(self):
        return getattr(self,'build_'+self.data['id'])()

    def construct(self):
        self.camera.background_color=BG
        self.set_camera_orientation(phi=CAM_PHI,theta=CAM_THETA,focal_distance=10000)
        self.header();self.dynamic=VGroup()
        self.update_geometry,self.panel_state=self.build()
        self.add(self.dynamic)
        self.current_panel=None;self.current_key=None;self.caption=None
        if self.still_time is not None:
            t=self.still_time;idx=self.cue_at(t)
            if self.update_geometry:self.update_geometry(t)
            self.set_panel(idx);self.set_caption(idx)
            self.wait(1/config.frame_rate)
            return
        fps=config.frame_rate;s=self.data
        cuts=sorted(set([round(s['start']*fps),round(s['end']*fps)]+[
            round(c[k]*fps) for c in s['cues'] for k in ('start','end')]))
        for a,b in zip(cuts,cuts[1:]):
            if b<=a:continue
            t=a/fps;idx=self.cue_at((a+.1)/fps)
            # A cue boundary may fall within half a frame of the selected time.
            nearest=next((i for i,c in enumerate(s['cues']) if round(c['start']*fps)==a),None)
            if nearest is not None:idx=nearest
            if self.update_geometry:self.update_geometry(t+.5/fps)
            moving=self.update_geometry is not None and self.moving_during(a/fps,b/fps)
            new_panel=self.set_panel(idx);self.set_caption(idx)
            frames=b-a;fade_frames=min(8,frames) if new_panel else 0
            if fade_frames:
                span=fade_frames/fps
                anim=[FadeIn(self.current_panel,shift=UP*.06)]
                if moving:
                    anim.append(UpdateFromAlphaFunc(self.dynamic,lambda m,u,t=t,span=span:self.update_geometry(t+u*span)))
                self.play(*anim,run_time=span,rate_func=linear)
                a+=fade_frames
            if b>a:
                if moving:
                    begin=a/fps;span=(b-a)/fps
                    self.play(UpdateFromAlphaFunc(self.dynamic,lambda m,u,begin=begin,span=span:self.update_geometry(begin+u*span)),run_time=span,rate_func=linear)
                else:self.wait((b-a)/fps)
        if self.update_geometry:self.update_geometry(s['end'])

    def moving_during(self,a,b):
        windows={
            'transport_fast':self.data.get('motion_sections',[]),
            'vary':[(0,4)],'number':[(3,4)],'local':[(1,2)],'add':[(0,0)],
            'principal':[(5,5)],'cylinder':[(2,3)],'boundary':[(0,1)],
            'global':[(4,4)],'summary':[(1,3)],
        }.get(self.data['id'],[])
        return any(b>self.data['cues'][i]['start'] and a<self.data['cues'][j]['end'] for i,j in windows)

    def cue_at(self,t):
        return next((i for i,c in enumerate(self.data['cues']) if c['start']<=t<c['end']),-1)

    def set_caption(self,idx):
        if self.caption is not None:
            self.remove_fixed_in_frame_mobjects(self.caption);self.remove(self.caption)
        self.caption=None
        if idx>=0:
            content='\n'.join(textwrap.wrap(self.data['cues'][idx]['text'],width=100))
            self.caption=txt(content,22,INK,width=12.8).move_to([0,-3.02,0])
            if self.caption.height>.87:self.caption.scale_to_fit_height(.87)
            self.fixed(self.caption)

    def set_panel(self,idx):
        if idx<0 and self.current_panel is not None:return False
        key,title,items=self.panel_state(max(0,idx))
        if key==self.current_key:return False
        if self.current_panel is not None:
            self.remove_fixed_in_frame_mobjects(self.current_panel);self.remove(self.current_panel)
        self.current_key=key;self.current_panel=self.panel(title,items);self.fixed(self.current_panel)
        return True

    def constant(self,title,items):return lambda i:(0,title,items)

    def build_setup(self):
        self.globe(progress=0)
        self.add(tangent(geo.N),moving_arrow(geo.N,geo.A,BLUE,.45),moving_arrow(geo.N,geo.A,GOLD,.34))
        return None,self.constant('ОПЫТ С НАПРАВЛЕНИЕМ',[
            ('text','Замкнутый путь на поверхности',INK),
            ('eq','"поворот" -> "углы" -> "кривизна"',TEAL)])

    def build_transport_fast(self):
        s=self.data;self.add(sphere(),route(progress=0));self.labels();self.add(moving_arrow(geo.N,geo.A,BLUE,.44))
        vs=geo.vertices();full=[side(a,b,col) for a,b,col in zip(vs,vs[1:],[TEAL,GOLD,BLUE])]
        traces=VGroup(*[m.copy() for m in full]);plane=tangent(geo.N)
        template=Arrow3D(ORIGIN,RIGHT*RADIUS*.38,color=GOLD,thickness=.025,height=.16,base_radius=.065,resolution=6)
        arrow=template.copy();self.dynamic.add(traces,plane,arrow)
        def update(t):
            pr=sum(phase(s,t,a,b) for a,b in s['motion_sections']);p,v=geo.transport(pr)
            for i,(trace,path) in enumerate(zip(traces,full)):
                q=float(np.clip(pr-i,0,1));trace.pointwise_become_partial(path,0,q)
            plane.become(tangent(p))
            matrix=np.column_stack([v,np.cross(p,v),p])
            arrow.become(template).apply_matrix(matrix).shift(world(p*1.025))
        states=[('N → A',[('text','Вдоль меридиана',INK)]),('A → Б',[('text','Движение — на восток. Направление стрелки — на юг.',INK)]),('Б → N',[('text','Точка возвращается к полюсу. Стрелка смотрит назад.',INK)])]
        def panel(i):
            n=0 if i<2 else 1 if i<4 else 2;title,items=states[n];return n,title,items
        update(s['start']);return update,panel

    def comparison(self):
        origin=np.array([-5.65,-1.8,0.])
        g=VGroup(Arrow(origin,origin+RIGHT*.95,buff=0,color=BLUE,stroke_width=4),
                 Arrow(origin,origin+UP*.95,buff=0,color=GOLD,stroke_width=4),
                 at(txt('90°',24,GOLD),-5.32,-1.08))
        self.fixed(g)

    def build_excess(self):
        self.globe(fill=True);self.add(moving_arrow(geo.N,geo.A,BLUE,.44),moving_arrow(*geo.transport(3)));self.comparison()
        marks=angles();self.dynamic.add(marks)
        def update(t):marks.set_opacity(float(t>=self.data['cues'][2]['start']))
        def panel(i):
            if i==0:return 0,'СРАВНИВАЕМ НАПРАВЛЕНИЯ',[('eq','Delta theta = 90 degree',GOLD)]
            if i==1:return 1,'ГЕОДЕЗИЧЕСКИЕ',[('text','Меридианы и экватор — аналоги прямых на сфере.',INK)]
            items=[('text','α, β, γ — внутренние углы',MUTED),('eq','alpha + beta + gamma = 270 degree',INK)]
            if i>=3:items.append(('eq','270 degree - 180 degree = 90 degree',GOLD))
            if i>=4:items.append(('eq','epsilon = alpha + beta + gamma - pi',TEAL))
            return min(i,4),'УГЛОВОЙ ИЗБЫТОК',items
        return update,panel

    def build_area(self):
        self.globe(fill=True)
        def panel(i):
            items=[('text','A — площадь треугольника; R — радиус сферы',MUTED)]
            if i>=1:items.append(('eq','A = (4 pi R^2)/8 = (pi R^2)/2',INK))
            if i>=3:items.append(('eq','A/R^2 = pi/2 = 90 degree',GOLD))
            return min(i,3),'ОДНА ВОСЬМАЯ СФЕРЫ',items
        return None,panel

    def build_vary(self):
        s=self.data;base=sphere();faces=[];static=VGroup();changing=VGroup()
        for face in base:
            p=(face.get_center()-CENTER)/RADIUS
            if p[2]>0 and p[0]>0 and p[1]>0:
                faces.append((face,math.atan2(p[1],p[0])));changing.add(face)
            else:static.add(face)
        self.add(static);lines=VGroup();self.dynamic.add(changing,lines)
        def update(t):
            phi=PI/2-PI/3*phase(s,t,0,4)
            for face,lon in faces:
                strength=float(np.clip((phi-lon)/(PI/14)+.5,0,1))
                face.set_fill(interpolate_color(ManimColor('#183f52'),ManimColor(TEAL),strength),opacity=.68+.08*strength)
            lines.become(VGroup(route(phi),angles(phi)))
        def panel(i):
            items=[('text','φ — угол между меридианами',MUTED),('eq','epsilon = phi',GOLD)]
            if i>=3:items.append(('eq','A = R^2 phi = R^2 epsilon',TEAL))
            if i>=4:items.append(('text','Угол, площадь и избыток уменьшаются втрое.',INK))
            return min(i,4),'МЕНЯЕМ ПЛОЩАДЬ',items
        update(s['start']);return update,panel

    def build_number(self):
        self.set_camera_orientation(phi=0,theta=-PI/2)
        axes=Axes(x_range=[10,20,5],y_range=[0,.7,.2],x_length=5.4,y_length=4.1,
            axis_config={'include_tip':False,'stroke_color':GRID,'stroke_width':2}).move_to([-3.35,-.15,0])
        graph=axes.plot(lambda r:180/PI/r**2,x_range=[10,20],color=TEAL)
        self.add(axes,graph,at(txt('Избыток, градусы',22,MUTED),-6.1,2.25),at(txt('Радиус, км',19,MUTED),-2.25,-1.8))
        for x in (10,15,20):self.add(txt(str(x),20,MUTED).next_to(axes.c2p(x,0),DOWN,buff=.12))
        for y in (.2,.4,.6):self.add(txt(str(y),18,MUTED).next_to(axes.c2p(10,y),LEFT,buff=.12))
        def update(t):
            r=10+10*phase(self.data,t,3,4);p=axes.c2p(r,180/PI/r**2)
            self.dynamic.become(VGroup(Dot(p,color=GOLD,radius=.075),DashedLine(axes.c2p(r,0),p,color=GOLD,stroke_width=1.5)))
        def panel(i):
            items=[('eq','epsilon = A/R^2',TEAL)]
            if i>=1:items.append(('eq','A = 1 thin "км"^2',INK))
            if i>=2:items.append(('eq','R=10: quad epsilon approx 0.57 degree',GOLD))
            if i>=3:items.append(('eq','R=20: quad epsilon approx 0.14 degree',BLUE))
            return min(i,3),'ОДНА ПЛОЩАДЬ, ДВА РАДИУСА',items
        update(self.data['start']);return update,panel

    def build_local(self):
        self.add(sphere());base=geo.unit([1,1,1]);a=geo.unit(np.cross(base,[0,0,1]));b=np.cross(base,a)
        def update(t):
            size=.7-.59*phase(self.data,t,1,2)
            vs=[geo.unit(base+size*(math.cos(u)*a+math.sin(u)*b)) for u in (PI/2,PI/2+TAU/3,PI/2+2*TAU/3)]
            self.dynamic.become(VGroup(*[side(p,q,TEAL) for p,q in zip(vs,vs[1:]+vs[:1])],Dot3D(world(base*1.02),color=GOLD,radius=.045,resolution=(4,8))))
        def panel(i):
            items=[('text','Избыток на единицу площади',INK)]
            if i>=2:items=[('text','K — гауссова кривизна в точке',MUTED),('eq','K = lim_(A -> 0) epsilon/A',TEAL)]
            if i>=3:items.append(('eq','"сфера:" quad K = 1/R^2',GOLD))
            return min(i,3),'ИЗМЕРЯЕМ В ОДНОЙ ТОЧКЕ',items
        update(self.data['start']);return update,panel

    def build_add(self):
        self.globe(fill=True);mid=geo.unit(geo.A+geo.vertices()[2])
        def update(t):self.dynamic.become(VGroup(side(geo.N,mid,RED,phase(self.data,t,0,0))))
        def panel(i):
            items=[('text','Индексы 1 и 2 обозначают две части после разреза.',MUTED)]
            if i>=2:items.append(('eq','alpha_1+alpha_2=alpha',INK))
            if i>=3:items.append(('eq','epsilon_1+epsilon_2=epsilon',GOLD))
            if i>=4:items.append(('eq','A_1+A_2=A',TEAL))
            return min(i,4),'РАЗРЕЗАЕМ НА ДВА ТРЕУГОЛЬНИКА',items
        update(self.data['start']);return update,panel

    def ellipsoid(self,n=12,heat=False,axes=None):
        axes=np.array([1.45,1,.78]) if axes is None else np.array(axes)
        surface=Surface(lambda u,v:world(np.array([math.cos(u)*math.cos(v),math.cos(u)*math.sin(v),math.sin(u)])*axes*.8),
            u_range=[-PI/2+.001,PI/2-.001],v_range=[0,TAU],resolution=(n,2*n),
            checkerboard_colors=False,fill_color=TEAL,fill_opacity=.86,stroke_color=GRID,stroke_width=.55)
        if heat:
            for face in surface:
                p=(face.get_center()-CENTER)/(RADIUS*.8)
                val=np.clip((geo.ellipsoid_curvature(p)-.25)/2.2,0,1)
                face.set_fill(interpolate_color(ManimColor('#247a87'),ManimColor(GOLD),val))
        return surface

    def build_integral(self):
        self.add(self.ellipsoid(16,True))
        def panel(i):
            items=[('text','Участки с разной кривизной',INK)]
            if i>=2:items=[('text','ΔAᵢ — площадь участка; Kᵢ — его кривизна',MUTED),('eq','sum_i K_i Delta A_i',GOLD)]
            if i>=4:items.append(('eq','sum_i K_i Delta A_i -> integral K dif A',TEAL))
            return 0 if i<2 else 2 if i<4 else 4,'СУММИРУЕМ МЕСТНЫЕ ВКЛАДЫ',items
        return None,panel

    def build_bonnet(self):
        self.globe(fill=True);m=txt('T',38,TEAL).move_to(world(geo.unit([1,1,.65])));self.add_fixed_orientation_mobjects(m)
        def panel(i):
            items=[('text','T — область без дыр с геодезическими сторонами',MUTED)]
            if i>=1:items.append(('eq','epsilon = integral_T K dif A',TEAL))
            if i>=3:items.append(('text','dA — элемент площади',MUTED))
            if i>=4:items.append(('text','Углы границы измеряют кривизну внутри.',INK))
            return min(i,4),'ТЕОРЕМА ГАУССА — БОННЕ',items
        return None,panel

    def patch(self,kind='dome'):
        def f(x,y):return np.array([x,y,-.4*(x*x+y*y) if kind=='dome' else .4*(x*x-y*y)])
        surface=Surface(lambda u,v:world(f(u,v)*.9),u_range=[-1,1],v_range=[-1,1],resolution=(16,16),
            checkerboard_colors=False,fill_color=TEAL if kind=='dome' else RED,fill_opacity=.7,stroke_width=.45,stroke_color=GRID)
        c1=curve([world(f(u,0)*.9) for u in np.linspace(-1,1,61)],GOLD,5)
        c2=curve([world(f(0,u)*.9) for u in np.linspace(-1,1,61)],BLUE,5)
        return VGroup(surface,c1,c2)

    def build_principal(self):
        dome=self.patch();saddle=self.patch('saddle');self.dynamic.add(dome.copy())
        def update(t):
            u=phase(self.data,t,5,5)
            morph(self.dynamic[0],dome,saddle,u)
        def panel(i):
            items=[('text','Два главных нормальных сечения',INK)]
            if i>=1:items.append(('eq','k_1, quad k_2',GOLD))
            if i>=3:items.append(('eq','K=k_1 k_2',TEAL))
            if i>=4:items.append(('eq','K>0' if i==4 else 'K<0',GOLD if i==4 else RED))
            return min(i,5),'ГЛАВНЫЕ КРИВИЗНЫ',items
        return update,panel

    def build_saddle(self):
        self.add(self.patch('saddle'))
        def panel(i):
            if i==0:return 0,'ЗНАК КРИВИЗНЫ',[('eq','"сфера:" quad K>0',TEAL),('eq','alpha+beta+gamma>pi',GOLD)]
            items=[('eq','"седло:" quad K<0',RED),('eq','alpha+beta+gamma<pi',GOLD)]
            if i>=3:items.append(('text','Отрицательный избыток — недостаток углов.',INK))
            return min(i,3),'НА СЕДЛЕ УГЛОВ НЕДОСТАЁТ',items
        return None,panel

    def bent_sheet(self,bend):
        f=lambda x,y:world(geo.cylinder(x,y,bend)*.86)
        surface=Surface(f,u_range=[-1.2,1.2],v_range=[-1.2,1.2],resolution=(16,12),
            checkerboard_colors=False,fill_color=TEAL,fill_opacity=.76,stroke_width=.65,stroke_color=GRID)
        vertices=[(-.9,-.8),(.9,-.8),(-.15,.9)]
        sides=[]
        for a,b in zip(vertices,vertices[1:]+vertices[:1]):
            sides.append(curve([f(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t)+.025*np.array([0,0,1]) for t in np.linspace(0,1,40)],GOLD,5))
        return VGroup(surface,*sides)

    def build_cylinder(self):
        self.dynamic.add(self.bent_sheet(0))
        scale=RADIUS*.86
        originals=[(m,(m.get_points().copy()-CENTER)/scale) for m in self.dynamic.family_members_with_points()]
        def update(t):
            bend=1.25*phase(self.data,t,2,3)
            for m,points in originals:
                result=points.copy()
                if bend>1e-8:
                    result[:,0]=np.sin(bend*points[:,0])/bend
                    result[:,2]+=(1-np.cos(bend*points[:,0]))/bend
                m.set_points(CENTER+scale*result)
        def panel(i):
            items=[('text','R — радиус цилиндра',MUTED),('eq','k_1=1/R, quad k_2=0',INK)]
            if i>=1:items.append(('eq','K=k_1 k_2=0',TEAL))
            if i>=3:items.append(('eq','alpha+beta+gamma=pi',GOLD))
            if i>=4:items.append(('text','Длины и внутренние углы сохраняются.',INK))
            return min(i,4),'СВОРАЧИВАЕМ ЛИСТ',items
        update(self.data['start']);return update,panel

    def build_boundary(self):
        self.set_camera_orientation(phi=0,theta=-PI/2)
        center=np.array([-3.25,-.1,0]);r=1.82
        self.add(Circle(radius=r,color=TEAL,stroke_width=4).move_to(center),txt('K = 0',36).move_to(center))
        def update(t):
            a=TAU*phase(self.data,t,0,1);p=center+r*np.array([math.cos(a),math.sin(a),0]);v=np.array([-math.sin(a),math.cos(a),0])
            self.dynamic.become(VGroup(Dot(p,color=GOLD),Arrow(p,p+v*.85,buff=0,color=GOLD,stroke_width=5)))
        def panel(i):
            items=[('eq','"поворот касательной" = 360 degree',GOLD)]
            if i>=3:items=[('text','kɢ — геодезическая кривизна границы',MUTED),('eq','integral.cont k_g dif s = 2 pi',GOLD)]
            if i>=4:items.append(('eq','"геодезическая:" quad k_g=0',TEAL))
            return 0 if i<3 else min(i,4),'ВКЛАД САМОЙ ГРАНИЦЫ',items
        update(self.data['start']);return update,panel

    def build_turns(self):
        self.globe(fill=True);self.add(angles())
        def panel(i):
            items=[('eq','"поворот в вершине" = pi-alpha',INK)]
            if i>=2:items=[('eq','3 times 90 degree = 270 degree',INK)]
            if i>=3:items.append(('eq','270 degree + 90 degree = 360 degree',GOLD))
            if i>=5:items=[('eq','alpha+beta+gamma-pi',GOLD),('eq','= integral_T K dif A',TEAL)]
            return min(i,5),'ГДЕ ОСТАЛЬНЫЕ 90°?',items
        return None,panel

    def build_global(self):
        a=self.ellipsoid(14,False,axes=[1.15,1.15,1.15]);b=self.ellipsoid(14,False)
        self.dynamic.add(a.copy())
        def update(t):morph(self.dynamic[0],a,b,phase(self.data,t,4,4))
        def panel(i):
            items=[('text','S — замкнутая поверхность без края',MUTED)]
            if i>=1:items.append(('eq','integral_S K dif A = 2 pi chi(S)',TEAL))
            if i>=2:items.append(('text','χ = вершины − рёбра + грани',INK))
            if i>=3:items.append(('eq','chi=2 quad -> quad integral_S K dif A=4 pi',GOLD))
            return min(i,3),'ОТ ГЕОМЕТРИИ К ТОПОЛОГИИ',items
        return update,panel

    def build_torus(self):
        def f(u,v):return world(.77*np.array([(1+.42*math.cos(v))*math.cos(u),(1+.42*math.cos(v))*math.sin(u),.42*math.sin(v)]))
        torus=Surface(f,u_range=[0,TAU],v_range=[0,TAU],resolution=(32,18),checkerboard_colors=False,
            fill_opacity=.95,stroke_color=GRID,stroke_width=.4)
        for face in torus:
            p=(face.get_center()-CENTER)/(RADIUS*.77);outer=np.linalg.norm(p[:2])>1
            face.set_fill(TEAL if outer else RED)
        self.add(torus)
        def panel(i):
            items=[('eq','chi=0',INK)]
            if i>=1:items.append(('eq','integral_S K dif A=0',GOLD))
            if i>=2:items.append(('text','Снаружи K > 0; у отверстия K < 0',MUTED))
            if i>=4:items.append(('text','Вклады компенсируются. Сам тор не плоский.',INK))
            return min(i,4),'ПОЛОЖИТЕЛЬНОЕ И ОТРИЦАТЕЛЬНОЕ',items
        return None,panel

    def build_summary(self):
        self.set_camera_orientation(phi=0,theta=-PI/2)
        cards=VGroup()
        items=[('ТОЧКА','K=lim_(A -> 0) epsilon/A','Местная кривизна',TEAL),
            ('ОБЛАСТЬ','epsilon=integral_T K dif A','Углы геодезического треугольника',GOLD),
            ('ПОВЕРХНОСТЬ','integral_S K dif A=2 pi chi','Связь с топологией',BLUE)]
        for j,(title,formula,note,color) in enumerate(items):
            x=-4.5+j*4.5
            card=VGroup(txt(title,22,color).move_to([x,1.55,0]),eq(formula,35,color,width=4).move_to([x,.2,0]),
                para(note,24,3.8,MUTED).move_to([x,-1.3,0]))
            cards.add(card)
        self.add(cards)
        def update(t):
            for j,card in enumerate(cards):
                cue=[1,2,3][j];card.set_opacity(.2+.8*phase(self.data,t,cue,cue))
        self.dynamic.add(cards);self.remove(cards)
        # Summary uses the whole frame instead of the right-hand formula column.
        self.panel_state=lambda i:(0,'',[])
        return update,lambda i:(0,'',[])
