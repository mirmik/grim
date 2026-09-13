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
OUT=ROOT/"output-voxcpm-scenes"
NARRATOR="XTTS v2"
os.environ.setdefault("MPLCONFIGDIR",str(OUT/"mpl-cache"))
from PIL import Image,ImageDraw,ImageFont,ImageColor
import numpy as np
from matplotlib import mathtext
from matplotlib.font_manager import FontProperties

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
