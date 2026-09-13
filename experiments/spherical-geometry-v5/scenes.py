"""Revised lesson: short setup, then measurements, additivity and topology."""
from scene_support import *

DYNAMIC={'setup','prepare_arrow','excess','quick_triangle','vary','number','local','add','integral','cylinder','boundary','transport_fast'}

def filled_triangle(im,vs,col=CYAN):
    pts=[]
    for a,b in zip(vs,vs[1:]+vs[:1]):pts += [arc(a,b,u) for u in np.linspace(0,1,61)]
    overlay=Image.new('RGBA',im.size)
    from PIL import ImageColor
    ImageDraw.Draw(overlay).polygon([project(p) for p in pts],fill=(*ImageColor.getrgb(col),65))
    im.paste(overlay,(0,0),overlay)
    line3(ImageDraw.Draw(im),pts+[pts[0]],col,5)

@lru_cache(16)
def ellipsoid_picture(n=16):
    im=Image.new('RGB',(1080,615),PANEL);d=ImageDraw.Draw(im)
    lats=np.linspace(-math.pi/2,math.pi/2,n+1);lons=np.linspace(0,2*math.pi,2*n+1)
    faces=[]
    for a,b in zip(lats,lats[1:]):
        for c,e in zip(lons,lons[1:]):
            ps=[ellipsoid_point(a,c),ellipsoid_point(b,c),ellipsoid_point(b,e),ellipsoid_point(a,e)]
            p=ellipsoid_point((a+b)/2,(c+e)/2)
            k=ellipsoid_curvature(p);v=np.clip((k-.25)/3,0,1)
            col=tuple(round(x+(y-x)*v) for x,y in zip((31,96,119),(243,192,101)))
            faces.append((np.dot(p,VIEW),ps,col))
    for _,ps,col in sorted(faces,key=lambda x:x[0]):
        d.polygon([project(p,(540,290),245) for p in ps],fill=col,outline='#405772',width=1)
    return im

def torus_picture(d):
    faces=[]
    def point(u,v):return np.array([(1+.43*math.cos(v))*math.cos(u),(1+.43*math.cos(v))*math.sin(u),.43*math.sin(v)])
    for a,b in zip(np.linspace(0,2*math.pi,65),np.linspace(0,2*math.pi,65)[1:]):
        for c,e in zip(np.linspace(0,2*math.pi,33),np.linspace(0,2*math.pi,33)[1:]):
            ps=[point(a,c),point(b,c),point(b,e),point(a,e)]
            shade=.45+.45*abs(math.cos((c+e)/2))
            base=(70,203,194) if math.cos((c+e)/2)>=0 else (232,114,143)
            col=tuple(round(x*shade) for x in base)
            faces.append((np.dot(np.mean(ps,axis=0),VIEW),ps,col))
    for _,ps,col in sorted(faces,key=lambda x:x[0]):
        d.polygon([project(p,(600,530),280) for p in ps],fill=col,outline='#344963',width=1)

def plot_number(d,radius):
    x0,x1,y0,y1=180,1020,730,335
    d.line((x0,y1,x0,y0,x1,y0),fill=MUTED,width=3)
    for val in (.2,.4,.6):
        yy=y0-(y0-y1)*val/.7;dashed(d,(x0,yy),(x1,yy),GRID,2);text(d,(x0-20,yy-12),f'{val:.1f}°',23,MUTED,'ra')
    points=[(x0+(r-10)/10*(x1-x0),y0-math.degrees(1/r**2)/.7*(y0-y1)) for r in np.linspace(10,20,150)]
    d.line(points,fill=CYAN,width=5)
    xx=x0+(radius-10)/10*(x1-x0);yy=y0-math.degrees(1/radius**2)/.7*(y0-y1)
    d.ellipse((xx-10,yy-10,xx+10,yy+10),fill=GOLD)
    for r in (10,15,20):text(d,(x0+(r-10)/10*(x1-x0),y0+15),str(r),26,MUTED,'ma')
    text(d,(190,275),'Избыток ε, градусы',28,CYAN)
    text(d,(1000,790),'Радиус R, км',27,MUTED,'ra')

