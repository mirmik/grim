"""Plan or migrate managed book names. Stop Grim before --apply; retains all IDs."""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import shutil
import sys
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.library import atomic_json, manifest, page_map
from server.naming import OPAQUE, PageText, apply_names, name_plan, readable_name, working_subdirectory
from server.versions import SOURCE, file_digest, source_file


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.urls=[]; self.ids=[]
    def handle_starttag(self, tag, attrs):
        for key,value in attrs:
            if value and key in ('href','src','poster','data','xlink:href'): self.urls.append(value)
            if value and key == 'id': self.ids.append(value)


def validate_copy(before, after, mapping):
    """All pre-existing local links still reach the same file and anchors survive."""
    excluded=working_subdirectory(before)
    for file in before.rglob('*'):
        relative=file.relative_to(before).as_posix()
        if Path(relative).parts[0]==excluded or not file.is_file() or any(p.startswith('.') for p in Path(relative).parts): continue
        target=after/mapping.get(relative,relative)
        assert target.is_file(),f'Missing migrated file: {target}'
        if file.suffix.lower() not in ('.html','.htm','.css','.svg','.js','.ncx','.md','.json','.txt','.vtt','.srt','.xhtml'):
            assert file_digest(file)==file_digest(target),f'Binary changed: {relative}'
        if file.suffix.lower() in ('.html','.htm','.xhtml'):
            old=Links();old.feed(file.read_text())
            new=Links();new.feed(target.read_text())
            assert old.ids==new.ids,f'Anchors changed: {relative}'
            old_text=PageText();old_text.feed(file.read_text())
            new_text=PageText();new_text.feed(target.read_text())
            assert old_text.text==new_text.text,f'Book text changed: {relative}'
            assert len(old.urls)==len(new.urls),f'Links disappeared: {relative}'
            for original,changed in zip(old.urls,new.urls):
                a,b=urlsplit(original),urlsplit(changed)
                if a.scheme or a.netloc or a.path.startswith('/'):continue
                old_path=posixpath.normpath(posixpath.join(posixpath.dirname(relative),unquote(a.path))) if a.path else relative
                if not (before/old_path).is_file():continue  # Existing legacy EPUB nav gaps.
                new_relative=mapping.get(relative,relative)
                new_path=posixpath.normpath(posixpath.join(posixpath.dirname(new_relative),unquote(b.path))) if b.path else new_relative
                assert new_path==mapping.get(old_path,old_path),f'Wrong target: {relative}: {original} -> {changed}'
                assert (after/new_path).is_file(),f'Broken link: {changed}'
                assert a.fragment==b.fragment,f'Fragment changed: {original}'
    old_pages=page_map(manifest(before));new_pages=page_map(manifest(after))
    assert old_pages.keys()==new_pages.keys(),'Page IDs changed'
    for key,page in old_pages.items():
        assert new_pages[key]['path']==mapping.get(page['path'],page['path'])


def plan(directory):
    registry=json.loads((directory/'library.json').read_text())
    entries=[];occupied={p.name.casefold() for p in (directory/'books').iterdir()}
    for entry in registry['books']:
        root=Path(entry['root']);root=root if root.is_absolute() else directory/root
        if root.parent!=directory/'books':continue
        if root.is_symlink() or any(p.is_symlink() for p in root.rglob('*')):
            raise ValueError(f'Symlink in managed book: {root}')
        copy_folder=working_subdirectory(root)
        source=root if copy_folder else root/SOURCE/'book'
        main=source if source.exists() else root
        title=manifest(main)['title']
        folder=root.name
        if OPAQUE.fullmatch(folder):
            base=readable_name(title);folder=base;index=2
            while folder.casefold() in occupied:
                folder=f'{base}-{index}';index+=1
            occupied.add(folder.casefold())
        entries.append({'id':entry['id'],'title':title,'before':root.name,'after':folder,
                        'copy_folder':copy_folder, 'working':name_plan(root/copy_folder if copy_folder else root),
                        'source':name_plan(source) if (root/SOURCE).exists() else None})
    return {'registry':registry,'books':entries}


