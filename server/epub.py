"""One-way EPUB import into ordinary, independently editable Grim HTML pages."""
from copy import deepcopy
import hashlib
from html.entities import html5
import io
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import tempfile
from urllib.parse import quote, unquote, urlsplit, urlunsplit
import uuid
import xml.etree.ElementTree as ET
import zipfile

from .library import atomic_json, manifest

MAX_UPLOAD = 64 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_MEMBER = 32 * 1024 * 1024
MAX_MEMBERS = 5000
PAGE_CHARS = 7000
MIN_PAGE_CHARS = 4000
CONTAINERS = {'body', 'div', 'section', 'article', 'main', 'span'}
WRAPPER_ID = '{urn:grim:import}wrapper'
HEADINGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
DOCUMENT_TYPES = {'application/xhtml+xml', 'text/html'}


class EpubError(ValueError):
    pass


def local(name):
    return name.rsplit('}', 1)[-1]


def parse_xml(data, name):
    # EPUB's ordinary external DOCTYPE needs no fetching. Entity declarations,
    # including internal expansion attacks, are not part of this import format.
    if re.search(br'<!\s*ENTITY\b', data.replace(b'\x00', b''), re.I):
        raise EpubError(f'Объявления XML-сущностей не поддерживаются: {name}')
    # XHTML books often use the standard HTML named entities from their DTD.
    # Expand only that built-in list to numeric references, never an external DTD.
    def entity(match):
        value = html5.get(match[1].decode('ascii') + ';')
        return ''.join(f'&#{ord(c)};' for c in value).encode('ascii') if value else match[0]
    data = re.sub(br'&([A-Za-z][A-Za-z0-9]+);', entity, data)
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError) as exc:
        raise EpubError(f'Не удалось прочитать XML/XHTML: {name}') from exc
    pending = [(root, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > 128:
            raise EpubError(f'Слишком глубокая вложенность XML: {name}')
        pending.extend((child, depth + 1) for child in node)
    return root


def member_path(base, href):
    url = urlsplit(href)
    if url.scheme or url.netloc:
        raise EpubError(f'Внешний файл в составе EPUB: {href}')
    path = unquote(url.path)
    path = posixpath.normpath(posixpath.join(posixpath.dirname(base), path))
    if path.startswith(('/', '../')) or path in ('.', '..') or '\\' in path or '\x00' in path:
        raise EpubError(f'Недопустимый путь EPUB: {href}')
    return path


def archive_members(archive):
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > MAX_EXPANDED:
        raise EpubError('EPUB слишком велик после распаковки')
    members = {}
    for item in infos:
        name = item.filename
        parts = name.rstrip('/').split('/')
        if (not name or name.startswith('/') or any(p in ('', '.', '..') for p in parts)
                or any(c in name for c in ('\\', '\x00', '?', '#', '%'))
                or any(ord(c) < 32 for c in name)
                or stat.S_ISLNK(item.external_attr >> 16)):
            raise EpubError(f'Недопустимый путь в архиве: {name}')
        if item.file_size > MAX_MEMBER or item.flag_bits & 1:
            raise EpubError('Зашифрованный или слишком большой файл внутри EPUB')
        if item.is_dir():
            continue
        if name in members:
            raise EpubError(f'Повторяющийся путь в EPUB: {name}')
        members[name] = item
    return members


def normalize_document(root):
    """Keep HTML, SVG and MathML structure; drop active imported book code."""
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        node.tag = local(node.tag)
        attrs = {}
        for key, value in node.attrib.items():
            name = local(key)
            if name.lower().startswith('on') or name in ('srcdoc', 'base'):
                continue
            if key.startswith('{http://www.w3.org/1999/xlink}'):
                name = 'xlink:' + name
            elif key.startswith('{http://www.idpf.org/2007/ops}'):
                name = 'epub:' + name
            attrs[name] = value
        node.attrib = attrs
    for parent in root.iter():
        for child in list(parent):
            if child.tag in {'script', 'iframe', 'object', 'embed', 'base'} or (
                    child.tag == 'meta' and child.get('http-equiv')):
                # Preserve following book text even when dropping an active node.
                index = list(parent).index(child)
                if child.tail:
                    if index:
                        parent[index - 1].tail = (parent[index - 1].tail or '') + child.tail
                    else:
                        parent.text = (parent.text or '') + child.tail
                parent.remove(child)
    return root


def text_size(node):
    return len(' '.join(''.join(node.itertext()).split()))


def units(node):
    """Split structural wrappers, keeping each semantic leaf and its ancestry."""
    if node.tag not in CONTAINERS or not len(node):
        return [deepcopy(node)]
    result = []
    attrs = {**node.attrib, WRAPPER_ID: str(id(node))}
    if node.text and node.text.strip():
        wrapper = ET.Element(node.tag, attrs)
        wrapper.text = node.text
        result.append(wrapper)
    for child in node:
        for piece in units(child):
            wrapper = ET.Element(node.tag, attrs)
            wrapper.append(piece)
            result.append(wrapper)
    if result:
        result[-1].tail = node.tail
    return result or [deepcopy(node)]


def first_heading(node):
    return next((el for el in node.iter() if el.tag in HEADINGS), None)


def split_body(body, target, boundaries=()):
    pieces = units(body)
    minimum = min(MIN_PAGE_CHARS, target)
    groups, group, size = [], [], 0
    seen_boundaries = set()
    previous_heading = False
    for piece in pieces:
        amount = text_size(piece)
        heading = first_heading(piece)
        boundary_ids = {el.get('id') for el in piece.iter() if el.get('id') in boundaries}
        # An EPUB TOC anchor may wrap a whole chapter in nested spans. Only
        # its first appearance starts a section, not every cloned wrapper.
        section_start = bool(boundary_ids - seen_boundaries)
        seen_boundaries.update(boundary_ids)
        # A heading stays with its following paragraph, including at a size cut.
        if group and size >= minimum and not previous_heading and (size + amount > target or heading is not None or section_start):
            groups.append(group)
            group, size = [], 0
        group.append(piece)
        size += amount
        previous_heading = heading is not None or section_start
    if group:
        groups.append(group)
    # Recombine adjacent ancestry wrappers so publisher layout survives splitting.
    def merge(parent, incoming):
        if len(parent) and incoming.tag in CONTAINERS:
            previous = parent[-1]
            if previous.tag == incoming.tag and previous.attrib == incoming.attrib and not previous.tail and not incoming.text:
                for child in list(incoming):
                    merge(previous, child)
                previous.tail = incoming.tail
                return
        parent.append(deepcopy(incoming))
    result = []
    seen_ids = set()
    for group in groups:
        container = ET.Element('root')
        for piece in group:
            merge(container, piece)
        page_body = container[0]
        for el in page_body.iter():
            el.attrib.pop(WRAPPER_ID, None)
            identity = el.get('id')
            if identity:
                if identity in seen_ids:
                    del el.attrib['id']
                else:
                    seen_ids.add(identity)
        result.append(page_body)
    return result


def join_short_pages(pages, reading_sources, minimum):
    """Spine file boundaries are not mandatory reading-page boundaries."""
    result = []
    for page in pages:
        size = text_size(page['body'])
        if (result and 0 < result[-1]['text_size'] < minimum and size > 0
                and page['source'] in reading_sources
                and all(s['source'] in reading_sources for s in result[-1]['segments'])):
            result[-1]['segments'].append(page)
            result[-1]['text_size'] += size
        else:
            result.append({**page, 'segments': [page], 'text_size': size})
    return result


def rewrite_css(css, rewrite):
    # Stylesheet files stay in place; only inline CSS moves with a merged page.
    css = re.sub(r'''url\(\s*(["']?)(.*?)\1\s*\)''',
                 lambda m: 'url("' + rewrite(m[2].strip()).replace('"', '%22') + '")', css, flags=re.I)
    return re.sub(r'''(@import\s+)(["'])(.*?)\2''',
                  lambda m: m[1] + m[2] + rewrite(m[3]) + m[2], css, flags=re.I)


def rewrite_srcset(value, rewrite):
    result = []
    remaining = value.strip()
    while remaining:
        # Data URLs contain commas; their candidate ends at whitespace.
        pattern = r'\S+' if remaining.lower().startswith('data:') else r'[^\s,]+'
        match = re.match(pattern, remaining)
        if not match:
            remaining = remaining[1:].lstrip()
            continue
        url = match[0]
        remaining = remaining[len(url):].lstrip()
        descriptor, separator, remaining = remaining.partition(',')
        result.append(rewrite(url) + (' ' + descriptor.strip() if descriptor.strip() else ''))
        if not separator:
            break
        remaining = remaining.lstrip()
    return ', '.join(result)


def navigation(archive, items, spine):
    """Read EPUB 3 nav or EPUB 2 NCX labels in their original hierarchy order."""
    entries = []
    nav = next((item for item in items.values() if 'nav' in item['properties']), None)
    if nav:
        root = parse_xml(archive.read(nav['path']), nav['path'])
        toc = next((el for el in root.iter() if local(el.tag) == 'nav' and
                    'toc' in el.get('{http://www.idpf.org/2007/ops}type', '').split()), None)
        if toc is not None:
            for el in toc.iter():
                if local(el.tag) == 'a' and el.get('href'):
                    entries.append((nav['path'], el.get('href'), ' '.join(''.join(el.itertext()).split())))
    if not entries:
        ncx = items.get(spine.get('toc')) or next((i for i in items.values() if i['type'] == 'application/x-dtbncx+xml'), None)
        if ncx:
            root = parse_xml(archive.read(ncx['path']), ncx['path'])
            for point in root.iter():
                if local(point.tag) != 'navPoint':
                    continue
                content = next((el for el in point if local(el.tag) == 'content'), None)
                label = next((el for el in point if local(el.tag) == 'navLabel'), None)
                if content is not None and label is not None:
                    entries.append((ncx['path'], content.get('src', ''), ' '.join(''.join(label.itertext()).split())))
    return [(member_path(base, href), unquote(urlsplit(href).fragment), title) for base, href, title in entries]


def build_book(data, root, target_chars=PAGE_CHARS):
    if len(data) > MAX_UPLOAD:
        raise EpubError('Максимальный размер EPUB — 64 МБ')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive_members(archive)
        if archive.read('mimetype').strip() != b'application/epub+zip':
            raise EpubError('Файл не является EPUB')
        if 'META-INF/encryption.xml' in members:
            encryption = parse_xml(archive.read('META-INF/encryption.xml'), 'encryption.xml')
            if any(local(el.tag) == 'EncryptedData' for el in encryption.iter()):
                raise EpubError('EPUB содержит зашифрованные ресурсы (включая защищённые шрифты); такой импорт пока не поддерживается')
        container = parse_xml(archive.read('META-INF/container.xml'), 'container.xml')
        package = next((el.get('full-path') for el in container.iter() if local(el.tag) == 'rootfile'), None)
        if not package or package not in members:
            raise EpubError('Не найдено описание книги EPUB')
        opf = parse_xml(archive.read(package), package)
        metadata = next((el for el in opf if local(el.tag) == 'metadata'), [])
        title = next((' '.join(''.join(el.itertext()).split()) for el in metadata if local(el.tag) == 'title'), '') or 'Книга EPUB'
        authors = [' '.join(''.join(el.itertext()).split()) for el in metadata if local(el.tag) == 'creator']
        items = {}
        for el in opf.iter():
            if local(el.tag) == 'item':
                path = member_path(package, el.get('href', ''))
                if path not in members:
                    raise EpubError(f'В EPUB отсутствует файл: {path}')
                items[el.get('id')] = {'path': path, 'type': el.get('media-type', ''), 'properties': el.get('properties', '').split()}
        spine = next((el for el in opf if local(el.tag) == 'spine'), None)
        if spine is None:
            raise EpubError('В EPUB отсутствует порядок чтения (spine)')
        order = []
        for ref in spine:
            if local(ref.tag) != 'itemref':
                continue
            item = items.get(ref.get('idref'))
            if not item or item['type'] not in DOCUMENT_TYPES:
                raise EpubError('В порядке чтения EPUB есть неподдерживаемый документ')
            if item['path'] not in order:
                order.append(item['path'])
        if not order:
            raise EpubError('EPUB не содержит глав для чтения')
        reading_sources = set(order)
        nav = navigation(archive, items, spine)
        documents = {i['path'] for i in items.values() if i['type'] in DOCUMENT_TYPES}
        # Non-spine documents can contain footnotes linked from the main text.
        order.extend(sorted(documents - set(order)))
        pages = []
        used_paths = set(members)
        for source in order:
            doc = normalize_document(parse_xml(archive.read(source), source))
            body = next((el for el in doc if el.tag == 'body'), None)
            head = next((el for el in doc if el.tag == 'head'), None)
            if body is None:
                raise EpubError(f'Нет body в главе EPUB: {source}')
            source_labels = {fragment: label for path, fragment, label in nav if path == source and fragment}
            parts = split_body(body, target_chars, source_labels)
            base_title = next((label for path, _, label in nav if path == source and label), '')
            heading = first_heading(body)
            base_title = base_title or (''.join(heading.itertext()).strip() if heading is not None else '') or PurePosixPath(source).stem
            for number, part in enumerate(parts, 1):
                # Reserved names are checked against every original archive path.
                path = str(PurePosixPath(source).with_suffix('')) + f'-grim-{number:03d}.html'
                while path in used_paths:
                    path = path[:-5] + '-page.html'
                used_paths.add(path)
                heading = first_heading(part)
                label = ''.join(heading.itertext()).strip() if heading is not None else ''
                label = label or next((source_labels[el.get('id')] for el in part.iter() if el.get('id') in source_labels), '')
                label = label or (base_title if number == 1 else f'{base_title} — {number}')
                pages.append({'id': f'page-{len(pages) + 1:04d}', 'source': source, 'path': path, 'title': label, 'body': part,
                              'head': deepcopy(head) if head is not None else ET.Element('head'),
                              'attrs': doc.attrib.copy(), 'chapter': base_title})

        pages = join_short_pages(pages, reading_sources, min(MIN_PAGE_CHARS, target_chars))
        starts, anchors = {}, {}
        for page in pages:
            # Two source files may use the same IDs. Keep their destinations
            # distinct after joining, including links to the start of a file.
            reserved = {el.get('id') for segment in page['segments'] for el in segment['body'].iter() if el.get('id')}
            used = set()
            def unique_id(candidate):
                while candidate in reserved:
                    candidate += '-section'
                reserved.add(candidate)
                return candidate
            for index, segment in enumerate(page['segments']):
                for el in segment['body'].iter():
                    identity = el.get('id')
                    if identity:
                        renamed = unique_id(f'grim-{index}-{identity}') if identity in used else identity
                        used.add(renamed)
                        el.set('id', renamed)
                        anchors.setdefault((segment['source'], identity), (page['path'], renamed))
                start = ''
                if index:
                    start = unique_id(f'grim-source-{index}')
                    segment['start_anchor'] = start
                starts.setdefault(segment['source'], (page['path'], start))

        def rewrite(value, source, destination):
            url = urlsplit(value)
            if url.scheme or url.netloc or not value:
                return value
            resolved = member_path(source, url.path) if url.path else source
            fragment = unquote(url.fragment)
            if fragment:
                target, fragment = anchors.get((resolved, fragment), (starts.get(resolved, (resolved, ''))[0], fragment))
            else:
                target, fragment = starts.get(resolved, (resolved, ''))
            relative = posixpath.relpath(target, posixpath.dirname(destination) or '.')
            if ':' in relative.split('/')[0]:
                relative = './' + relative
            # Match encodeURIComponent in the viewer's path comparison.
            return urlunsplit(('', '', quote(relative, safe="/!~*'()"), url.query, quote(fragment, safe="/!~*'()")))

        for page in pages:
            head = ET.Element('head')
            body = page['body']
            seen_head = set()
            for index, segment in enumerate(page['segments']):
                rebase = lambda value: rewrite(value, segment['source'], page['path'])
                for subtree in (segment['head'], segment['body']):
                    for el in subtree.iter():
                        for attribute in ('href', 'src', 'poster', 'data', 'xlink:href'):
                            if attribute in el.attrib:
                                el.set(attribute, rebase(el.get(attribute)))
                        if 'srcset' in el.attrib:
                            el.set('srcset', rewrite_srcset(el.get('srcset'), rebase))
                        if 'style' in el.attrib:
                            el.set('style', rewrite_css(el.get('style'), rebase))
                        if el.tag == 'style' and el.text:
                            el.text = rewrite_css(el.text, rebase)
                for el in segment['head']:
                    key = ET.tostring(el)
                    if key not in seen_head:
                        seen_head.add(key)
                        head.append(el)
                if index:
                    # Keep each body's own classes, language and styles on a
                    # wrapper, rather than flattening unrelated source trees.
                    wrapper = ET.Element('section', {key: value for key, value in segment['attrs'].items() if key in ('lang', 'dir')})
                    wrapper.set('id', segment['start_anchor'])
                    segment['body'].tag = 'section'
                    wrapper.append(segment['body'])
                    body.append(wrapper)
            for el in list(head):
                if el.tag in ('title', 'meta'):
                    head.remove(el)
            head.insert(0, ET.Element('meta', {'charset': 'utf-8'}))
            ET.SubElement(head, 'title').text = page['title']
            ET.SubElement(head, 'meta', {'name': 'viewport', 'content': 'width=device-width, initial-scale=1'})
            # Defaults precede publisher CSS; no forced width/height for figures.
            style = ET.Element('style')
            style.text = 'body{max-width:48rem;margin:0 auto;padding:2rem 1.25rem;line-height:1.65;overflow-wrap:break-word}img,svg,video{max-width:100%;height:auto}pre{overflow:auto}table{max-width:100%}'
            head.insert(1, style)
            document = ET.Element('html', page['attrs'])
            document.extend([head, body])
            output = root / 'content' / page['path']
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text('<!DOCTYPE html>\n' + ET.tostring(document, encoding='unicode', method='html'), encoding='utf-8')
        # Keep original resource paths: CSS url()/@import, srcset and SVG resource
        # references therefore remain relative to the same directory as before.
        for path, info in members.items():
            if path in documents or path == 'mimetype' or path.startswith('META-INF/') or path == package:
                continue
            output = root / 'content' / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.read(info))
        toc = []
        for source in order:
            chapter_pages = [p for p in pages if p['source'] == source]
            nodes = [{'id': p['id'], 'title': p['title'], 'path': 'content/' + p['path']} for p in chapter_pages]
            if len(nodes) == 1:
                toc.extend(nodes)
            elif nodes:
                toc.append({'id': f'chapter-{len(toc) + 1:04d}', 'title': chapter_pages[0]['chapter'], 'children': nodes})
        atomic_json(root / 'book.json', {'title': title, 'subtitle': ', '.join(authors), 'pages': toc})
        atomic_json(root / 'epub-import.json', {'format': 'epub', 'sha256': hashlib.sha256(data).hexdigest(),
                    'target_chars': target_chars, 'min_page_chars': min(MIN_PAGE_CHARS, target_chars),
                    'pages': [{'path': 'content/' + p['path'], 'source': p['source'],
                               'sources': list(dict.fromkeys(s['source'] for s in p['segments']))} for p in pages],
                    'navigation': [{'source': p, 'fragment': f, 'title': t} for p, f, t in nav]})
        manifest(root)


def import_epub(data, books_directory):
    """Publish only a complete folder; failed imports never enter discovery."""
    books_directory.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.epub-', dir=books_directory))
    try:
        try:
            build_book(data, stage)
        except (zipfile.BadZipFile, KeyError, RuntimeError, NotImplementedError) as exc:
            raise EpubError('Повреждённый или неподдерживаемый архив EPUB') from exc
        destination = books_directory / uuid.uuid4().hex
        stage.rename(destination)
        return destination
    finally:
        if stage.exists():
            shutil.rmtree(stage)
