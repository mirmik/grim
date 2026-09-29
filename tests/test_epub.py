import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.epub import EpubError, MIN_PAGE_CHARS, PAGE_CHARS, import_epub, parse_xml, split_body, text_size
from server.library import page_map
from epub_fixture import epub_bytes


@pytest.mark.parametrize('epub2', [False, True])
def test_import_preserves_content_resources_and_cross_part_links(tmp_path, epub2):
    root = import_epub(epub_bytes(epub2=epub2), tmp_path / 'books')
    book = json.loads((root / 'book.json').read_text())
    pages = list(page_map(book).values())
    assert book['title'] == 'Проверка EPUB' and book['subtitle'] == 'Автор'
    assert book['pages'][0]['title'] == ('Глава из NCX' if epub2 else 'Глава из оглавления')
    chapters = [p for p in pages if 'chapter-grim-' in p['path']]
    assert len(chapters) >= 3
    contents = [(root / p['path']).read_text() for p in chapters]
    merged = ''.join(contents)
    for i in range(36):
        assert merged.count(f'Абзац {i:03d}.') == 1
    assert merged.count('Последний абзац.') == 1
    assert '<svg' in contents[0] and '<mfrac>' in contents[0]
    assert '<figcaption>Подпись к рисунку</figcaption>' in contents[0]
    assert '<table id="table">' in contents[0]
    assert 'href="styles/book.css"' in contents[0]
    assert 'src="images/picture.svg"' in contents[0]
    assert 'href="' + Path(chapters[-1]['path']).name + '#end"' in contents[0]
    assert 'href="chapter-grim-001.html#intro"' in contents[-1]
    assert 'href="notes-grim-001.html#note"' in contents[0]
    assert (root / 'content/OEBPS/styles/book.css').read_text().endswith('url("../images/picture.svg"); }')
    assert (root / 'content/OEBPS/images/picture.svg').is_file()
    assert not list((tmp_path / 'books').glob('.epub-*'))


def test_split_nested_wrappers_and_large_atomic_blocks():
    body = ET.fromstring('<body><div class="chapter" id="c"><section><h1>Title</h1><p>A</p><p>B</p><table><tr><td>' + 'x' * 100 + '</td></tr></table><p>C</p></section></div></body>')
    parts = split_body(body, 8)
    assert ''.join(''.join(p.itertext()) for p in parts) == ''.join(body.itertext())
    assert all(p.find('div/section') is not None for p in parts)
    assert sum(len(list(p.iter('table'))) for p in parts) == 1
    assert '<h1>Title</h1><p>A</p>' in ET.tostring(parts[0], encoding='unicode')
    assert sum(el.get('id') == 'c' for p in parts for el in p.iter()) == 1


def test_sibling_containers_remain_distinct():
    body = ET.fromstring('<body><div class="box"><p>One</p></div><div class="box"><p>Two</p></div></body>')
    parts = split_body(body, 12000)
    assert len(parts) == 1 and len(parts[0].findall('div')) == 2
    assert ET.tostring(parts[0]) == ET.tostring(body)


def test_short_introduction_stays_with_subheading_even_before_large_paragraph():
    intro = '<h1>Chapter</h1><p>' + 'A' * 900 + '</p>'
    body = ET.fromstring('<body>' + intro + '<h2>Section</h2><p>' + 'B' * 13000 + '</p><h2>Next</h2><p>End</p></body>')
    parts = split_body(body, 12000)
    assert len(parts) == 2
    assert parts[0].find('h1').text == 'Chapter'
    assert parts[0].find('h2').text == 'Section'
    assert 'B' * 13000 in ''.join(parts[0].itertext())
    assert parts[1].find('h2').text == 'Next'


def test_whitespace_does_not_make_a_title_page_long():
    body = ET.fromstring('<body><h1>Chapter</h1><p>' + '\n ' * 2000 + 'Intro</p><h2>Section</h2><p>Content</p></body>')
    assert len(split_body(body, 12000)) == 1


def test_nested_spans_do_not_make_the_entire_chapter_indivisible():
    paragraphs = ''.join(f'<p id="p{i}">{i:02d} ' + 'word ' * 180 + '</p>' for i in range(35))
    body = ET.fromstring('<body><span><span id="chapter"><div class="title"><p>Chapter</p></div>' + paragraphs + '</span></span></body>')
    parts = split_body(body, PAGE_CHARS, {'chapter'})
    assert len(parts) >= 5
    assert all(MIN_PAGE_CHARS <= text_size(part) <= PAGE_CHARS for part in parts[:-1])
    assert all(len(part.findall('.//p')) > 1 for part in parts)
    assert ''.join(''.join(part.itertext()) for part in parts) == ''.join(body.itertext())
    assert sum(el.get('id') == 'chapter' for part in parts for el in part.iter()) == 1
    assert all(part.find('span/span') is not None for part in parts)


def test_heading_after_brief_introduction_waits_for_minimum_page_size():
    body = ET.fromstring('<body><h1>Chapter</h1><p>' + 'x' * 3000 + '</p><h2>Section</h2><p>' + 'y' * 2500 + '</p><h2>Next</h2><p>Text</p></body>')
    parts = split_body(body, PAGE_CHARS)
    assert len(parts) == 2
    assert [el.text for el in parts[0].iter('h2')] == ['Section']
    assert parts[1].find('h2').text == 'Next'


