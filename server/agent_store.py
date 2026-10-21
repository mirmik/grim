"""Local agent settings, conversations, accepted jobs and file preimages."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid


class AgentStore:
    def __init__(self, directory: Path):
        self.path = directory / 'agent.sqlite3'
        self.lock = threading.RLock()
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (book_id TEXT PRIMARY KEY, messages TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, payload TEXT NOT NULL,
                    status TEXT NOT NULL, response TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '', events TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS edits (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL, book_id TEXT NOT NULL,
                    path TEXT NOT NULL, before_text TEXT, after_text TEXT NOT NULL,
                    status TEXT NOT NULL, created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY, book_id TEXT NOT NULL, title TEXT NOT NULL,
                    messages TEXT NOT NULL DEFAULT '[]', created_at REAL NOT NULL, updated_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS book_chats (book_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS model_requests (
                    chat_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, request TEXT NOT NULL,
                    created_at REAL NOT NULL, step INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS session_archives (
                    operation_id TEXT PRIMARY KEY, book_id TEXT NOT NULL, chat_id TEXT NOT NULL,
                    messages TEXT NOT NULL, created_at REAL NOT NULL);
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            if 'chat_id' not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN chat_id TEXT NOT NULL DEFAULT ''")
            if 'book_context' not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN book_context TEXT NOT NULL DEFAULT '{}'")
            db.execute('CREATE INDEX IF NOT EXISTS jobs_chat ON jobs(chat_id,created_at,id)')
            db.execute('CREATE INDEX IF NOT EXISTS chats_book ON chats(book_id,updated_at)')
            # Materialize the old per-book conversation once. Keep the legacy
            # table intact; every existing job retains its ID and file history.
            books = db.execute('SELECT book_id FROM sessions UNION SELECT book_id FROM jobs').fetchall()
            for row in books:
                book_id = row['book_id']
                if not db.execute('SELECT 1 FROM book_chats WHERE book_id=?', (book_id,)).fetchone():
                    old = db.execute('SELECT messages FROM sessions WHERE book_id=?', (book_id,)).fetchone()
                    first = db.execute('SELECT payload,created_at FROM jobs WHERE book_id=? ORDER BY created_at,id LIMIT 1', (book_id,)).fetchone()
                    title = ' '.join(json.loads(first['payload']).get('message', '').split())[:80] if first else 'Прежний чат'
                    self._new_chat(db, book_id, title or 'Прежний чат', old['messages'] if old else '[]', first['created_at'] if first else None)
                chat = self._chat(db, book_id)
                db.execute("UPDATE jobs SET chat_id=? WHERE book_id=? AND chat_id=''", (chat['id'], book_id))
            # Do not replay a model turn whose file effects may already exist.
            db.execute("UPDATE jobs SET status='interrupted', error=? WHERE status IN ('queued','running','stopping')",
                       ('Сервер перезапущен. Проверьте уже внесённые изменения перед новым заданием.',))

    @contextmanager
    def db(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            try:
                with db:
                    yield db
            finally:
                db.close()

    def settings(self):
        with self.db() as db:
            row = db.execute('SELECT data FROM settings WHERE id=1').fetchone()
        return json.loads(row['data']) if row else {}

    def save_settings(self, data):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)', (json.dumps(data),))

    @staticmethod
    def _new_chat(db, book_id, title='Новый чат', messages='[]', created_at=None):
        chat_id, now = uuid.uuid4().hex, time.time()
        db.execute('INSERT INTO chats VALUES(?,?,?,?,?,?)', (chat_id, book_id, title, messages, created_at or now, now))
        db.execute('INSERT OR REPLACE INTO book_chats VALUES(?,?)', (book_id, chat_id))
        return chat_id

    @classmethod
    def _chat(cls, db, book_id, chat_id=None):
        if chat_id is not None:
            row = db.execute('SELECT * FROM chats WHERE id=? AND book_id=?', (chat_id, book_id)).fetchone()
            if row is None:
                raise KeyError('Чат не найден в этой книге')
            return row
        row = db.execute('SELECT chats.* FROM chats JOIN book_chats ON chats.id=book_chats.chat_id WHERE book_chats.book_id=? AND chats.book_id=?', (book_id, book_id)).fetchone()
        if row is not None:
            return row
        return cls._chat(db, book_id, cls._new_chat(db, book_id))

    @staticmethod
    def _chat_info(row):
        return {key: row[key] for key in ('id', 'book_id', 'title', 'created_at', 'updated_at')}

    def chat(self, book_id, chat_id=None):
        with self.db() as db:
            return self._chat_info(self._chat(db, book_id, chat_id))

    def chats(self, book_id):
        with self.db() as db:
            self._chat(db, book_id)
            rows = db.execute('SELECT chats.*, (SELECT COUNT(*) FROM jobs WHERE jobs.chat_id=chats.id) AS job_count FROM chats WHERE book_id=? ORDER BY updated_at DESC,id', (book_id,)).fetchall()
            return [{**self._chat_info(row), 'job_count': row['job_count']} for row in rows]

    def new_chat(self, book_id):
        with self.db() as db:
            chat_id = self._new_chat(db, book_id)
            return self._chat_info(self._chat(db, book_id, chat_id))

    def activate_chat(self, book_id, chat_id):
        with self.db() as db:
            chat = self._chat(db, book_id, chat_id)
            db.execute('INSERT OR REPLACE INTO book_chats VALUES(?,?)', (book_id, chat_id))
            return self._chat_info(chat)

    def session(self, book_id, chat_id=None):
        with self.db() as db:
            return json.loads(self._chat(db, book_id, chat_id)['messages'])

    def save_session(self, book_id, messages, chat_id=None):
        with self.db() as db:
            chat = self._chat(db, book_id, chat_id)
            db.execute('UPDATE chats SET messages=?,updated_at=? WHERE id=?', (json.dumps(messages, ensure_ascii=False), time.time(), chat['id']))

    def refresh_system(self, book_id, chat_id, content):
        with self.db() as db:
            chat = self._chat(db, book_id, chat_id)
            if db.execute("SELECT 1 FROM jobs WHERE book_id=? AND status IN ('queued','running','stopping')", (book_id,)).fetchone():
                raise ValueError('Дождитесь завершения или остановки задания этой книги')
            messages = [{'role': 'system', 'content': content}] + [m for m in json.loads(chat['messages']) if m.get('role') != 'system']
            db.execute('UPDATE chats SET messages=?,updated_at=? WHERE id=?', (json.dumps(messages, ensure_ascii=False), time.time(), chat_id))

    def commit_compaction(self, job_id, original, messages, response):
        """Archive and replace the context together, guarded by job and preimage."""
        with self.db() as db:
            job = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if job['status'] != 'running':
                return False
            chat = self._chat(db, job['book_id'], job['chat_id'])
            if json.loads(chat['messages']) != original:
                raise ValueError('Контекст чата изменился во время сжатия. Сводка не сохранена.')
            now = time.time()
            db.execute('INSERT INTO session_archives VALUES(?,?,?,?,?)',
                       (job_id, job['book_id'], job['chat_id'], chat['messages'], now))
            db.execute('UPDATE chats SET messages=?,updated_at=? WHERE id=?', (json.dumps(messages, ensure_ascii=False), now, chat['id']))
            db.execute("UPDATE jobs SET status='completed',response=?,error='' WHERE id=?", (response, job_id))
            return True

    def archives(self, book_id, chat_id, operation_id=None):
        with self.db() as db:
            self._chat(db, book_id, chat_id)
            if operation_id:
                row = db.execute('SELECT * FROM session_archives WHERE book_id=? AND chat_id=? AND operation_id=?',
                                 (book_id, chat_id, operation_id)).fetchone()
                return {**dict(row), 'messages': json.loads(row['messages'])} if row else None
            return [dict(row) for row in db.execute('SELECT operation_id,created_at FROM session_archives WHERE book_id=? AND chat_id=? ORDER BY created_at DESC',
                                                   (book_id, chat_id))]

    def save_model_request(self, chat_id, job_id, request):
        with self.db() as db:
            db.execute('''INSERT INTO model_requests VALUES(?,?,?,?,1) ON CONFLICT(chat_id) DO UPDATE SET
                step=CASE WHEN model_requests.job_id=excluded.job_id THEN model_requests.step+1 ELSE 1 END,
                job_id=excluded.job_id,request=excluded.request,created_at=excluded.created_at''',
                (chat_id, job_id, json.dumps(request, ensure_ascii=False), time.time()))

    def model_request(self, chat_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM model_requests WHERE chat_id=?', (chat_id,)).fetchone()
        return {**dict(row), 'request': json.loads(row['request'])} if row else None

    @staticmethod
    def decode_job(row):
        if row is None:
            return None
        data = dict(row)
        data['payload'] = json.loads(data['payload'])
        data['events'] = json.loads(data['events'])
        data['book_context'] = json.loads(data['book_context'])
        return data

    def job(self, job_id):
        with self.db() as db:
            return self.decode_job(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())

    def jobs(self, book_id, chat_id=None):
        with self.db() as db:
            if chat_id is None:
                rows = db.execute('SELECT * FROM jobs WHERE book_id=? ORDER BY created_at,id', (book_id,)).fetchall()
            else:
                self._chat(db, book_id, chat_id)
                rows = db.execute('SELECT * FROM jobs WHERE book_id=? AND chat_id=? ORDER BY created_at,id', (book_id, chat_id)).fetchall()
        return [self.decode_job(row) for row in rows]

    def submit(self, book_id, payload, book_context=None):
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        with self.db() as db:
            previous = db.execute('SELECT * FROM jobs WHERE id=?', (payload['job_id'],)).fetchone()
            if previous:
                if previous['book_id'] != book_id or previous['payload'] != canonical:
                    raise ValueError('ID задания уже использован с другим содержимым')
                return self.decode_job(previous), False
            chat = self._chat(db, book_id, payload.get('chat_id'))
            if db.execute("SELECT 1 FROM jobs WHERE book_id=? AND status IN ('queued','running','stopping')", (book_id,)).fetchone():
                raise ValueError('Агент уже работает с этой книгой')
            now = time.time()
            if not any(m.get('role') != 'system' for m in json.loads(chat['messages'])) and payload.get('operation') != 'compact':
                title = ' '.join(payload['message'].split())[:80] or 'Новый чат'
                db.execute('UPDATE chats SET title=? WHERE id=?', (title, chat['id']))
            db.execute('UPDATE chats SET updated_at=? WHERE id=?', (now, chat['id']))
            db.execute('INSERT INTO jobs(id,book_id,payload,status,created_at,chat_id,book_context) VALUES(?,?,?,?,?,?,?)',
                       (payload['job_id'], book_id, canonical, 'queued', now, chat['id'], json.dumps(book_context or {}, ensure_ascii=False)))
        return self.job(payload['job_id']), True

    def update_job(self, job_id, status, response='', error=''):
        with self.db() as db:
            db.execute('UPDATE jobs SET status=?,response=?,error=? WHERE id=?', (status, response, error, job_id))

    def event(self, job_id, name, detail):
        with self.db() as db:
            events = json.loads(db.execute('SELECT events FROM jobs WHERE id=?', (job_id,)).fetchone()['events'])
            events.append({'name': name, 'detail': str(detail)[:2000]})
            db.execute('UPDATE jobs SET events=? WHERE id=?', (json.dumps(events[-100:]), job_id))

    def before_edit(self, job_id, book_id, path, before, after):
        edit_id = uuid.uuid4().hex
        with self.db() as db:
            db.execute('INSERT INTO edits VALUES(?,?,?,?,?,?,?,?)',
                       (edit_id, job_id, book_id, path, before, after, 'prepared', time.time()))
        return edit_id

    def finish_edit(self, edit_id, status):
        with self.db() as db:
            db.execute('UPDATE edits SET status=? WHERE id=?', (status, edit_id))

    def history(self, book_id):
        with self.db() as db:
            return [dict(row) for row in db.execute(
                'SELECT id,job_id,path,status,created_at FROM edits WHERE book_id=? ORDER BY created_at DESC LIMIT 100', (book_id,))]

    def edit(self, book_id, edit_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM edits WHERE book_id=? AND id=?', (book_id, edit_id)).fetchone()
            return dict(row) if row else None
