"""Install a verified chapter companion in the existing registered book."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import shutil

root=Path(__file__).resolve().parent;out=root/'output';project=root.parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--book-root',type=Path);args=parser.parse_args()
if args.book_root:
    book=args.book_root.resolve()
else:
    registry=json.loads((project/'.grim/library.json').read_text())
    matches=[Path(b['root']) for b in registry['books'] if b['title']=='Дифференциальная геометрия']
    assert len(matches)==1,'Specify --book-root when the title is ambiguous'
    book=matches[0]
chapter=book/'chapters/vector-fields-and-comparison.html';source=chapter.read_text()
assert '<h1 id="vector-fields">Векторные поля и проблема сравнения</h1>' in source
if '<!-- chapter-video:start -->' not in source:
    (out/'chapter-before.html').write_text(source)
report=json.loads((out/'validation.json').read_text());assert report['status']=='passed'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(out/'vector-fields-and-comparison.mp4')==report['video_sha256']
media=book/'assets/video';media.mkdir(parents=True,exist_ok=True)
files={
    'vector-fields-and-comparison.mp4':'vector-fields-and-comparison.mp4',
    'vector-fields-and-comparison.jpg':'vector-fields-and-comparison.jpg',
    'subtitles.vtt':'vector-fields-and-comparison.ru.vtt',
    'subtitles.srt':'vector-fields-and-comparison.ru.srt',
    'chapters.vtt':'vector-fields-and-comparison.chapters.vtt',
}
def copy_atomic(src,dst):
    temp=dst.with_name(dst.name+'.tmp');shutil.copyfile(src,temp);temp.replace(dst)
for src,dst in files.items():copy_atomic(out/src,media/dst)
for ext in ['css','js']:
    source_asset=root/f'player.{ext}';target_asset=book/f'assets/chapter-video.{ext}'
    if target_asset.exists():assert digest(source_asset)==digest(target_asset),'Shared player must stay compatible'
    else:copy_atomic(source_asset,target_asset)
timeline=json.loads((out/'timeline.json').read_text())
def timecode(t):
    seconds=int(t);return f'{seconds//60}:{seconds%60:02d}'
shortcuts=[('field','Карта ветра'),('cylinder','Развёртка цилиндра'),('basis','Подвижные оси'),
           ('projection','Касательная часть'),('transport','Параллельный перенос')]
buttons=[]
for id,label in shortcuts:
    scene=next(s for s in timeline if s['id']==id);t=scene['start'];caption=f'{timecode(t)} · {label}'
    buttons.append(f'<button type="button" data-video-time="{t:.5f}" aria-label="Смотреть с {timecode(t)}: {html.escape(label)}">{html.escape(caption)}</button>')
block=f'''<!-- chapter-video:start -->
<figure class="chapter-video" id="chapter-video" aria-labelledby="chapter-video-title">
  <div class="chapter-video-header"><h2 id="chapter-video-title">Видео к главе</h2><span class="chapter-video-duration">{timecode(round(timeline[-1]['end']))}</span></div>
  <video controls playsinline preload="metadata" crossorigin="anonymous" width="1920" height="1080" poster="../assets/video/vector-fields-and-comparison.jpg" aria-label="Векторные поля и проблема сравнения — наглядное введение">
    <source src="../assets/video/vector-fields-and-comparison.mp4" type="video/mp4">
    <track kind="subtitles" srclang="ru" label="Русские" src="../assets/video/vector-fields-and-comparison.ru.vtt">
    <track kind="chapters" srclang="ru" label="Части ролика" src="../assets/video/vector-fields-and-comparison.chapters.vtt">
    Ваш браузер не поддерживает встроенное видео. Скачайте ролик по ссылке ниже.
  </video>
  <figcaption>Карта ветра, развёртка цилиндра и вращающиеся оси: как сравнивать стрелки в разных точках и выделять изменение вдоль поверхности. Наглядное введение перед чтением главы.</figcaption>
  <nav class="chapter-video-chapters" aria-label="Части видео">{''.join(buttons)}</nav>
  <p class="chapter-video-error" role="status" hidden></p>
  <p class="chapter-video-links"><a href="../assets/video/vector-fields-and-comparison.mp4" download>Скачать видео</a><a href="../assets/video/vector-fields-and-comparison.ru.srt" download>Субтитры</a></p>
</figure>
<!-- chapter-video:end -->'''
if '<!-- chapter-video:start -->' in source:
    source=re.sub(r'<!-- chapter-video:start -->.*?<!-- chapter-video:end -->',lambda _:block,source,flags=re.S)
else:
    match=re.search(r'<p\b[^>]*id="purpose"[^>]*>.*?</p>',source,re.S);assert match
    source=source[:match.end()]+'\n\n'+block+source[match.end():]
if '../assets/chapter-video.css' not in source:
    source=source.replace('</head>','<link rel="stylesheet" href="../assets/chapter-video.css"><script defer src="../assets/chapter-video.js"></script></head>',1)
temp=chapter.with_name(chapter.name+'.tmp');temp.write_text(source);temp.replace(chapter)
(out/'installation-report.json').write_text(json.dumps(dict(book_root=str(book),chapter=str(chapter),
    files={dst:digest(media/dst) for dst in files.values()}),indent=2))
print(chapter)
