"""Readable disk names; book/page IDs remain independent of display names."""
import json
from html import unescape
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import posixpath
import re
import unicodedata
from urllib.parse import quote, unquote, urlsplit, urlunsplit

UUID = r'[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}'
OPAQUE = re.compile(r'^(?:[a-fA-F0-9]{24,}|(?:ch(?:apter)?|page|part|section)?[\d_-]+)$', re.I)
TEXT_TYPES = {'.html', '.htm', '.xhtml', '.css', '.js', '.svg', '.ncx', '.md', '.txt', '.vtt', '.srt'}


def readable_name(title, fallback='книга'):
    name = unicodedata.normalize('NFC', title).lower()
    name = re.sub(r'[^\w\s-]', '', name, flags=re.U)
    name = re.sub(r'[_\s-]+', '-', name).strip('-') or fallback
    while len(name.encode('utf-8')) > 180:
        name = name[:-1]
    return name.rstrip('-')


def available_path(parent, name, *, directory=False):
    """Reserve a folder atomically, or choose a noncolliding staged destination."""
    index = 1
    while True:
        path = parent / (name if index == 1 else f'{name}-{index}')
        if directory:
            try:
                path.mkdir(parents=True, exist_ok=False)
                return path
            except FileExistsError:
                pass
        elif not path.exists():
            return path
        index += 1


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.body = False
        self.skip = 0
        self.text = []
    def handle_starttag(self, tag, attrs):
        if tag == 'body': self.body = True
        if tag in ('style', 'script'): self.skip += 1
    def handle_endtag(self, tag):
        if tag == 'body': self.body = False
        if tag in ('style', 'script'): self.skip = max(0, self.skip - 1)
    def handle_data(self, data):
        if self.body and not self.skip and data.strip(): self.text.append(' '.join(data.split()))


def page_title(root, page):
    title = page['title'].strip()
    if title.lower() == 'cover': return 'Обложка'
    if not title or OPAQUE.fullmatch(title):
        parser = PageText(); parser.feed((root / page['path']).read_text(encoding='utf-8'))
        title = next((text for text in parser.text if len(text) > 2), 'Раздел книги')[:110]
    return re.sub(r'\s+[—–]\s+(\d+)$', r' — часть \1', title)


def working_subdirectory(root):
    index=root/'.grim-source'/'index.json'
    if index.exists():
        data=json.loads(index.read_text())
        if data.get('format')==2:return data['working_directory']
    return None


def name_plan(root):
    from .library import manifest, page_map
    book = manifest(root)
    mapping = {}
    excluded=working_subdirectory(root)
    files = [p for p in root.rglob('*') if p.is_file() and p.relative_to(root).parts[0]!=excluded and not any(part.startswith('.') for part in p.relative_to(root).parts)]
    used = {p.relative_to(root).as_posix().casefold() for p in files}
    def assign(relative, stem):
        old = PurePosixPath(relative)
        base = readable_name(stem, 'файл')
        candidate = old.with_name(base + old.suffix.lower()).as_posix()
        index = 2
        while candidate.casefold() in used and candidate != relative:
            candidate = old.with_name(f'{base}-часть-{index}{old.suffix.lower()}').as_posix()
            index += 1
        used.add(candidate.casefold())
        if candidate != relative: mapping[relative] = candidate
    for page in page_map(book).values():
        stem = PurePosixPath(page['path']).stem
        if '-grim-' in stem or OPAQUE.fullmatch(stem):
            assign(page['path'], page_title(root, page))
    for file in files:
        relative = file.relative_to(root).as_posix()
        if relative in mapping: continue
        clean = re.sub(r'[-_]?' + UUID, '', file.stem)
        if clean != file.stem:
            assign(relative, clean or 'ресурс')
        elif OPAQUE.fullmatch(file.stem):
            assign(relative, {'.jpg':'иллюстрация', '.png':'иллюстрация', '.svg':'иллюстрация',
                              '.css':'стили', '.js':'скрипт', '.ttf':'шрифт', '.otf':'шрифт'}.get(file.suffix.lower(), 'ресурс'))
    return mapping


def rewritten_url(value, relative, mapping):
    try:
        url = urlsplit(value)
    except ValueError:
        return value
    if url.scheme or url.netloc or not url.path or url.path.startswith('/'):
        return value
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), unquote(url.path)))
    if resolved not in mapping: return value
    target = posixpath.relpath(mapping[resolved], posixpath.dirname(mapping.get(relative, relative)) or '.')
    return urlunsplit(('', '', quote(target, safe='/.-_~'), url.query, url.fragment))


def rewrite_references(text, relative, mapping):
    # Preserve HTML/JS bytes except literal URLs. IDs, text, scripts and layout
    # are not reserialized; directories stay in place, so dynamic bases survive.
    def quoted(match):
        return match[1] + rewritten_url(match[2], relative, mapping) + match[1]
    text = re.sub(r'''(["'])([^"'\n]*)\1''', quoted, text)
    def css(match):
        value = match[2].strip()
        changed = rewritten_url(value, relative, mapping)
        return match[1] + changed + match[3] if changed != value else match[0]
    text = re.sub(r'''(url\(\s*)([^"'()]*)(\s*\))''', css, text, flags=re.I)
    # Quoted srcset contains multiple URLs, unlike normal quoted attributes.
    from .epub import rewrite_srcset
    text = re.sub(r'''(\bsrcset\s*=\s*)(["'])(.*?)\2''',
                  lambda m: m[1]+m[2]+rewrite_srcset(m[3], lambda v: rewritten_url(v, relative, mapping))+m[2], text, flags=re.I)
    return text


def apply_names(root, mapping):
    """Operate on a staged copy only. The caller publishes/backs up atomically."""
    from .library import atomic_json, manifest
    if not mapping: return
    excluded=working_subdirectory(root)
    for file in list(root.rglob('*')):
        relative = file.relative_to(root).as_posix()
        if Path(relative).parts[0]==excluded or any(part.startswith('.') for part in Path(relative).parts) or not file.is_file(): continue
        if file.suffix.lower() in TEXT_TYPES:
            before = file.read_text(encoding='utf-8')
            after = rewrite_references(before, relative, mapping)
            if after != before: file.write_text(after, encoding='utf-8')
    book = json.loads((root / 'book.json').read_text())
    def visit(nodes):
        for node in nodes:
            if node.get('path') in mapping: node['path'] = mapping[node['path']]
            visit(node.get('children', []))
    visit(book['pages'])
    for relative, target in mapping.items():
        (root / relative).rename(root / target)
    atomic_json(root / 'book.json', book)
    metadata = root / 'epub-import.json'
    if metadata.exists():
        data = json.loads(metadata.read_text())
        for page in data.get('pages', []): page['path'] = mapping.get(page['path'], page['path'])
        atomic_json(metadata, data)
    manifest(root)
