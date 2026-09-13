"""Local development headers matching the Ubuntu 24.04 runtime libraries."""
from pathlib import Path
import subprocess
import urllib.request

root=Path(__file__).resolve().parent/'.native'
root.mkdir(exist_ok=True)
packages=[
    ('p/pango1.0','libpango1.0-dev','1.52.1+ds-1build1'),
    ('h/harfbuzz','libharfbuzz-dev','8.3.0-2build2'),
    ('f/fribidi','libfribidi-dev','1.0.13-3build1'),
    ('libt/libthai','libthai-dev','0.1.29-2build1'),
    ('libd/libdatrie','libdatrie-dev','0.2.13-3build1'),
    ('g/graphite2','libgraphite2-dev','1.3.14-2ubuntu0.24.04.1'),
]
for folder,name,version in packages:
    filename=f'{name}_{version}_amd64.deb'
    dest=root/filename
    if not dest.exists():
        urllib.request.urlretrieve('https://archive.ubuntu.com/ubuntu/pool/main/'+folder+'/'+filename,dest)
    subprocess.run(['dpkg-deb','-x',str(dest),str(root)],check=True)
    print(name,flush=True)
for pc in root.glob('usr/lib/*/pkgconfig/*.pc'):
    pc.write_text(pc.read_text().replace('prefix=/usr','prefix='+str(root/'usr')))
for link in root.glob('usr/lib/*/*.so'):
    if link.is_symlink() and not link.exists():
        system=Path('/usr/lib/x86_64-linux-gnu')/link.readlink().name
        if system.exists():
            link.unlink();link.symlink_to(system)
