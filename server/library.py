"""Durable folder registry. One local process owns it; no database or book copies."""
import json
import os
from pathlib import Path
import re
import uuid

from fastapi import HTTPException


def library_directory():
    return Path(os.environ.get('GRIM_LIBRARY', Path.home() / '.grim')).expanduser()


def safe_file(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        raise HTTPException(404, 'Файл не найден в папке книги')
    return candidate


def validate_manifest(data, root: Path):
    if not isinstance(data['title'], str) or not data['title'].strip():
        raise ValueError('Укажите title книги')
    seen = set()
    def visit(nodes):
        if not isinstance(nodes, list):
            raise ValueError('pages/children должны быть массивами')
        for node in nodes:
            if not isinstance(node['id'], str) or not node['id'] or node['id'] in seen:
                raise ValueError('ID узлов должны быть уникальными строками')
            if not isinstance(node['title'], str):
                raise ValueError('title узла должен быть строкой')
            seen.add(node['id'])
            if 'path' in node:
                path = node['path']
                if not isinstance(path, str) or any(c in path for c in ('?', '#', '\\')) or Path(path).is_absolute() or '..' in Path(path).parts:
                    raise ValueError('Пути страниц должны быть относительными')
                if safe_file(root, path).suffix.lower() not in ('.html', '.htm'):
                    raise ValueError('Страницы должны быть HTML')
            visit(node.get('children', []))
    visit(data['pages'])
    return data


def manifest(root: Path):
    try:
        data = json.loads(safe_file(root, 'book.json').read_text(encoding='utf-8'))
        return validate_manifest(data, root)
    except (KeyError, ValueError, TypeError, OSError, HTTPException) as exc:
        raise HTTPException(422, f'Не удалось прочитать book.json: {exc}') from exc


def page_map(data):
    result = {}
    def visit(nodes):
        for n in nodes:
            if 'path' in n:
                result[n['id']] = {k: n[k] for k in ('id', 'title', 'path')}
            visit(n.get('children', []))
    visit(data['pages'])
    return result


def atomic_json(file: Path, value):
    temporary = file.with_name(file.name + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, file)
        directory = os.open(file.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class Library:
    def __init__(self, directory: Path, initial_roots: list[Path]):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.file = self.directory / 'library.json'
        self.entries = {}
        if self.file.exists():
            # A broken registry is never silently replaced with an empty library.
            data = json.loads(self.file.read_text(encoding='utf-8'))
            if data['version'] != 1:
                raise ValueError('Unsupported library.json version')
            for entry in data['books']:
                if not re.fullmatch(r'[a-f0-9]{32}', entry['id']) or entry['id'] in self.entries:
                    raise ValueError('Invalid or duplicate book ID in library.json')
                root = Path(entry['root'])
                if not root.is_absolute():
                    root = (self.directory / root).resolve()
                    if not root.is_relative_to(self.directory):
                        raise ValueError('Relative book root must stay inside the library')
                self.entries[entry['id']] = {**entry, 'root': str(root)}
        for root in initial_roots:
            resolved = str(root.resolve())
            if not any(e['root'] == resolved for e in self.entries.values()):
                self.register(root)
        if not self.file.exists():
            self.save()
        self.discover()

    def save(self):
        entries = []
        for entry in self.entries.values():
            root = Path(entry['root'])
            if root.is_relative_to(self.directory):
                root = root.relative_to(self.directory)
            entries.append({**entry, 'root': str(root)})
        atomic_json(self.file, {'version': 1, 'books': entries})

    def discover(self):
        """Import books received through file sync; the registry stays local."""
        books = self.directory / 'books'
        known = {entry['root'] for entry in self.entries.values()}
        if not books.is_dir():
            return
        for root in sorted(books.iterdir()):
            if root.name.startswith('.') or '.sync-conflict-' in root.name or root.is_symlink():
                continue
            if str(root.resolve()) in known or not (root / 'book.json').is_file():
                continue
            try:
                self.register(root)
            except HTTPException:
                # Syncthing may deliver the manifest before its HTML pages.
                # Retry incomplete books on the next library refresh.
                continue

    def root(self, book_id: str):
        entry = self.entries.get(book_id)
        if not entry:
            self.discover()
            entry = self.entries.get(book_id)
            if not entry:
                raise HTTPException(404, 'Книга не найдена в библиотеке')
        return Path(entry['root'])

    def describe(self, book_id: str, strict=False):
        entry = self.entries[book_id]
        try:
            data = manifest(self.root(book_id))
            return {**entry, 'title': data['title'], 'subtitle': data.get('subtitle', ''), 'page_count': len(page_map(data)), 'error': None}
        except HTTPException as exc:
            if strict:
                raise
            return {**entry, 'subtitle': '', 'page_count': 0, 'error': exc.detail}

    def register(self, root: Path):
        if not root.is_absolute():
            raise HTTPException(422, 'Введите абсолютный путь к папке на этом компьютере')
        root = root.resolve()
        for entry in self.entries.values():
            if entry['root'] == str(root):
                return self.describe(entry['id'])
        data = manifest(root)
        if root.is_relative_to(self.directory / 'books'):
            book_id = uuid.uuid5(uuid.NAMESPACE_URL, 'grim:' + root.relative_to(self.directory).as_posix()).hex
        else:
            book_id = uuid.uuid4().hex
        self.entries[book_id] = {'id': book_id, 'root': str(root), 'title': data['title']}
        try:
            self.save()
        except OSError:
            del self.entries[book_id]
            raise
        return self.describe(book_id)

    def create(self, title: str):
        title = title.strip()
        if not title:
            raise HTTPException(422, 'Введите название книги')
        root = self.directory / 'books' / uuid.uuid4().hex
        root.mkdir(parents=True, exist_ok=False)
        # Truly empty: the external agent can create the first page and update TOC.
        atomic_json(root / 'book.json', {'title': title, 'subtitle': '', 'pages': []})
        try:
            return self.register(root)
        except Exception:
            (root / 'book.json').unlink()
            root.rmdir()
            raise