def draw_visual(t,timeline,idx):
    s=timeline[idx];mode=s['id'];u=phase(s,t,0,len(s['cues'])-1)
    im=globe().copy();d=ImageDraw.Draw(im)
    panel(d,(1165,235,1860,850))
    text(d,(75,40),'ДИФФЕРЕНЦИАЛЬНАЯ ГЕОМЕТРИЯ · КРИВИЗНА ИЗНУТРИ',23,CYAN)
    text(d,(1845,40),f'{idx+1:02d} / {len(timeline):02d}',24,MUTED,'ra')
    title_size=49
    while len(wrap(s['title'],title_size,1770))>1:title_size-=1
    text(d,(75,100),s['title'],title_size,FG,bold=True)
    text(d,(75,175),s['chapter'],27,MUTED)
    if mode in ('goal','quick_triangle','excess','area','vary','bonnet','turns'):
        phi=math.pi/2-math.pi/3*phase(s,t,0,3) if mode=='vary' else math.pi/2
        progress=sum(phase(s,t,i,i) for i in (3,4,5)) if mode=='quick_triangle' else 3
        triangle(im,phi,progress,angles=(mode=='excess' and t>=s['cues'][2]['start']) or (mode=='quick_triangle' and progress>=2.99))
        d=ImageDraw.Draw(im)
        if mode=='goal':
            info(d,'ЧТО УЗНАЕМ')
            for j,line in enumerate(['Углы → площадь','Площадь → кривизна','Кривизна → топология']):text(d,(1200,390+j*105),line,36,[FG,CYAN,GOLD][j])
            text(d,(1200,755),'Длины и углы измеряем на поверхности',25,MUTED)
        elif mode=='quick_triangle':
            p,_=transport(progress);x,y=project(p);d.ellipse((x-9,y-9,x+9,y+9),fill=FG)
            info(d,'ГЕОДЕЗИЧЕСКИЕ НА СФЕРЕ')
            paragraph(d,1200,370,'Дуги окружностей с центром в центре сферы',600,31)
            if progress>=2.99:
                text(d,(1200,555),'90° + 90° + 90°',44,CYAN)
                text(d,(1200,650),'= 270°',65,GOLD,bold=True)
            else:
                for j,(label,col) in enumerate([('N → A · меридиан',CYAN),('A → Б · экватор',GOLD),('Б → N · меридиан',BLUE)]):text(d,(1200,535+j*80),label,32,col)
        elif mode=='excess':
            vector(d,N,A,BLUE);vector(d,*transport(3));tangent_inset(d)
            if t<s['cues'][1]['start']:
                info(d,'СРАВНИВАЕМ НАПРАВЛЕНИЯ')
                text(d,(1200,395),'Поворот: 90°',56,GOLD)
                paragraph(d,1200,545,'Золотая стрелка перпендикулярна исходной голубой метке.',600,32)
            elif t<s['cues'][2]['start']:
                info(d,'ГЕОДЕЗИЧЕСКИЕ НА СФЕРЕ')
                paragraph(d,1200,395,'Меридианы и экватор — аналоги прямых на поверхности.',600,34)
            else:
                info(d,'УГЛЫ СФЕРИЧЕСКОГО ТРЕУГОЛЬНИКА')
                text(d,(1200,370),'α, β, γ — внутренние углы',28,MUTED)
                if t>=s['cues'][3]['start']:text(d,(1200,480),'270° − 180° = 90°',40,GOLD)
                if t>=s['cues'][4]['start']:
                    formula(im,(1200,595),r'\varepsilon=\alpha+\beta+\gamma-\pi',30,600)
                    text(d,(1200,740),'ε — угловой избыток',30,CYAN)
        elif mode=='area':
            info(d,'A — ПЛОЩАДЬ, R — РАДИУС')
            formula(im,(1200,385),r'A=\frac{4\pi R^2}{8}=\frac{\pi R^2}{2}',31,600)
            formula(im,(1200,595),r'\frac{A}{R^2}=\frac{\pi}{2}=90^\circ',32,600)
            text(d,(600,805),'Выделена 1/8 площади сферы',26,MUTED,'ma')
        elif mode=='vary':
            info(d,'φ — УГОЛ МЕЖДУ МЕРИДИАНАМИ')
            text(d,(1200,380),f'φ = {math.degrees(phi):.0f}°',57,GOLD,bold=True)
            text(d,(1200,490),f'Избыток ε = {math.degrees(phi):.0f}°',38,CYAN)
            formula(im,(1200,620),r'A=R^2\varphi=R^2\varepsilon',30,600)
            text(d,(1200,755),'В формулах углы — в радианах',26,MUTED)
        elif mode=='bonnet':
            info(d,'T — ОБЛАСТЬ ТРЕУГОЛЬНИКА')
            formula(im,(1200,385),r'\varepsilon=\int_T K\,dA',44,600)
            paragraph(d,1200,565,'K — местная кривизна; dA — элемент площади.',600,30)
            paragraph(d,1200,685,'Область без дыр, граница из геодезических.',600,31,FG)
        else:
            info(d,'ВНЕШНИЕ ПОВОРОТЫ + КРИВИЗНА')
            text(d,(1200,380),'270° + 90° = 360°',40,GOLD)
            formula(im,(1200,490),r'3\pi-(\alpha+\beta+\gamma)+\int_T K\,dA=2\pi',25,600)
            formula(im,(1200,675),r'\alpha+\beta+\gamma-\pi=\int_T K\,dA',29,600)
            text(d,(600,805),'Внешний поворот = π − внутренний угол',25,MUTED,'ma')
    elif mode=='number':
        panel(d,(60,235,1140,850));r=10+10*phase(s,t,3,4);plot_number(d,r)
        info(d,'ПЛОЩАДЬ A = 1 км²')
        formula(im,(1200,365),r'\varepsilon=\frac{A}{R^2}',37,600)
        text(d,(1200,495),f'R = {r:.1f} км',40,FG)
        text(d,(1200,580),f'ε = {1/r**2:.4f} рад',38,CYAN)
        text(d,(1200,660),f'≈ {math.degrees(1/r**2):.3f}°',44,GOLD)
        text(d,(1200,765),'R × 2 → ε / 4 при той же площади',26,MUTED)
    elif mode=='local':
        rho=.8-.7*phase(s,t,0,2)
        vs=[math.cos(rho)*VIEW+math.sin(rho)*(math.cos(a)*RIGHT+math.sin(a)*UP) for a in (math.pi/2,7*math.pi/6,11*math.pi/6)]
        filled_triangle(im,vs);d=ImageDraw.Draw(im)
        eps=solid_angle(*vs);area=9*eps
        info(d,'K — ГАУССОВА КРИВИЗНА В ТОЧКЕ')
        formula(im,(1200,360),r'K(p)=\lim_{T\to p}\frac{\varepsilon(T)}{A(T)}',30,600)
        paragraph(d,1200,515,'T — уменьшаемый треугольник; p — выбранная точка.',600,27)
        text(d,(1200,620),f'A = {area:.4f}',32,FG)
        text(d,(1200,680),f'ε = {eps:.4f} рад',32,CYAN)
        text(d,(1200,755),'ε / A = 1/9',38,GOLD)
        x,y=project(VIEW);d.ellipse((x-4,y-4,x+4,y+4),fill=FG);text(d,(x+20,y+10),'p',25,FG)
        text(d,(600,805),'Сфера R = 3. Треугольник T стягивается к точке p',24,MUTED,'ma')
    elif mode=='add':
        triangle(im);m=arc(A,vertices()[2],.5)
        if phase(s,t,0,0)>.35:
            filled_triangle(im,[N,A,m],CYAN);filled_triangle(im,[N,m,vertices()[2]],GOLD)
        d=ImageDraw.Draw(im)
        info(d,'ГЕОДЕЗИЧЕСКИЙ РАЗРЕЗ')
        formula(im,(1200,395),r'\varepsilon=\varepsilon_1+\varepsilon_2',36,600)
        formula(im,(1200,530),r'A=A_1+A_2',36,600)
        paragraph(d,1200,670,'В новой точке на стороне внутренние углы дают π.',600,30)
    elif mode=='integral':
        n=[8,12,20][min(2,int(u*3))];im.paste(ellipsoid_picture(n),(60,235));d=ImageDraw.Draw(im)
        info(d,'T — РАССМАТРИВАЕМАЯ ОБЛАСТЬ')
        formula(im,(1200,390),r'\sum_i K_i\,\Delta A_i\ \longrightarrow\ \int_T K\,dA',28,600)
        paragraph(d,1200,540,'Kᵢ — кривизна участка; ΔAᵢ — его площадь.',600,31)
        paragraph(d,1200,665,'Светлее цвет → больше K. Сетка уточняет разбиение.',600,29)
        text(d,(1200,790),'dA — элемент площади',26,MUTED)
        text(d,(600,805),'Эллипсоид: кривизна меняется от точки к точке',25,MUTED,'ma')
    elif mode in ('principal','saddle'):
        panel(d,(60,235,1140,850));surface_mesh(d,'saddle',(600,525),215)
        info(d,'k₁, k₂ — ГЛАВНЫЕ КРИВИЗНЫ')
        formula(im,(1200,380),r'K=k_1k_2',39,600)
        if mode=='principal':
            paragraph(d,1200,540,'Одинаковые знаки: K > 0. Разные знаки: K < 0.',600,33)
            text(d,(1200,745),'Знак зависит от обоих изгибов',28,MUTED)
        else:
            formula(im,(1200,540),r'K<0\ \Longrightarrow\ \varepsilon<0',30,600)
            text(d,(1200,675),'α + β + γ < 180°',37,RED)
            text(d,(1200,765),'При K < 0 во всей области',25,MUTED)
        text(d,(600,805),'Главные нормальные сечения через центр седла',24,MUTED,'ma')
    elif mode=='cylinder':
        panel(d,(60,235,1140,850));surface_mesh(d,'cylinder',(600,615),215,1.15*phase(s,t,1,3))
        info(d,'ОДНО ИЗ НАПРАВЛЕНИЙ ПРЯМОЕ')
        formula(im,(1200,380),r'K=k_1\cdot 0=0',35,600)
        paragraph(d,1200,535,'Сворачиваем без растяжения. Длины и углы сохраняются.',600,32)
        text(d,(1200,720),'α + β + γ = 180°',37,GOLD)
        text(d,(600,805),'Изометрическое сворачивание листа',26,MUTED,'ma')
    elif mode=='boundary':
        panel(d,(60,235,1140,850));theta=2*math.pi*phase(s,t,0,2);c=(560,525);r=190
        d.ellipse((c[0]-r,c[1]-r,c[0]+r,c[1]+r),outline=CYAN,width=5)
        p=(c[0]+r*math.cos(theta),c[1]-r*math.sin(theta));q=(p[0]-85*math.sin(theta),p[1]-85*math.cos(theta));arrow(d,p,q,GOLD,6,17)
        text(d,(560,505),'K = 0',43,FG,'ma')
        text(d,(560,780),'Касательная поворачивается на 360°',29,GOLD,'ma')
        info(d,'kɢ — ГЕОДЕЗИЧЕСКАЯ КРИВИЗНА')
        paragraph(d,1200,370,'Изгиб самой границы внутри поверхности',600,32)
        formula(im,(1200,515),r'\oint k_g\,ds=2\pi',36,600)
        text(d,(1200,640),'ds — элемент длины границы',26,MUTED)
        text(d,(1200,750),'На геодезической: kɢ = 0',30,CYAN)
    elif mode=='setup':
        triangle(im,progress=0,fill=False);local_plane(im,N);d=ImageDraw.Draw(im)
        vector(d,N,A,BLUE,size=.46);vector(d,N,A,GOLD,size=.34)
        info(d,'ОПЫТ С НАПРАВЛЕНИЕМ')
        paragraph(d,1200,375,'Поворот стрелки → углы треугольника → кривизна',600,34)
        if t>=s['cues'][2]['start']:
            text(d,(600,805),'Голубая стрелка — исходная метка',26,BLUE,'ma')
        if t>=s['cues'][3]['start']:
            paragraph(d,1200,560,'На стороне сохраняем угол с путём. В вершине стрелку не вращаем.',600,31)
    elif mode=='prepare_arrow':
        triangle(im);local_plane(im,N);d=ImageDraw.Draw(im)
        vector(d,N,A,BLUE,size=.46);vector(d,N,A,GOLD,size=.34)
        info(d,'ПАРАЛЛЕЛЬНЫЙ ПЕРЕНОС')
        paragraph(d,1200,375,'Стрелка лежит в касательной плоскости.',600,32)
        if t>=s['cues'][3]['start']:paragraph(d,1200,515,'На геодезической сохраняем угол с направлением пути.',600,31)
        if t>=s['cues'][4]['start']:paragraph(d,1200,670,'В вершине поворачивает маршрут. Стрелку не вращаем.',600,30)
        text(d,(600,805),'Голубая метка сохранит исходное направление',25,BLUE,'ma')
    elif mode=='transport_fast':
        pr=sum(phase(s,t,a,b) for a,b in s['motion_sections']);triangle(im,progress=pr,fill=pr>=2.99);p,v=transport(pr);local_plane(im,p);d=ImageDraw.Draw(im);vector(d,N,A,BLUE);vector(d,p,v)
        if pr>2.99:tangent_inset(d)
        leg=min(3,int(pr+1e-9))
        labels=[('N → A','Стрелка смотрит вперёд, вдоль меридиана.'),('A → Б','Точка движется на восток. Стрелка направлена на юг.'),('Б → N','Точка поднимается к полюсу. Стрелка смотрит назад.'),('СНОВА НА ПОЛЮСЕ','Сравните золотую стрелку с оставленной голубой меткой.')]
        info(d,labels[leg][0]);paragraph(d,1200,390,labels[leg][1],600,35)
        if leg==3:text(d,(1200,685),'Направление изменилось',35,GOLD)
        text(d,(600,805),'Голубая стрелка — исходная метка',26,BLUE,'ma')
    elif mode=='global':
        im.paste(ellipsoid_picture(20),(60,235));d=ImageDraw.Draw(im)
        info(d,'χ — ЭЙЛЕРОВА ХАРАКТЕРИСТИКА')
        formula(im,(1200,365),r'\int_S K\,dA=2\pi\chi(S)',32,600)
        text(d,(1200,485),'S — вся замкнутая поверхность',25,MUTED)
        text(d,(1200,555),'χ = вершины − рёбра + грани',27,FG)
        text(d,(1200,640),'Для сферы: χ = 2',34,CYAN)
        text(d,(1200,725),'Интеграл = 4π',41,GOLD)
        text(d,(600,805),'Сфера → эллипсоид: полный интеграл сохраняется',24,MUTED,'ma')
    elif mode=='torus':
        panel(d,(60,235,1140,850));torus_picture(d)
        info(d,'ТОР: χ = 0')
        formula(im,(1200,375),r'\int_S K\,dA=0',39,600)
        text(d,(1200,540),'Снаружи: K > 0',35,CYAN)
        text(d,(1200,620),'У отверстия: K < 0',35,RED)
        paragraph(d,1200,720,'Нулевой интеграл не означает K = 0 в каждой точке.',600,28)
        text(d,(600,805),'Положительные и отрицательные вклады равны',25,MUTED,'ma')
    elif mode=='summary':
        panel(d,(60,235,1860,850))
        for j,(title,expr,note) in enumerate([
            ('ТОЧКА',r'K=\lim\frac{\varepsilon}{A}','Избыток на единицу площади'),
            ('ОБЛАСТЬ',r'\varepsilon=\int_T K\,dA','Геодезический треугольник'),
            ('ВСЯ ПОВЕРХНОСТЬ',r'\int_S K\,dA=2\pi\chi','Геометрия связана с топологией')]):
            x=115+j*600;text(d,(x,330),title,27,CYAN,bold=True);formula(im,(x,455),expr,32,500)
            paragraph(d,x,650,note,480,29)
    return im
