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
            ''')
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

    def session(self, book_id):
        with self.db() as db:
            row = db.execute('SELECT messages FROM sessions WHERE book_id=?', (book_id,)).fetchone()
        return json.loads(row['messages']) if row else []

    def save_session(self, book_id, messages):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?)', (book_id, json.dumps(messages)))

    @staticmethod
    def decode_job(row):
        if row is None:
            return None
        data = dict(row)
        data['payload'] = json.loads(data['payload'])
        data['events'] = json.loads(data['events'])
        return data

    def job(self, job_id):
        with self.db() as db:
            return self.decode_job(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())

    def jobs(self, book_id):
        with self.db() as db:
            rows = db.execute('SELECT * FROM jobs WHERE book_id=? ORDER BY created_at,id', (book_id,)).fetchall()
        return [self.decode_job(row) for row in rows]

    def submit(self, book_id, payload):
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        with self.db() as db:
            previous = db.execute('SELECT * FROM jobs WHERE id=?', (payload['job_id'],)).fetchone()
            if previous:
                if previous['book_id'] != book_id or previous['payload'] != canonical:
                    raise ValueError('ID задания уже использован с другим содержимым')
                return self.decode_job(previous), False
            if db.execute("SELECT 1 FROM jobs WHERE book_id=? AND status IN ('queued','running','stopping')", (book_id,)).fetchone():
                raise ValueError('Агент уже работает с этой книгой')
            db.execute('INSERT INTO jobs(id,book_id,payload,status,created_at) VALUES(?,?,?,?,?)',
                       (payload['job_id'], book_id, canonical, 'queued', time.time()))
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
