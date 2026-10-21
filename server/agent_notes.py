"""Free-form, book-scoped agent notes stored as ordinary UTF-8 files."""
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile
import threading

DIRECTORY = '.grim-agent-notes'
MAX_BYTES = 64_000


class NoteError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class AgentNotes:
    def __init__(self, root, lock=None):
        self.directory = Path(root).resolve() / DIRECTORY
        self.lock = lock or threading.RLock()

    def target(self, name):
        if (not isinstance(name, str) or not name.strip() or name.startswith('.')
                or len(name.encode('utf-8')) > 200
                or any(c in name for c in '/\\?#')
                or any(ord(c) < 32 or ord(c) == 127 for c in name)):
            raise NoteError(422, 'Нужно имя записки без папок, скрытых имён и управляющих символов')
        if self.directory.is_symlink() or (self.directory.exists() and not self.directory.is_dir()):
            raise NoteError(422, 'Хранилище записок должно быть обычной папкой')
        file = self.directory / name
        if file.is_symlink():
            raise NoteError(422, 'Симлинки в записках не поддерживаются')
        return file

    def _read(self, file):
        try:
            fd = os.open(file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            raise NoteError(404, 'Записка не найдена') from None
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise NoteError(422, 'Записка должна быть обычным файлом')
        with os.fdopen(fd, 'rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise NoteError(422, f'Записка слишком велика: максимум {MAX_BYTES} байт')
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            raise NoteError(422, 'Записка должна быть в UTF-8') from None
        return data

    @staticmethod
    def result(name, data):
        return {'name': name, 'content': data.decode('utf-8'),
                'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

    def list(self):
        with self.lock:
            self.target('check')
            if not self.directory.exists():
                return {'notes': []}
            notes = []
            for file in sorted(self.directory.iterdir()):
                try:
                    self.target(file.name)
                except NoteError:
                    continue
                if file.is_file():
                    info = file.stat()
                    notes.append({'name': file.name, 'bytes': info.st_size, 'updated_at': info.st_mtime})
            return {'notes': notes}

    def read(self, name):
        with self.lock:
            return self.result(name, self._read(self.target(name)))

    def _expected(self, file, expected_sha256):
        if not isinstance(expected_sha256, str) or not re.fullmatch('[a-f0-9]{64}', expected_sha256):
            raise NoteError(422, 'Нужен SHA-256 из notes_read')
        before = self._read(file)
        if hashlib.sha256(before).hexdigest() != expected_sha256:
            raise NoteError(409, 'Записка изменилась. Перечитайте её перед обновлением или удалением.')
        return before

    def _save(self, name, content, expected_sha256=None, *, create=False):
        if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_BYTES:
            raise NoteError(422, f'Нужен текст UTF-8 не более {MAX_BYTES} байт')
        with self.lock:
            file = self.target(name)
            if not create:
                self._expected(file, expected_sha256)
            self.directory.mkdir(exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.note-', suffix='.tmp', dir=self.directory)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(content.encode('utf-8'))
                    stream.flush()
                    os.fsync(stream.fileno())
                self.target(name)
                if create:
                    try:
                        # Publish without replacing an existing note, even if an
                        # external editor created it since the initial check.
                        os.link(temporary, file)
                    except FileExistsError:
                        raise NoteError(409, 'Записка уже существует. Прочитайте её перед обновлением.') from None
                else:
                    self._expected(file, expected_sha256)
                    os.replace(temporary, file)
                self._sync()
            finally:
                Path(temporary).unlink(missing_ok=True)
            return self.result(name, content.encode('utf-8'))

    def create(self, name, content):
        return self._save(name, content, create=True)

    def update(self, name, content, expected_sha256):
        return self._save(name, content, expected_sha256)

    def delete(self, name, expected_sha256):
        with self.lock:
            file = self.target(name)
            self._expected(file, expected_sha256)
            file.unlink()
            self._sync()
            return {'name': name, 'deleted': True}

    def _sync(self):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