def test_short_spine_documents_join_with_rebased_links_resources_and_ids(tmp_path):
    opf = '''<package><metadata><title>Joined</title></metadata><manifest>
      <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
      <item id="intro" href="intro.xhtml" media-type="application/xhtml+xml"/>
      <item id="small" href="part/small.xhtml" media-type="application/xhtml+xml"/>
      <item id="next" href="part/next.xhtml" media-type="application/xhtml+xml"/>
      </manifest><spine><itemref idref="cover"/><itemref idref="intro"/><itemref idref="small"/><itemref idref="next"/></spine></package>'''
    extra = {
        'OEBPS/package.opf': opf,
        'OEBPS/cover.xhtml': '<html><body><img src="images/picture.svg"/></body></html>',
        'OEBPS/intro.xhtml': '<html><head><link rel="stylesheet" href="styles/book.css"/></head><body><h1 id="part">Chapter</h1><p>Intro</p><a href="part/next.xhtml#part">Next heading</a><a href="part/next.xhtml">Next document</a></body></html>',
        'OEBPS/part/small.xhtml': '<html><body><h2>Small subsection</h2></body></html>',
        'OEBPS/part/next.xhtml': '<html lang="ru"><head><style>.figure{background:url(../images/picture.svg)}</style><link rel="stylesheet" href="../styles/book.css"/></head><body class="chapter"><h2 id="part">Subsection</h2><img src="../images/picture.svg" srcset="../images/picture.svg 1x, ../images/picture.svg 2x"/><p style="background:url(../images/picture.svg)">' + 'Text ' * 500 + '</p><a href="#part">Self</a><a href="../intro.xhtml#part">Back</a></body></html>',
    }
    root = import_epub(epub_bytes(extra=extra), tmp_path / 'books')
    pages = list(page_map(json.loads((root / 'book.json').read_text())).values())
    assert len(pages) == 2  # Image-only cover remains a separate page.
    assert pages[1]['title'] == 'Chapter'
    markup = (root / pages[1]['path']).read_text()
    assert 'Small subsection' in markup and 'Subsection' in markup and markup.count('Text ') == 500
    assert 'href="intro-grim-001.html#grim-2-part"' in markup
    assert 'href="intro-grim-001.html#grim-source-2"' in markup
    assert 'href="intro-grim-001.html#part"' in markup
    assert markup.count('id="part"') == 1
    assert 'src="images/picture.svg"' in markup
    assert 'srcset="images/picture.svg 1x, images/picture.svg 2x"' in markup
    assert 'url("images/picture.svg")' in markup
    assert markup.count('href="styles/book.css"') == 1
    metadata = json.loads((root / 'epub-import.json').read_text())
    assert metadata['min_page_chars'] == MIN_PAGE_CHARS
    assert metadata['pages'][1]['sources'] == ['OEBPS/intro.xhtml', 'OEBPS/part/small.xhtml', 'OEBPS/part/next.xhtml']


def test_standard_xhtml_entities_without_external_dtd():
    root = parse_xml(b'<!DOCTYPE html SYSTEM "http://invalid.example/xhtml.dtd"><html><body><p>A&nbsp;B &amp; &lt; &mdash;</p></body></html>', 'test.xhtml')
    assert ''.join(root.itertext()) == 'A\u00a0B & < \u2014'


@pytest.mark.parametrize('extra', [
    {'../escape': 'bad'}, {'/absolute': 'bad'}, {'OEBPS/../escape': 'bad'},
    {'META-INF/encryption.xml': '<encryption><EncryptedData/></encryption>'},
    {'OEBPS/chapter.xhtml': '<broken'},
    {'OEBPS/chapter.xhtml': '<!DOCTYPE html [<!ENTITY boom "bad">]><html><body>&boom;</body></html>'},
])
def test_failed_import_leaves_no_book(tmp_path, extra):
    directory = tmp_path / 'books'
    with pytest.raises(EpubError):
        import_epub(epub_bytes(extra=extra), directory)
    assert list(directory.iterdir()) == []
    assert not (tmp_path / 'escape').exists()


def test_bad_zip_and_limits(tmp_path, monkeypatch):
    with pytest.raises(EpubError):
        import_epub(b'not a zip', tmp_path)
    monkeypatch.setattr('server.epub.MAX_EXPANDED', 100)
    with pytest.raises(EpubError, match='распаковки'):
        import_epub(epub_bytes(), tmp_path)
    assert not list(tmp_path.iterdir())


def test_import_api_authentication_serving_and_restart(tmp_path):
    directory = tmp_path / 'library'
    with TestClient(create_app(library_dir=directory)) as client:
        route = '/api/library/import-epub'
        assert client.post(route, content=epub_bytes()).status_code == 403
        token = client.get('/api/library').json()['writer_token']
        headers = {'X-Grim-Viewer': token, 'Content-Type': 'application/epub+zip'}
        bad = client.post(route, content=b'broken', headers=headers)
        assert bad.status_code == 422
        response = client.post(route, content=epub_bytes(), headers=headers)
        assert response.status_code == 200, response.text
        entry = response.json()
        book = client.get('/api/books/' + entry['id']).json()
        path = next(iter(page_map(book).values()))['path']
        page = client.get(f'/book/{entry["id"]}/{path}')
        assert 'parent.postMessage' in page.text and '<mfrac>' in page.text
        assert client.get(f'/book/{entry["id"]}/content/OEBPS/images/picture.svg').status_code == 200
    with TestClient(create_app(library_dir=directory)) as client:
        assert any(b['id'] == entry['id'] for b in client.get('/api/library').json()['books'])
        assert client.get('/api/books/' + entry['id']).json()['pages'] == book['pages']


def test_upload_limit_checked_on_stream(tmp_path, monkeypatch):
    monkeypatch.setattr('server.app.MAX_UPLOAD', 16)
    with TestClient(create_app(library_dir=tmp_path)) as client:
        token = client.get('/api/library').json()['writer_token']
        response = client.post('/api/library/import-epub', content=b'x' * 17, headers={'X-Grim-Viewer': token})
        assert response.status_code == 413
        assert not (tmp_path / 'books').exists()
