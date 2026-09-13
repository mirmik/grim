"""Native Manim illustrations of fields, moving frames and tangent projection."""
import importlib.util
import json
from pathlib import Path
import numpy as np
from manim import *
import geometry as geo

ROOT=Path(__file__).resolve().parent
TIMELINE=json.loads((ROOT/'output/timeline.json').read_text())
spec=importlib.util.spec_from_file_location('vector_scene_base',ROOT.parent/'spherical-geometry-manim/lesson.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.TIMELINE=TIMELINE
txt,para,eq,at,phase,curve=base.txt,base.para,base.eq,base.at,base.phase,base.curve
BG,INK,MUTED,GRID,TEAL,GOLD,BLUE,RED=base.BG,base.INK,base.MUTED,base.GRID,base.TEAL,base.GOLD,base.BLUE,base.RED


def arrow3(color=TEAL):
    m=Arrow3D(ORIGIN,RIGHT,color=color,thickness=.023,height=.13,base_radius=.06,resolution=6)
    m.remove(m.cone)
    m.cone=Cone(direction=RIGHT,base_radius=.06,height=.13,resolution=(1,8),
                fill_color=color,fill_opacity=1,stroke_width=0).shift(RIGHT)
    m.add(m.cone)
    m.template=[(q,q.get_points().copy()) for q in m.family_members_with_points()]
    return m


def put3(m,p,v,opacity=1.):
    v=np.asarray(v,dtype=float);length=np.linalg.norm(v)
    if length<1e-6:m.set_opacity(0);return
    axis=v/length;ref=OUT if abs(axis[2])<.9 else RIGHT
    side=np.cross(ref,axis);side/=np.linalg.norm(side)
    matrix=np.column_stack([v,side,np.cross(axis,side)])
    for part,points in m.template:part.set_points(points@matrix.T+np.asarray(p))
    m.set_opacity(opacity)


def a2(p,v,color=TEAL,opacity=1.,width=5):
    v=np.asarray(v,dtype=float)
    if np.linalg.norm(v)<1e-6:return Line(p,np.asarray(p)+1e-5*RIGHT,stroke_opacity=0)
    return Arrow(p,np.asarray(p)+v,buff=0,color=color,stroke_width=width,
                 max_tip_length_to_length_ratio=.2).set_opacity(opacity)


class Lesson(base.Lesson):
    def set_caption(self,idx):pass

    def header(self):
        s=self.data
        self.fixed(at(txt(s['chapter'].upper(),18,TEAL,width=11.7),-6.6,3.8),
            at(txt(s['title'],33,INK,width=13),-6.6,3.32),
            at(txt(f'{self.part+1:02d} / {len(TIMELINE):02d}',17,MUTED),5.55,3.8),
            Line([-6.6,2.7,0],[6.6,2.7,0],color=GRID,stroke_width=1),
            at(txt('GRIM · ВЕКТОРНЫЕ ПОЛЯ И ПРОБЛЕМА СРАВНЕНИЯ',15,MUTED),-6.6,-3.65))

    def moving_during(self,a,b):
        windows={'field':[(0,4)],'compare':[(0,3)],'planes':[(0,4)],'cylinder':[(0,4)],
                 'basis':[(1,5)],'projection':[(1,3),(5,5)],'transport':[(0,4)]}[self.data['id']]
        return any(b>self.data['cues'][i]['start'] and a<self.data['cues'][j]['end'] for i,j in windows)

    def flat(self):self.set_camera_orientation(phi=0,theta=-PI/2)

    def camera_map(self,x=-3.25,y=-.1,scale=1.,theta=70*DEGREES,phi=62*DEGREES):
        self.set_camera_orientation(phi=phi,theta=theta)
        right=np.array([-np.sin(theta),np.cos(theta),0.])
        up=np.array([-np.cos(phi)*np.cos(theta),-np.cos(phi)*np.sin(theta),np.sin(phi)])
        center=x*right+y*up
        return lambda p:center+scale*np.asarray(p),right,up

    def label3(self,text,p,color=INK,size=23):
        label=txt(text,size,color).move_to(p);self.add_fixed_orientation_mobjects(label);return label

    def panel(self,title,items):
        if self.data['id']=='transport':
            g=VGroup(txt(title,22,TEAL,width=12.5).move_to([0,-2.55,0]))
            if items:
                g.add(para(items[0][1],24,width=12,color=items[0][2]).move_to([0,-3.03,0]))
            return g
        return super().panel(title,items)

    def build_field(self):
        self.flat();s=self.data
        def wind(y):return np.array([.62+.11*y,.13*y,0])
        for x in np.arange(-5.9,-.7,.8):
            for y in np.arange(-2,2,.65):self.add(a2([x,y,0],wind(y),TEAL,.45,3))
        pathx=-3.5
        self.add(Line([pathx,-2.1,0],[pathx,2.1,0],color=BLUE,stroke_width=5))
        dot=Dot(color=INK,radius=.065);v=a2(ORIGIN,RIGHT);velocity=a2(ORIGIN,UP,BLUE)
        self.dynamic.add(dot,v,velocity)
        self.add(txt('Маршрут',22,BLUE).move_to([-4.35,-2.52,0]),txt('Поле ветра',22,TEAL).move_to([-1.55,-2.52,0]))
        def update(t):
            y=-1.85+3.7*phase(s,t,0,4);p=np.array([pathx,y,0])
            dot.move_to(p);v.become(a2(p,wind(y)*1.9,TEAL,1,7))
            velocity.become(a2(p,UP*.65,BLUE,phase(s,t,3),4))
        def panel(i):
            if i<2:return 0,'ВЕКТОРНОЕ ПОЛЕ',[('eq','p -> X(p)',TEAL),('text','В каждой точке — своя стрелка',INK),('text','Длина показывает скорость ветра',MUTED)]
            if i<4:return 2,'ПОЛЕ ВДОЛЬ ПУТИ',[('eq','V(t)=X(gamma(t))',TEAL),('text','Синий — наше движение',BLUE),('text','Зелёный — ветер в текущей точке',TEAL)]
            return 4,'ЧТО ИЗМЕНЯЕТСЯ?',[('text','Сравниваем значения поля вдоль выбранного маршрута',INK)]
        return update,panel

    def build_compare(self):
        self.flat();s=self.data;o=np.array([-3.8,-.85,0]);p=np.array([-5.35,-1.8,0]);q=np.array([-2.4,.45,0])
        v=np.array([1.35,.6,0]);w=np.array([.65,1.7,0])
        self.add(Dot(p,color=MUTED),Dot(q,color=MUTED),DashedLine(p,q,color=GRID),
                 a2(p,v,TEAL,.25),a2(q,w,BLUE,.25))
        old=a2(p,v);new=a2(q,w,BLUE);delta=a2(o+v,w-v,GOLD)
        self.dynamic.add(old,new,delta)
        self.add(txt('Старое значение',20,TEAL).move_to([-5,-2.55,0]),txt('Новое значение',20,BLUE).move_to([-1.8,-2.55,0]))
        def update(t):
            join=phase(s,t,0);shrink=1-.8*phase(s,t,3)
            wp=v+shrink*(w-v)
            old.become(a2((1-join)*p+join*o,v,TEAL))
            new.become(a2((1-join)*q+join*o,wp,BLUE))
            delta.become(a2(o+v,shrink*(w-v),GOLD,phase(s,t,1),6))
        def panel(i):
            if i==0:return 0,'ОДНО ОБЩЕЕ НАЧАЛО',[('text','Переносим, сохраняя длину и направление',INK)]
            if i==1:return 1,'РАЗНОСТЬ',[('eq','Delta V=V(t+h)-V(t)',GOLD),('text','От старого конца к новому',MUTED)]
            if i<4:return 2,'СКОРОСТЬ ИЗМЕНЕНИЯ',[('eq','(Delta V)/h -> (d V)/(d t)',GOLD),('text','Сближаем моменты измерения',INK)]
            return 4,'ПРАВИЛО СРАВНЕНИЯ',[('text','На плоскости параллельный перенос привычен',INK)]
        return update,panel

    def build_planes(self):
        world,sr,su=self.camera_map(scale=1.65,theta=35*DEGREES,phi=55*DEGREES);s=self.data
        def p(u,v):return np.array([u,v,.32*u*u+.22*v*v])
        surf=Surface(lambda u,v:world(p(u,v)),u_range=[-1.35,1.35],v_range=[-1,1],resolution=(18,14),
                     checkerboard_colors=False,fill_color=TEAL,fill_opacity=.35,stroke_color=GRID,stroke_width=.65)
        self.add(surf,curve([world(p(u,0)+.007*OUT) for u in np.linspace(-1.2,1.2,40)],BLUE,4))
        def tangent(u,color):
            e=np.array([1,0,.64*u]);e/=np.linalg.norm(e);pt=p(u,0)
            return Polygon(*[world(pt+.42*(a*e+b*UP)) for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]],
                           fill_color=color,fill_opacity=.18,stroke_color=color,stroke_width=1.2)
        fixed=tangent(-1.05,BLUE);self.add(fixed)
        a=arrow3(TEAL);put3(a,world(p(-1.05,0)),1.15*np.array([1,0,-.64*1.05])/np.linalg.norm([1,0,-.64*1.05]));self.add(a)
        plane=tangent(.1,GOLD);v=arrow3(TEAL);dot=Dot3D(radius=.045,color=INK,resolution=(4,8))
        self.dynamic.add(plane,v,dot)
        self.fixed(at(txt('Синий путь · зелёные значения поля',20,MUTED,width=5.8),-6.1,-2.75))
        def update(t):
            u=-.4+1.5*phase(s,t,0,4);pt=p(u,0);e=np.array([1,0,.64*u]);e/=np.linalg.norm(e)
            plane.become(tangent(u,GOLD));put3(v,world(pt),1.15*e);dot.move_to(world(pt))
        def panel(i):
            if i<2:return 0,'РАЗНЫЕ КАСАТЕЛЬНЫЕ ПЛОСКОСТИ',[('eq','X(p) in T_p M',TEAL),('text','Плоскость зависит от точки',INK)]
            if i<4:return 2,'ВЗГЛЯД ИЗ ПРОСТРАНСТВА',[('text','Трёхмерную разность вычислить можно',INK),('text','Она замечает внешний изгиб',GOLD)]
            return 4,'ВЗГЛЯД С ПОВЕРХНОСТИ',[('text','Изменилось ли направление внутри нашего мира?',GOLD)]
        return update,panel

    def cylinder_mesh(self,world,span=np.pi,height=1.1,bend=1.,resolution=(28,10)):
        m=Surface(lambda u,v:world([u,0,v]),u_range=[-span,span],v_range=[-height,height],resolution=resolution,
                  checkerboard_colors=False,fill_color=TEAL,fill_opacity=.24,stroke_color=GRID,stroke_width=.55)
        # Store flat material coordinates; every deformation preserves ds²+dz².
        inv=[]
        origin=world([0,0,0]);ex=world([1,0,0])-origin;ez=world([0,0,1])-origin
        for face in m.family_members_with_points():
            pts=face.get_points().copy()-origin
            inv.append((face,pts@ex/np.dot(ex,ex),pts@ez/np.dot(ez,ez)))
        def bend_to(k):
            for face,us,zs in inv:face.set_points(np.array([world(geo.sheet(u,z,k)) for u,z in zip(us,zs)]))
        bend_to(bend)
        return m,bend_to

    def build_cylinder(self):
        world,sr,su=self.camera_map(x=-3.2,y=.25,scale=.9);s=self.data
        mesh,bend_to=self.cylinder_mesh(world);trace=VMobject();v=arrow3();dot=Dot3D(radius=.046,color=INK,resolution=(4,8))
        arrows=[arrow3(TEAL) for _ in range(7)];seam=VMobject()
        self.dynamic.add(mesh,trace,seam,*arrows,v,dot)
        self.fixed(at(txt('Один лист · без растяжения',22,MUTED,width=5.8),-6,-2.75))
        def update(t):
            k=1-phase(s,t,2,3);pos=-1.5+3*phase(s,t,0,1)
            bend_to(k)
            trace.become(curve([world(geo.sheet(u,0,k)+.012*geo.frame(u,k)[2]) for u in np.linspace(-2.8,2.8,65)],BLUE,4))
            seam.become(curve([world(geo.sheet(np.pi,z,k)) for z in np.linspace(-1.1,1.1,12)],RED,3))
            seam.set_opacity(phase(s,t,2))
            for u,a in zip(np.linspace(-2.6,2.6,7),arrows):
                put3(a,world(geo.sheet(u,0,k)+.025*geo.frame(u,k)[2]),.5*geo.field(u,0,k),.65)
            point=world(geo.sheet(pos,0,k)+.045*geo.frame(pos,k)[2]);dot.move_to(point);put3(v,point,.85*geo.field(pos,0,k))
        def panel(i):
            if i<2:return 0,'В ПРОСТРАНСТВЕ',[('text','Стрелка поворачивается вместе с цилиндром',TEAL),('text','Её длина постоянна',MUTED)]
            if i<5:return 2,'НА РАЗВЁРТКЕ',[('text','Маршрут стал прямым',BLUE),('text','Стрелки одинаковы',TEAL),('text','Длины и углы сохранены',MUTED)]
            return 5,'КАКОЕ ИЗМЕНЕНИЕ МЫ ИЩЕМ?',[('text','Изменение вдоль поверхности',INK),('text','Внешний изгиб нужно отделить',GOLD)]
        return update,panel

    def build_basis(self):
        self.flat();s=self.data;o=np.array([-3.5,-.35,0]);length=1.9
        self.add(Circle(radius=length,color=GRID,stroke_width=1).move_to(o),Dot(o,color=INK))
        axis1=Line(o-3*RIGHT,o+3*RIGHT,color=BLUE);axis2=Line(o-2*UP,o+2*UP,color=RED)
        p1=a2(o,RIGHT,BLUE);p2=a2(o,UP,RED);guide=DashedLine(o,o+RIGHT,color=GRID)
        self.dynamic.add(axis1,axis2,guide,p1,p2)
        fixed=a2(o,length*RIGHT,TEAL,1,8).set_z_index(5);self.add(fixed)
        self.add(txt('V — неподвижная стрелка',23,TEAL,width=5.8).move_to([-3.4,-2.9,0]))
        label1=txt('e₁',23,BLUE);label2=txt('e₂',23,RED)
        nums=VGroup();self.dynamic.add(label1,label2)
        # Fixed readouts keep component values separate from the moving picture.
        na=DecimalNumber(1,num_decimal_places=2,font_size=35,color=BLUE,mob_class=Text)
        nb=DecimalNumber(0,num_decimal_places=2,font_size=35,color=RED,mob_class=Text)
        self.dynamic.add(na,nb)
        self.fixed(at(txt('a =',28,BLUE),.9,-1.8),at(txt('b =',28,RED),3.55,-1.8))
        def update(t):
            angle=(PI/2-.01)*phase(s,t,1,4)
            e1=np.array([np.cos(angle),np.sin(angle),0]);e2=np.array([-np.sin(angle),np.cos(angle),0])
            axis1.put_start_and_end_on(o-2.3*e1,o+2.3*e1);axis2.put_start_and_end_on(o-2.3*e2,o+2.3*e2)
            va=length*np.cos(angle)*e1;vb=-length*np.sin(angle)*e2
            p1.become(a2(o,va,BLUE,phase(s,t,2),5));p2.become(a2(o+va,vb,RED,phase(s,t,2),5))
            guide.become(DashedLine(o+va,o+length*RIGHT,color=GRID,dash_length=.08))
            label1.move_to(o+2.48*e1);label2.move_to(o+2.48*e2)
            na.set_value(np.cos(angle)).move_to([2.2,-2.0,0]);nb.set_value(-np.sin(angle)).move_to([4.95,-2.0,0])
        def panel(i):
            if i<4:return 0,'ЗАПИСЬ В ПОДВИЖНЫХ ОСЯХ',[('eq','V=a e_1+b e_2',TEAL),('text','Оси вращаются, компоненты меняются',INK)]
            return 4,'ДВА ВКЛАДА',[('text','Изменение компонент',BLUE),('text','Изменение базиса',RED),('text','Здесь они компенсируются',INK)]
        return update,panel

    def build_projection(self):
        world,sr,su=self.camera_map(x=-4.1,y=-.4,scale=1.2,theta=45*DEGREES,phi=58*DEGREES);s=self.data
        plane=Polygon(*[world([x,y,0]) for x,y in [(-1.25,-1.25),(1.25,-1.25),(1.25,1.25),(-1.25,1.25)]],
                      fill_color=TEAL,fill_opacity=.2,stroke_color=GRID,stroke_width=1.3)
        self.add(plane,Dot3D(world([0,0,0]),radius=.05,color=INK,resolution=(4,8)))
        tangent=np.array([-1.1,1.1,0]);normal=np.array([0,0,1.35]);ambient=tangent+normal
        a=arrow3(GOLD);tan=arrow3(BLUE);norm=arrow3(RED);v=arrow3(TEAL)
        self.dynamic.add(a,tan,norm,v)
        self.label3('dV/dt',world(ambient)+.23*su,GOLD)
        lt=self.label3('Касательная часть',world(tangent)-.24*su,BLUE,20)
        ln=self.label3('Нормальная часть',world(tangent+.65*normal)+1.4*sr,RED,17)
        self.dynamic.add(lt,ln)
        self.fixed(at(txt('Касательная плоскость в текущей точке',20,MUTED,width=5.9),-6.2,-2.8))
        def update(t):
            put3(a,world([0,0,0]),1.2*ambient*phase(s,t,1))
            visible=phase(s,t,2);keep=phase(s,t,3)
            put3(tan,world([0,0,0]),1.2*tangent,visible)
            put3(norm,world(tangent),1.2*normal,visible*(1-.65*keep))
            lt.set_opacity(visible);ln.set_opacity(visible*(1-.65*keep))
            put3(v,world([0,0,.015]),1.2*np.array([.85,0,0]),phase(s,t,5))
        def panel(i):
            if i<2:return 0,'ОБЫЧНАЯ ПРОИЗВОДНАЯ',[('eq','(d V)/(d t)',GOLD),('text','Как меняется стрелка в трёхмерном пространстве',INK)]
            if i==2:return 2,'РАЗЛОЖЕНИЕ ИЗМЕНЕНИЯ',[('text','Вдоль поверхности',BLUE),('text','Поперёк поверхности',RED)]
            return 3,'КОВАРИАНТНАЯ ПРОИЗВОДНАЯ',[('eq','(D V)/(d t)=((d V)/(d t))_"tan"',BLUE),('text','Касательная часть обычной производной',INK)]
        return update,panel

    def build_transport(self):
        s=self.data;groups=[]
        for x,rotating in [(-3.1,False),(3.1,True)]:
            world,sr,su=self.camera_map(x=x,y=.65,scale=.84)
            mesh,_=self.cylinder_mesh(world,span=2.4,height=.75,resolution=(22,8));self.add(mesh)
            self.add(curve([world(geo.sheet(u,0,1)+.018*geo.frame(u)[2]) for u in np.linspace(-2.2,2.2,60)],BLUE,3))
            v=arrow3(TEAL);change=arrow3(GOLD);tan=arrow3(BLUE);dot=Dot3D(radius=.04,color=INK,resolution=(4,8))
            self.dynamic.add(v,change,tan,dot)
            self.fixed(txt('Поворот на листе' if rotating else 'Постоянно на листе',23,INK).move_to([x,2.05,0]))
            center=np.array([x,-1.30,0]);strip=Rectangle(width=4.9,height=1.5,fill_color=TEAL,fill_opacity=.08,stroke_color=GRID)
            strip.move_to(center);line=Line(center+LEFT*2.2,center+RIGHT*2.2,color=BLUE,stroke_width=2)
            mini=a2(center,RIGHT,TEAL);mini_point=Dot(center,radius=.045,color=INK)
            self.fixed(strip,line,mini,mini_point)
            self.dynamic.add(mini,mini_point)
            self.fixed(txt('DV/dt ≠ 0' if rotating else 'DV/dt = 0',23,BLUE).move_to([x,-2.24,0]))
            groups.append((world,v,change,tan,dot,mini,mini_point,center,rotating))
        def update(t):
            q=phase(s,t,0,4);u=-1.65+3.3*q
            for world,v,a,tan,dot,mini,mdot,center,rotating in groups:
                beta=.48*(u+1.65) if rotating else 0.;rate=.48 if rotating else 0.
                p=world(geo.sheet(u,0,1)+.03*geo.frame(u)[2]);ambient,tangent,_=geo.derivative(u,beta,rate)
                put3(v,p,.76*geo.field(u,beta));put3(a,p,.72*ambient,phase(s,t,1 if not rotating else 2))
                put3(tan,p,.72*tangent,phase(s,t,2));dot.move_to(p)
                fp=center+RIGHT*(1.65-3.3*q);mini.become(a2(fp,.67*np.array([-np.cos(beta),np.sin(beta),0]),TEAL))
                mdot.move_to(fp)
        def panel(i):
            if i<3:return 0,'ЗОЛОТОЙ — ОБЫЧНАЯ ПРОИЗВОДНАЯ · ГОЛУБОЙ — КАСАТЕЛЬНАЯ ЧАСТЬ',[]
            if i==3:return 3,'ПАРАЛЛЕЛЬНЫЙ ПЕРЕНОС',[('text','Стрелка движется без внутреннего изменения',INK)]
            if i==4:return 4,'ЕСЛИ ПЕРЕНОСИМ СКОРОСТЬ МАРШРУТА',[('text','Получаем геодезическую при постоянной скорости',INK)]
            return 5,'ТЕПЕРЬ — К ФОРМУЛАМ ГЛАВЫ',[('text','Они описывают правило сравнения в разных точках',INK)]
        return update,panel
