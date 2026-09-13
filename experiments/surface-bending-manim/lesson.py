"""A chapter companion: native Manim geometry with uninterrupted VoxCPM2 scenes."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import numpy as np
from manim import *
import geometry as geo

ROOT=Path(__file__).resolve().parent
TIMELINE=json.loads((ROOT/'output/timeline.json').read_text())
# Reuse the tested frame scheduler, captions and typography, not previous footage.
spec=importlib.util.spec_from_file_location('chapter_scene_base',ROOT.parent/'spherical-geometry-manim/lesson.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.TIMELINE=TIMELINE
txt,para,eq,at,phase,curve=base.txt,base.para,base.eq,base.at,base.phase,base.curve
BG,INK,MUTED,GRID,TEAL,GOLD,BLUE,RED=base.BG,base.INK,base.MUTED,base.GRID,base.TEAL,base.GOLD,base.BLUE,base.RED
PHI=58*DEGREES;THETA=45*DEGREES
SR=np.array([-np.sin(THETA),np.cos(THETA),0.])
SU=np.array([-np.cos(PHI)*np.cos(THETA),-np.cos(PHI)*np.sin(THETA),np.sin(PHI)])
DEFAULT_C=-3.15*SR-.35*SU
C=DEFAULT_C.copy()
SCALE=1.8
def world(p):return C+SCALE*np.asarray(p)

def arrow(color=GOLD):
    m=Arrow3D(ORIGIN,RIGHT,color=color,thickness=.025,height=.14,base_radius=.065,resolution=6)
    # Arrow3D's resolution only controls the shaft; its default cone has 1024
    # faces. Eight angular faces suffice at this size and keep Cairo fast.
    m.remove(m.cone)
    m.cone=Cone(direction=RIGHT,base_radius=.065,height=.14,resolution=(1,8),
                fill_color=color,fill_opacity=1,stroke_width=0).shift(RIGHT)
    m.add(m.cone)
    m.template=[(q,q.get_points().copy()) for q in m.family_members_with_points()]
    return m

def put_arrow(m,p,v):
    v=np.asarray(v);length=np.linalg.norm(v)
    if length<1e-8:m.set_opacity(0);return
    a=v/length;ref=OUT if abs(a[2])<.9 else RIGHT
    b=np.cross(ref,a);b/=np.linalg.norm(b);d=np.cross(a,b)
    mat=np.column_stack([v,b,d])
    for part,points in m.template:part.set_points(points@mat.T+np.asarray(p))
    m.set_opacity(1)

def patch(a=1,b=3):
    return Surface(lambda u,v:world(geo.graph(u,v,a,b)),u_range=[-.8,.8],v_range=[-.8,.8],
        resolution=(16,16),checkerboard_colors=False,fill_color=TEAL,fill_opacity=.52,
        stroke_width=.6,stroke_color='#427478')

def section_curve(theta,a=1,b=3,color=GOLD):
    return curve([world(geo.section(theta,t,a,b)+np.array([0,0,.006])) for t in np.linspace(-.8,.8,61)],color,5)

class Lesson(base.Lesson):
    def __init__(self,*args,**kwargs):
        global C
        C=DEFAULT_C.copy()
        super().__init__(*args,**kwargs)

    def set_caption(self,idx):
        # Captions are optional WebVTT tracks in the book player.
        # Keep the animation clear instead of burning a second copy into the frame.
        pass

    def header(self):
        s=self.data
        self.fixed(at(txt(s['chapter'].upper(),18,TEAL,width=11.8),-6.6,3.8),
            at(txt(s['title'],34,INK,width=13),-6.6,3.32),
            at(txt(f'{self.part+1:02d} / {len(TIMELINE):02d}',17,MUTED),5.55,3.8),
            Line([-6.6,2.7,0],[6.6,2.7,0],color=GRID,stroke_width=1),
            at(txt('GRIM · КАК ПОВЕРХНОСТЬ ИЗГИБАЕТСЯ',15,MUTED),-6.6,-3.65))

    def moving_during(self,a,b):
        windows={
            'normals':[(0,3)],'construction':[(3,3)],'derivative':[(0,3)],
            'operator':[(2,2)],'second':[(4,4)],'section':[(1,1),(3,3)],
            'principal':[(0,1),(4,5)],'saddle':[(2,2)],'cylinder':[(4,4)],'sphere':[(3,3)]
        }.get(self.data['id'],[])
        return any(b>self.data['cues'][i]['start'] and a<self.data['cues'][j]['end'] for i,j in windows)

    def flat(self):self.set_camera_orientation(phi=0,theta=-PI/2)

    def mark_origin(self):
        self.add(Dot3D(world([0,0,.01]),radius=.045,color=INK,resolution=(4,8)))
        m=txt('p',23,INK).move_to(world([0,0,0])-.24*SU)
        self.add_fixed_orientation_mobjects(m)

    def label(self,text,p,color=INK):
        m=txt(text,25,color).move_to(p);self.add_fixed_orientation_mobjects(m);return m

    def build_normals(self):
        s=self.data
        sheet=Surface(lambda u,v:world([u,v,0]),u_range=[-1.15,1.15],v_range=[-1,1],resolution=(18,12),
            checkerboard_colors=False,fill_color=TEAL,fill_opacity=.6,stroke_color=GRID,stroke_width=.7)
        originals=[(m,(m.get_points().copy()-C)/SCALE) for m in sheet.family_members_with_points()]
        n=arrow();point=Dot3D(world([0,0,0]),radius=.05,color=INK,resolution=(4,8))
        trace=curve([world([x,0,.01]) for x in np.linspace(-1,1,60)],BLUE,4)
        self.dynamic.add(sheet,trace,point,n)
        def update(t):
            bend=1.25*phase(s,t,2,2)
            # First half of cylinder sentence turns across its axis; next sentence moves along it.
            q=phase(s,t,0,1);x=-.85+1.7*q
            if t>=s['cues'][2]['start']:x=.85-1.7*phase(s,t,2,2)
            y=-.75+1.5*phase(s,t,3,3) if t>=s['cues'][3]['start'] else 0
            for m,points in originals:
                result=points.copy()
                if bend>1e-8:
                    result[:,0]=np.sin(bend*points[:,0])/bend
                    result[:,2]=(np.cos(bend*points[:,0])-1)/bend
                m.set_points(C+SCALE*result)
            trace.become(curve([world(geo.sheet(u,0,bend)+np.array([0,0,.009])) for u in np.linspace(-1,1,60)],BLUE,4))
            p=world(geo.sheet(x,y,bend));point.move_to(p);put_arrow(n,p,SCALE*.6*geo.sheet_normal(x,bend))
        def panel(i):
            if i<2:return 0,'ПЛОСКОСТЬ',[('text','Нормаль n перпендикулярна поверхности',INK),('eq','norm(n)=1',GOLD),('text','Направление постоянно',BLUE)]
            return 2,'ЦИЛИНДР',[('text','Поперёк оси — поворот',GOLD),('text','Вдоль оси — без поворота',BLUE),('text','Изгиб зависит от направления',INK)]
        return update,panel

    def build_construction(self):
        self.add(patch());self.mark_origin()
        for v,text,color in [(RIGHT,'rᵤ',BLUE),(UP,'rᵥ',TEAL),(OUT,'n',GOLD)]:
            a=arrow(color);put_arrow(a,world([0,0,.012]),SCALE*.8*v);self.add(a)
            self.label(text,world(.95*v),color)
        opposite=arrow(RED);self.dynamic.add(opposite)
        def update(t):
            q=phase(self.data,t,3,3);put_arrow(opposite,world([0,0,0]),-OUT*SCALE*.8)
            opposite.set_opacity(q*.7)
        def panel(i):
            if i==0:return 0,'ДВЕ КООРДИНАТЫ',[('eq','r(u,v)',INK)]
            if i==1:return 1,'КАСАТЕЛЬНАЯ ПЛОСКОСТЬ',[('eq','r_u, quad r_v',BLUE),('text','Два независимых касательных вектора',INK)]
            return 2,'ЕДИНИЧНАЯ НОРМАЛЬ',[('eq','n = (r_u times r_v)/norm(r_u times r_v)',GOLD),('eq','norm(n)=1',INK),('text','Два выбора: n и −n',MUTED)]
        return update,panel

    def build_derivative(self):
        self.flat();center=np.array([-3.2,-.05,0]);radius=1.75
        self.add(Circle(radius=radius,color=GRID,stroke_width=2).move_to(center),Dot(center,color=MUTED))
        self.add(txt('Единичная сфера направлений',22,MUTED,width=5.6).move_to([-3.2,-2.28,0]))
        n=Arrow(center,center+RIGHT*radius,buff=0,color=GOLD);dn=n.copy().set_color(BLUE)
        end=Dot(color=INK);trail=VMobject();tangent=Line(color=GRID)
        self.dynamic.add(n,trail,tangent,dn,end)
        def update(t):
            a=.22+1.28*phase(self.data,t,0,3);v=np.array([np.cos(a),np.sin(a),0]);w=np.array([-np.sin(a),np.cos(a),0]);p=center+radius*v
            n.become(Arrow(center,p,buff=0,color=GOLD,stroke_width=6))
            dn.become(Arrow(p,p+1.03*w,buff=0,color=BLUE,stroke_width=6))
            tangent.put_start_and_end_on(p-1.1*w,p+1.35*w);end.move_to(p)
            trail.become(Arc(radius=radius,start_angle=.22,angle=max(.001,a-.22),color=TEAL,stroke_width=5).shift(center))
        def panel(i):
            if i<2:return 0,'ОТОБРАЖЕНИЕ ГАУССА',[('eq','p -> n(p)',GOLD),('text','Все стрелки перенесены в общее начало',INK)]
            if i<4:return 2,'СКОРОСТЬ ИЗМЕНЕНИЯ',[('eq','w -> dif n_p (w)',BLUE),('text','w — скорость на поверхности',MUTED),('text','dnₚ(w) — скорость конца нормали',INK)]
            return 4,'ПОСТОЯННАЯ ДЛИНА',[('eq','n dot n = 1',GOLD),('eq','n dot dif n_p (w)=0',BLUE),('eq','dif n_p (w) in T_p S',INK)]
        return update,panel

    def build_operator(self):
        self.flat();o=np.array([-3.35,-.4,0]);theta=PI/9;w=np.array([np.cos(theta),np.sin(theta),0])*.86
        self.add(Line(o+LEFT*2.2,o+RIGHT*2.2,color=GRID),Line(o+DOWN*1.5,o+UP*2.6,color=GRID),Dot(o,color=INK))
        self.add(txt('Касательная плоскость',22,MUTED).move_to([-3.2,-2.3,0]))
        input=Arrow(o,o+w,buff=0,color=BLUE);output=input.copy().set_color(GOLD)
        label_w=txt('w',28,BLUE);label_sw=txt('Sw',28,GOLD)
        self.dynamic.add(input,output,label_w,label_sw)
        def update(t):
            scale=1+phase(self.data,t,2,2)
            input.become(Arrow(o,o+scale*w,buff=0,color=BLUE,stroke_width=6))
            output.become(Arrow(o,o+scale*w*np.array([1,3,1]),buff=0,color=GOLD,stroke_width=6))
            label_w.move_to(o+scale*w+np.array([.25,-.12,0]))
            label_sw.move_to(o+scale*w*np.array([1,3,1])+np.array([.28,.12,0]))
        def panel(i):
            items=[('eq','S_p w = -dif n_p (w)',GOLD),('eq','S_p: T_p S -> T_p S',INK)]
            if i>=2:items.append(('eq','S_p (2w) = 2 S_p w',BLUE))
            if i>=3:items.append(('text','На выходе — вектор',MUTED))
            return min(i,3),'ОПЕРАТОР ФОРМЫ',items
        return update,panel

    def build_second(self):
        self.flat();o=np.array([-3.15,-.3,0]);theta=PI/4;w=np.array([np.cos(theta),np.sin(theta),0])*.7
        self.add(Line(o+LEFT*2.15,o+RIGHT*2.15,color=GRID),Line(o+DOWN*1.2,o+UP*2.4,color=GRID))
        a=Arrow(o,o+w,buff=0,color=BLUE);b=a.copy().set_color(GOLD)
        self.dynamic.add(a,b)
        self.add(txt('w',27,BLUE).move_to([-1.8,.18,0]),txt('Sw',27,GOLD).move_to([-2.15,2.1,0]),
            txt('Вектор → скалярное произведение → число',19,MUTED,width=5.8).move_to([-3.15,-2.25,0]))
        def update(t):
            scale=1+.32*phase(self.data,t,4,4)
            a.become(Arrow(o,o+scale*w,buff=0,color=BLUE,stroke_width=6))
            b.become(Arrow(o,o+scale*w*np.array([1,3,1]),buff=0,color=GOLD,stroke_width=6))
        def panel(i):
            if i<3:return 0,'ВТОРАЯ ФУНДАМЕНТАЛЬНАЯ ФОРМА',[('eq','I(w,z)=w dot z',MUTED),('eq','"II"(w,z)=I(S w,z)',GOLD),('text','I и II принимают два вектора и возвращают число',INK)]
            items=[('eq','k_n (w)=("II"(w,w))/(I(w,w))',TEAL),('text','I(w,w) — квадрат длины w',MUTED)]
            if i>=4:items.append(('eq','k_n (2w)=k_n (w)',BLUE))
            if i>=5:items.append(('eq','norm(w)=1 => k_n="II"(w,w)',INK))
            return min(i,5),'КРИВИЗНА НАПРАВЛЕНИЯ',items
        return update,panel

    def section_setup(self,principals=False):
        global C
        # Keep every plane in the 0..90° sweep visible; a 45° camera would
        # look edge-on at the final 45° example and hide the very curve it explains.
        theta=-35*DEGREES
        right=np.array([-np.sin(theta),np.cos(theta),0.])
        up=np.array([-np.cos(PHI)*np.cos(theta),-np.cos(PHI)*np.sin(theta),np.sin(PHI)])
        C=-3.15*right-.35*up
        self.set_camera_orientation(phi=PHI,theta=theta)
        self.add(patch());self.mark_origin()
        normal=arrow(GOLD);put_arrow(normal,world([0,0,0]),OUT*1.75);self.add(normal)
        self.label('n',world([0,0,1.1]),GOLD)
        if principals:self.add(section_curve(0,color=BLUE),section_curve(PI/2,color=RED))
        plane=Polygon(*[world([x,0,z]) for x,z in [(-.82,-.18),(.82,-.18),(.82,1.3),(-.82,1.3)]],fill_color=BLUE,fill_opacity=.15,stroke_color=BLUE,stroke_width=1)
        cut=section_curve(0);w=arrow(TEAL);self.dynamic.add(plane,cut,w)
        def rotate(theta,opacity=1):
            direction=np.array([np.cos(theta),np.sin(theta),0])
            plane.become(Polygon(*[world(x*direction+z*OUT) for x,z in [(-.82,-.18),(.82,-.18),(.82,1.3),(-.82,1.3)]],fill_color=BLUE,fill_opacity=.13*opacity,stroke_color=BLUE,stroke_opacity=.7*opacity,stroke_width=1))
            cut.become(section_curve(theta));cut.set_stroke(opacity=opacity)
            put_arrow(w,world([0,0,.014]),SCALE*.7*direction)
        return rotate

    def build_section(self):
        rotate=self.section_setup();s=self.data
        def update(t):rotate(PI/2*phase(s,t,3,3),phase(s,t,1,1))
        def panel(i):
            if i<2:return 0,'НОРМАЛЬНОЕ СЕЧЕНИЕ',[('text','Плоскость содержит w и n',BLUE),('text','Жёлтая кривая — пересечение с поверхностью',GOLD)]
            return 2,'ОДНА ТОЧКА, РАЗНЫЕ НАПРАВЛЕНИЯ',[('eq','k_n (w)',GOLD),('text','Кривизна плоского сечения в точке p',INK),('text','Знак — относительно нормали n',MUTED)]
        return update,panel

    def build_principal(self):
        rotate=self.section_setup(True);s=self.data
        def update(t):
            theta=PI/2*phase(s,t,0,1)
            if t>=s['cues'][4]['start']:theta=PI/2-PI/4*phase(s,t,4,4)
            rotate(theta)
        def panel(i):
            if i<2:return 0,'КРАЙНИЕ ЗНАЧЕНИЯ',[('eq','k_1=1, quad k_2=3',TEAL),('text','Синее сечение — пологое',BLUE),('text','Розовое сечение — крутое',RED)]
            if i<4:return 2,'ГЛАВНЫЕ НАПРАВЛЕНИЯ',[('eq','e_1 perp e_2',INK),('eq','S e_1=k_1 e_1',BLUE),('eq','S e_2=k_2 e_2',RED)]
            items=[('eq','k_n=k_1 cos^2 theta + k_2 sin^2 theta',GOLD),('text','θ — угол с первым главным направлением',MUTED)]
            if i==5:items.extend([('eq','theta=45 degree',BLUE),('eq','k_n=1/2+3/2=2',TEAL)])
            return i,'ФОРМУЛА ЭЙЛЕРА',items
        return update,panel

    def build_calculation(self):
        self.add(patch(),section_curve(0,color=BLUE),section_curve(PI/2,color=RED));self.mark_origin()
        for v,label,color in [(RIGHT,'rᵤ',BLUE),(UP,'rᵥ',RED),(OUT,'n',GOLD)]:
            a=arrow(color);put_arrow(a,world([0,0,.01]),SCALE*.65*v);self.add(a);self.label(label,world(.85*v),color)
        def panel(i):
            if i<2:return 0,'КВАДРАТИЧНАЯ ПОВЕРХНОСТЬ',[('eq','r(u,v)=(u,v,(u^2+3v^2)/2)',INK),('eq','p=(0,0,0), quad n=(0,0,1)',GOLD)]
            if i==2:return 2,'МЕТРИКА В НАЧАЛЕ КООРДИНАТ',[('eq','g=mat(1,0;0,1)',BLUE)]
            if i<5:
                items=[('text','b — матрица второй формы',MUTED),('eq','b=mat(1,0;0,3)',GOLD),('eq','S=g^(-1)b=mat(1,0;0,3)',INK)]
                if i==4:items.append(('eq','k_1=1, quad k_2=3',TEAL))
                return i,'НОРМАЛЬНЫЕ КОМПОНЕНТЫ ВТОРЫХ ПРОИЗВОДНЫХ',items
            return 5,'В ПРОИЗВОЛЬНЫХ КООРДИНАТАХ',[('eq','S=g^(-1)b',GOLD),('text','Собственные значения ищем у g⁻¹b',INK),('text','Одна матрица b ещё не задаёт главные кривизны',MUTED)]
        return None,panel

    def build_saddle(self):
        shape=patch();initial=[(m,(m.get_points().copy()-C)/SCALE) for m in shape.family_members_with_points()]
        c1=section_curve(0,color=BLUE);c2=section_curve(PI/2,color=RED)
        self.dynamic.add(shape,c1,c2);self.mark_origin()
        n=arrow(GOLD);put_arrow(n,world([0,0,.01]),OUT*1.7);self.add(n)
        def update(t):
            b=3-4*phase(self.data,t,2,2)
            for m,points in initial:
                p=points.copy();p[:,2]+=.5*(b-3)*p[:,1]**2;m.set_points(C+SCALE*p)
            c2.become(section_curve(PI/2,b=b,color=RED))
        def panel(i):
            items=[('eq','K=k_1 k_2',TEAL),('eq','H=(k_1+k_2)/2',GOLD)]
            if i==1:items.extend([('eq','k_1=1, quad k_2=3',INK),('eq','K=3, quad H=2',BLUE)])
            if i>=3:items.extend([('eq','k_1=1, quad k_2=-1',RED),('eq','K=-1, quad H=0',INK)])
            return i,'ПРОИЗВЕДЕНИЕ И ПОЛУСУММА',items
        return update,panel

    def build_cylinder(self):
        grid=Surface(lambda x,y:world([x,y,0]),u_range=[-1.15,1.15],v_range=[-1,1],resolution=(20,12),
            checkerboard_colors=False,fill_color=TEAL,fill_opacity=.65,stroke_color=GRID,stroke_width=.7)
        src=[(m,(m.get_points().copy()-C)/SCALE) for m in grid.family_members_with_points()]
        across=curve([world([x,0,0]) for x in np.linspace(-1.1,1.1,60)],GOLD,5)
        along=curve([world([0,y,0]) for y in np.linspace(-1,1,60)],BLUE,5)
        arrows=[arrow(GOLD) for _ in range(3)]
        self.dynamic.add(grid,across,along,*arrows)
        def update(t):
            bend=1.25*(1-phase(self.data,t,4,4))
            for m,points in src:
                p=points.copy()
                if bend>1e-8:p[:,0]=np.sin(bend*points[:,0])/bend;p[:,2]=(np.cos(bend*points[:,0])-1)/bend
                m.set_points(C+SCALE*p)
            across.become(curve([world(geo.sheet(x,0,bend)+.008*geo.sheet_normal(x,bend)) for x in np.linspace(-1.1,1.1,60)],GOLD,5))
            for x,m in zip([-.85,0,.85],arrows):put_arrow(m,world(geo.sheet(x,0,bend)),SCALE*.52*geo.sheet_normal(x,bend))
        def panel(i):
            if i<4:
                items=[('text','R — радиус, нормаль внешняя',MUTED),('eq','k_1=-1/R, quad k_2=0',INK)]
                if i>=3:items.append(('eq','K=0, quad S != 0',GOLD))
                return min(i,3),'ЦИЛИНДР',items
            return 4,'РАЗВЁРТКА БЕЗ РАСТЯЖЕНИЯ',[('text','Длины на листе сохраняются',BLUE),('text','Внешний изгиб уменьшается до нуля',GOLD),('eq','K=0',TEAL)]
        return update,panel

    def build_sphere(self):
        radius=1.;sphere=Surface(lambda u,v:world([np.sin(u)*np.cos(v),np.sin(u)*np.sin(v),np.cos(u)]),
            u_range=[.001,PI-.001],v_range=[0,TAU],resolution=(16,30),checkerboard_colors=False,fill_color=TEAL,fill_opacity=.48,stroke_color=GRID,stroke_width=.6)
        self.add(sphere)
        directions=[np.array([np.sin(u)*np.cos(v),np.sin(u)*np.sin(v),np.cos(u)]) for u in [PI/4,PI/2,3*PI/4] for v in [PI/8,3*PI/8,5*PI/8]]
        outward=[arrow(GOLD) for _ in directions];inward=[arrow(BLUE) for _ in directions]
        self.dynamic.add(*outward,*inward)
        def update(t):
            q=phase(self.data,t,3,3)
            for p,a,b in zip(directions,outward,inward):
                put_arrow(a,world(p),SCALE*.36*p);put_arrow(b,world(p),-SCALE*.36*p)
                a.set_opacity(1-q);b.set_opacity(q)
        def panel(i):
            if i<2:return 0,'СФЕРА РАДИУСА R',[('eq','n(p)=p/R',GOLD),('eq','dif n_p (w)=w/R',BLUE)]
            items=[('eq','k_1=k_2=-1/R',GOLD),('eq','K=1/R^2',TEAL)]
            if i>=3:items=[('eq','n -> -n',BLUE),('eq','k_1,k_2 -> -k_1,-k_2',INK),('eq','K=1/R^2',TEAL)]
            if i>=4:items.append(('text','Следующий вопрос: как измерить K изнутри?',MUTED))
            return min(i,4),'ВЫБОР СТОРОНЫ И КРИВИЗНА',items
        return update,panel