def visible_working_layout(root):
    """Upgrade the old snapshot-in-hidden-folder layout on the staged book."""
    source=root/SOURCE/'book'
    if not source.is_dir():return
    from server.naming import available_path
    folder='рабочая-копия';number=2
    while (root/folder).exists() or (source/folder).exists():
        folder=f'рабочая-копия-{number}';number+=1
    working=root/folder;working.mkdir()
    for child in list(root.iterdir()):
        if child==working or child.name.startswith('.'):continue
        child.rename(working/child.name)
    notes=root/'.grim-notes.json'
    if notes.exists():notes.rename(working/notes.name)
    source_notes=root/'.grim-source-notes.json'
    if source_notes.exists():source_notes.rename(notes)
    for child in list(source.iterdir()):child.rename(root/child.name)
    source.rmdir()
    index=json.loads((root/SOURCE/'index.json').read_text())
    index.update(format=2,working_directory=folder,working_name='Рабочая копия')
    atomic_json(root/SOURCE/'index.json',index)
    for relative in index['files']:source_file(root,relative)
    manifest(working)


def migrate(directory):
    data=plan(directory)
    stamp=datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S-%f')
    backup=directory/'backups'/f'readable-names-{stamp}'
    backup.mkdir(parents=True,exist_ok=False);backup.chmod(0o700)
    shutil.copy2(directory/'library.json',backup/'library.json')
    stage=backup/'prepared';stage.mkdir()
    original=backup/'original';original.mkdir()
    for entry in data['books']:
        root=directory/'books'/entry['before']
        dest=stage/entry['after']
        shutil.copytree(root,original/entry['before'])
        if (root/SOURCE).exists():
            index=json.loads((root/SOURCE/'index.json').read_text())
            for relative in index['files']:source_file(root,relative)
        shutil.copytree(root,dest)
        copy_folder=entry['copy_folder']
        working_before=root/copy_folder if copy_folder else root
        working_after=dest/copy_folder if copy_folder else dest
        apply_names(working_after,entry['working'])
        validate_copy(working_before,working_after,entry['working'])
        if entry['source'] is not None:
            source_before=root if copy_folder else root/SOURCE/'book'
            source_after=dest if copy_folder else dest/SOURCE/'book'
            apply_names(source_after,entry['source'])
            validate_copy(source_before,source_after,entry['source'])
            index=json.loads((dest/SOURCE/'index.json').read_text())
            index['files']={entry['source'].get(relative,relative):file_digest(source_after/entry['source'].get(relative,relative))
                            for relative in index['files']}
            index.setdefault('path_migrations',[]).append({'at':stamp,'renamed':entry['source']})
            atomic_json(dest/SOURCE/'index.json',index)
            for relative in index['files']:source_file(dest,relative)
        visible_working_layout(dest)
        atomic_json(dest/'.grim-book.json',{'id':entry['id']})
    atomic_json(backup/'rename-plan.json',data)
    # Abort if an external editor/sync changed anything during preparation.
    def hashes(root):return {p.relative_to(root).as_posix():file_digest(p) for p in root.rglob('*') if p.is_file()}
    for entry in data['books']:
        assert hashes(directory/'books'/entry['before'])==hashes(original/entry['before']), 'Concurrent book edit; migration not published'
    assert json.loads((directory/'library.json').read_text())==data['registry'],'Concurrent registry edit'
    moved=[];retired=backup/'retired';retired.mkdir()
    try:
        for entry in data['books']:
            root=directory/'books'/entry['before'];dest=directory/'books'/entry['after']
            root.rename(retired/entry['before']);moved.append(entry)
            (stage/entry['after']).rename(dest)
        by_id={entry['id']:entry for entry in data['books']}
        for entry in data['registry']['books']:
            if entry['id'] in by_id:entry['root']='books/'+by_id[entry['id']]['after']
        atomic_json(directory/'library.json',data['registry'])
    except Exception:
        for entry in reversed(moved):
            dest=directory/'books'/entry['after']
            if dest.exists():shutil.move(dest,stage/entry['after'])
            (retired/entry['before']).rename(directory/'books'/entry['before'])
        shutil.copy2(backup/'library.json',directory/'library.json')
        raise
    # Retired directories are the exact pre-migration files; keep one backup copy.
    shutil.rmtree(original)
    stage.rmdir()
    print(json.dumps({'backup':str(backup),'books':len(data['books']),
                      'renamed_files':sum(len(e['working'])+len(e['source'] or {}) for e in data['books'])},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,default=Path.home()/'.grim')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();directory=args.library.expanduser().resolve()
    if args.apply:migrate(directory)
    else:print(json.dumps(plan(directory),ensure_ascii=False,indent=2))
