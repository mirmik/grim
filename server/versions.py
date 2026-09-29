"""One optional, portable source snapshot beside the live working files."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Literal

from fastapi import HTTPException
from .library import atomic_json, manifest, safe_file

Version = Literal['working', 'source']
SOURCE = '.grim-source'


def file_digest(file):
    digest = hashlib.sha256()
    with file.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_exists(root):
    return (root / SOURCE).exists()


def content_files(root):
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__'))
        for name in [*dirs, *files]:
            if name.startswith('.') or name.endswith('.tmp'):
                continue
            file = Path(directory) / name
            if file.is_symlink():
                raise HTTPException(422, 'Для снимка замените симлинки обычными файлами: ' + str(file.relative_to(root)))
            if file.is_file():
                yield file.relative_to(root).as_posix(), file


def source_index(root):
    try:
        base = root / SOURCE
        if base.is_symlink() or (base / 'index.json').is_symlink():
            raise ValueError('симлинк в индексе')
        index = json.loads((base / 'index.json').read_text())
        if not isinstance(index, dict) or index.get('format') not in (1, 2) or not isinstance(index.get('files'), dict):
            raise ValueError('неверный индекс снимка')
        if index['format'] == 2:
            folder = index.get('working_directory')
            if not isinstance(folder, str) or not folder or folder.startswith('.') or any(c in folder for c in '/\\?#\x00'):
                raise ValueError('неверная папка рабочей копии')
        return index
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(409, 'Нарушена целостность оригинала: ' + str(exc)) from exc


def create_source(root):
    """Keep the main document in place and publish an independent visible copy."""
    from .naming import available_path
    destination = root / SOURCE
    if destination.exists():
        raise HTTPException(409, 'Рабочая копия уже создана')
    manifest(root)
    stage = Path(tempfile.mkdtemp(prefix='.grim-source-', dir=root))
    working = None
    try:
        hashes = {}
        for relative, file in content_files(root):
            target = stage / 'book' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with file.open('rb') as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            hashes[relative] = file_digest(target)
        manifest(stage / 'book')
        current = {relative: file_digest(file) for relative, file in content_files(root)}
        if current != hashes:
            raise HTTPException(409, 'Книга изменилась во время копирования. Повторите создание копии.')
        if (root / '.grim-notes.json').exists():
            shutil.copy2(root / '.grim-notes.json', stage / 'book' / '.grim-notes.json')
        working = available_path(root, 'рабочая-копия', directory=True)
        atomic_json(stage / 'index.json', {'format': 2, 'created_at': datetime.now(timezone.utc).isoformat(),
                    'files': hashes, 'working_directory': working.name, 'working_name': 'Рабочая копия'})
        (stage / 'book').rename(working)
        stage.rename(destination)
    except Exception:
        if working is not None and working.exists(): shutil.rmtree(working)
        raise
    finally:
        if stage.exists(): shutil.rmtree(stage)


def version_root(root, version: Version):
    if version not in ('working', 'source'):
        raise HTTPException(422, 'Неизвестная версия книги')
    if not source_exists(root):
        if version == 'working': return root
        raise HTTPException(404, 'Оригинал ещё не сохранён')
    index = source_index(root)
    if version == 'working':
        candidate = root / index['working_directory'] if index['format'] == 2 else root
        if candidate.is_symlink() or not candidate.is_dir():
            raise HTTPException(409, 'Папка рабочей копии отсутствует или заменена симлинком')
        return candidate
    source_file(root, 'book.json')
    return root if index['format'] == 2 else root / SOURCE / 'book'


def notes_location(root, version):
    version_root(root, version)
    if source_exists(root) and source_index(root)['format'] == 1:
        return root, version
    return version_root(root, version), 'working'


def source_file(root, relative):
    index = source_index(root)
    base = root if index['format'] == 2 else root / SOURCE / 'book'
    try:
        if base.is_symlink(): raise ValueError('симлинк в снимке')
        file = safe_file(base, relative)
        canonical = file.relative_to(base).as_posix()
        if any(p.is_symlink() for p in [base / relative, *(base / relative).parents] if p.is_relative_to(base)):
            raise ValueError('симлинк в снимке')
        expected = index['files'].get(canonical)
        if not expected or file_digest(file) != expected:
            raise ValueError(canonical)
        return file
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(409, 'Нарушена целостность оригинала: ' + str(exc)) from exc


def rename_working(root, title):
    from .naming import available_path, readable_name
    title = title.strip()
    if not title: raise HTTPException(422, 'Укажите название рабочей копии')
    index = source_index(root)
    if index['format'] != 2:
        raise HTTPException(409, 'Сначала обновите структуру папки книги')
    previous = version_root(root, 'working')
    folder = readable_name(title)
    target = previous if folder == previous.name else available_path(root, folder, directory=True)
    before = (previous / 'book.json').read_bytes()
    try:
        data = manifest(previous); data['title'] = title
        atomic_json(previous / 'book.json', data)
        if target != previous: previous.rename(target)
        index.update(working_directory=target.name, working_name=title)
        atomic_json(root / SOURCE / 'index.json', index)
    except Exception:
        if target != previous and target.exists():
            if not previous.exists(): target.rename(previous)
            else: target.rmdir()
        (previous / 'book.json').write_bytes(before)
        raise
    return index
