"""Persistent device credentials. Only SHA256 hashes and metadata reach disk."""
from copy import deepcopy
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import threading
import time


class AccessTokens:
    def __init__(self, path: Path, initial_hash: str):
        self.path = path
        self.lock = threading.RLock()
        schema = None
        changed = False
        if path.exists():
            info = path.stat()
            if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('Access token registry must be an owned regular file with mode 0600')
            data = json.loads(path.read_text())
            schema = data.get('schema')
            if schema not in (1, 2) or not isinstance(data.get('tokens'), list):
                raise ValueError('Invalid access token registry')
            self.rows = data['tokens']
            ids = set()
            for row in self.rows:
                if (not re.fullmatch(r'legacy|[a-f0-9]{32}', row.get('id', ''))
                        or row['id'] in ids or not re.fullmatch(r'[a-f0-9]{64}', row.get('hash', ''))
                        or not isinstance(row.get('name'), str)
                        or not isinstance(row.get('created_at'), int)
                        or any(row.get(key) is not None and not isinstance(row[key], int) for key in ('last_used_at', 'revoked_at'))):
                    raise ValueError('Invalid access token registry entry')
                ids.add(row['id'])
            legacy = next((row for row in self.rows if row['id'] == 'legacy'), None)
            if legacy is None:
                raise ValueError('Initial credential missing from access token registry')
            if legacy['hash'] != initial_hash:
                rows = deepcopy(self.rows)
                row = next(row for row in rows if row['id'] == 'legacy')
                row.update(hash=initial_hash, created_at=int(time.time()), last_used_at=None, revoked_at=None)
                self.rows = rows
                changed = True
        else:
            self.rows = [dict(id='legacy', name='Первоначальный токен', hash=initial_hash,
                              prefix='', created_at=int(time.time()), last_used_at=None, revoked_at=None)]
        # An access credential must never be the sole session-signing secret:
        # its former holder could otherwise forge another device's session.
        key_path = path.with_suffix('.key')
        if not key_path.exists():
            if schema == 2:
                raise ValueError('Access signing key missing; restore it rather than silently replacing it')
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(secrets.token_bytes(32))
                stream.flush()
                os.fsync(stream.fileno())
        info = key_path.stat()
        if key_path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Access signing key must be an owned regular file with mode 0600')
        self.signing_key = key_path.read_bytes()
        if len(self.signing_key) != 32:
            raise ValueError('Invalid access signing key')
        if schema != 2 or changed:
            self._commit(self.rows)

    def _commit(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix='.access-tokens-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump({'schema': 2, 'tokens': rows}, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.rows = rows
        finally:
            Path(temporary).unlink(missing_ok=True)

    def list(self):
        with self.lock:
            return [{key: value for key, value in row.items() if key != 'hash'} for row in reversed(self.rows)]

    def active(self, token_id):
        with self.lock:
            return any(row['id'] == token_id and row['revoked_at'] is None for row in self.rows)

    def authenticate(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            return next((row['id'] for row in self.rows if row['revoked_at'] is None
                         and hmac.compare_digest(row['hash'], digest)), None)

    def touch(self, token_id):
        with self.lock:
            now = int(time.time())
            if not any(row['id'] == token_id and row['revoked_at'] is None
                       and now - (row['last_used_at'] or 0) >= 60 for row in self.rows):
                return
            rows = deepcopy(self.rows)
            next(row for row in rows if row['id'] == token_id)['last_used_at'] = now
            self._commit(rows)

    def create(self, name):
        name = name.strip()
        if not name or len(name) > 80 or any(ord(char) < 32 for char in name):
            raise ValueError('Укажите название устройства длиной до 80 символов')
        raw = 'grim_' + secrets.token_urlsafe(32)
        row = dict(id=secrets.token_hex(16), name=name, hash=hashlib.sha256(raw.encode()).hexdigest(),
                   prefix=raw[:12], created_at=int(time.time()), last_used_at=None, revoked_at=None)
        with self.lock:
            if sum(item['revoked_at'] is None for item in self.rows) >= 256:
                raise ValueError('Сначала отзовите неиспользуемые токены: активно уже 256')
            self._commit([*self.rows, row])
        return {'token': raw, 'entry': {key: value for key, value in row.items() if key != 'hash'}}

    def revoke(self, token_id):
        with self.lock:
            if not any(row['id'] == token_id for row in self.rows):
                raise KeyError(token_id)
            rows = deepcopy(self.rows)
            row = next(row for row in rows if row['id'] == token_id)
            if row['revoked_at'] is None:
                row['revoked_at'] = int(time.time())
                self._commit(rows)
