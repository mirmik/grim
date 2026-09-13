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
from geometry import N,A,unit,arc,vertices,transport,cylinder,validate,solid_angle,ellipsoid_point,ellipsoid_curvature

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
