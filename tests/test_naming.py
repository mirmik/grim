import json
import shutil
from pathlib import Path
from urllib.parse import unquote

import pytest

from server.library import Library, atomic_json, manifest, page_map
from server.naming import apply_names, name_plan, readable_name, rewritten_url
from server.versions import SOURCE, create_source, source_file, version_root, file_digest
from scripts.readable_book_names import migrate


def test_readable_folders_keep_ids_across_rename_sync_and_collisions(tmp_path):
    library=Library(tmp_path/'library',[])
    first=library.create('Понятная книга');second=library.create('Понятная книга')
    assert Path(first['root']).name=='понятная-книга'
    assert Path(second['root']).name=='понятная-книга-2'
    renamed=Path(first['root']).with_name('новое-название')
    Path(first['root']).rename(renamed)
    library.discover()
    assert library.root(first['id'])==renamed
    (library.directory/'library.json').unlink()
    peer=Library(library.directory,[])
    assert set(peer.entries)=={first['id'],second['id']}


def fixture_book(root):
    (root/'pages').mkdir(parents=True)
    (root/'fonts').mkdir()
    font='Times-400-12345678-1234-1234-1234-123456789abc.otf'
    (root/'fonts'/font).write_bytes(b'font binary')
    (root/'pages'/'ch1-grim-001.html').write_text('<html><body><p id="stable">Text</p><a href="ch2-grim-001.html?read=1#note">Note</a><img srcset="../fonts/'+font+' 1x"/></body></html>')
    (root/'pages'/'ch2-grim-001.html').write_text('<html><body><p id="note">Note</p><a href="ch1-grim-001.html#stable">Back</a></body></html>')
    (root/'style.css').write_text('@font-face{src:url(fonts/'+font+')}')
    atomic_json(root/'book.json',{'title':'Тестовая книга','pages':[
        {'id':'stable-one','title':'Первая глава','path':'pages/ch1-grim-001.html'},
        {'id':'stable-two','title':'Примечания','path':'pages/ch2-grim-001.html'}]})


def test_migration_preserves_snapshots_binary_data_ids_and_links(tmp_path):
    library=tmp_path/'library';books=library/'books';books.mkdir(parents=True)
    root=books/('a'*32);fixture_book(root)
    registry=Library(library,[])
    entry=next(iter(registry.entries.values()));book_id=entry['id']
    # Legacy layout from the first implementation: working root, hidden main.
    old_source=root/SOURCE/'book'
    shutil.copytree(root,old_source,ignore=shutil.ignore_patterns(SOURCE))
    atomic_json(root/SOURCE/'index.json',{'format':1,'files':{p.relative_to(old_source).as_posix():file_digest(p) for p in old_source.rglob('*') if p.is_file()}})
    (root/'pages/ch1-grim-001.html').write_text((root/'pages/ch1-grim-001.html').read_text().replace('Text','Working text'))
    migrate(library)
    restored=Library(library,[]);new=restored.root(book_id)
    assert new.name=='тестовая-книга'
    assert not root.exists()
    assert version_root(new,'working')==new/'рабочая-копия'
    assert 'Working text' in (new/'рабочая-копия/pages/первая-глава.html').read_text()
    assert 'Working text' not in source_file(new,'pages/первая-глава.html').read_text()
    html=unquote((new/'pages/первая-глава.html').read_text())
    assert 'href="примечания.html?read=1#note"' in html
    assert 'srcset="../fonts/times-400.otf 1x"' in html
    assert 'url(fonts/times-400.otf)' in (new/'style.css').read_text()
    assert (new/'fonts/times-400.otf').read_bytes()==b'font binary'
    assert set(page_map(manifest(new)))=={'stable-one','stable-two'}
    backup=next((library/'backups').iterdir())
    assert (backup/'retired'/root.name/'pages/ch1-grim-001.html').exists()
    assert json.loads((backup/'library.json').read_text())['books'][0]['id']==book_id
    # A second pass must preserve the new layout and immutable main hashes.
    migrate(library)
    assert source_file(new,'pages/первая-глава.html').is_file()
    assert 'Working text' in (version_root(new,'working')/'pages/первая-глава.html').read_text()


def test_names_are_safe_bounded_and_mapping_ignores_external_urls():
    assert readable_name('../Тест / книга? #')=='тест-книга'
    assert len(readable_name('я'*1000).encode())<=180
    mapping={'pages/old.html':'pages/новое.html'}
    for url in ('https://example.org/pages/old.html','data:image/svg+xml,abc','#local','/vendor/old.html'):
        assert rewritten_url(url,'pages/index.html',mapping)==url
    assert unquote(rewritten_url('old.html?q=1#anchor','pages/index.html',mapping))=='новое.html?q=1#anchor'
