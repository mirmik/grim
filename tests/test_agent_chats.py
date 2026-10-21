import copy
import json
import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

from server.agent import AgentService, Turn
from server.agent_store import AgentStore
from server.app import create_app
from server.versions import create_source, rename_working
from test_agent import answer, call, turn
from test_server import make_book, entry, headers


def wait_chat(client, book_id, chat_id, job_id):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        jobs = client.get(f'/api/books/{book_id}/agent', params={'chat_id': chat_id}).json()['jobs']
        job = next(job for job in jobs if job['id'] == job_id)
        if job['status'] not in ('queued', 'running', 'stopping'):
            return job
        time.sleep(.02)
    pytest.fail('Chat job did not complete')


def test_legacy_migration_preserves_messages_jobs_and_edits_once(tmp_path):
    library = tmp_path / 'library'
    library.mkdir()
    payload = Turn(**turn()).model_dump()
    payload.pop('chat_id')
    messages = [{'role': 'user', 'content': 'Old question'}, {'role': 'assistant', 'content': 'Old answer'}]
    with sqlite3.connect(library / 'agent.sqlite3') as db:
        db.executescript('''CREATE TABLE sessions(book_id TEXT PRIMARY KEY,messages TEXT NOT NULL);
            CREATE TABLE jobs(id TEXT PRIMARY KEY,book_id TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,
                response TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',events TEXT NOT NULL DEFAULT '[]',created_at REAL NOT NULL);
            CREATE TABLE edits(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,book_id TEXT NOT NULL,path TEXT NOT NULL,
                before_text TEXT,after_text TEXT NOT NULL,status TEXT NOT NULL,created_at REAL NOT NULL);''')
        db.execute('INSERT INTO sessions VALUES(?,?)', ('book', json.dumps(messages)))
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)', (payload['job_id'], 'book', json.dumps(payload, sort_keys=True, ensure_ascii=False), 'completed', 'Old answer', '', '[]', 123))
        db.execute('INSERT INTO edits VALUES(?,?,?,?,?,?,?,?)', ('edit', payload['job_id'], 'book', 'one.html', 'before', 'after', 'applied', 123))
    store = AgentStore(library)
    old = store.chat('book')
    assert store.session('book', old['id']) == messages
    assert store.submit('book', payload)[1] is False
    assert store.job(payload['job_id'])['chat_id'] == old['id']
    assert store.edit('book', 'edit')['before_text'] == 'before'
    new = store.new_chat('book')
    assert store.session('book') == []
    restarted = AgentStore(library)
    assert len(restarted.chats('book')) == 2
    assert restarted.chat('book')['id'] == new['id']
    assert restarted.session('book', old['id']) == messages
    assert restarted.jobs('book', new['id']) == []
    with sqlite3.connect(library / 'agent.sqlite3') as db:
        assert json.loads(db.execute('SELECT messages FROM sessions').fetchone()[0]) == messages


@pytest.mark.skipif(not AgentService.available(), reason='Optional Nemor unavailable')
def test_chats_have_isolated_history_and_resume_after_restart(tmp_path):
    seen = []
    def complete(*, messages, **kwargs):
        seen.append(copy.deepcopy(messages))
        return answer(['old-answer', 'new-answer', 'continued-old'][len(seen)-1])
    root, library = make_book(tmp_path / 'book'), tmp_path / 'library'
    with TestClient(create_app(root, library, agent_completion=complete)) as client:
        book_id, auth = entry(client)['id'], headers(client)
        route = f'/api/books/{book_id}/agent'
        old = client.get(route).json()['chat']['id']
        first = {**turn('Old question'), 'chat_id': old}
        assert client.post(route + '/jobs', headers=auth, json=first).status_code == 200
        assert wait_chat(client, book_id, old, first['job_id'])['response'] == 'old-answer'
        new = client.post(route + '/chats', headers=auth).json()['chat']['id']
        assert client.get(route).json()['jobs'] == []
        second = {**turn('New question'), 'chat_id': new}
        client.post(route + '/jobs', headers=auth, json=second).raise_for_status()
        assert wait_chat(client, book_id, new, second['job_id'])['response'] == 'new-answer'
        assert 'old-answer' not in json.dumps(seen[1]) and 'Old question' not in json.dumps(seen[1])
        client.post(route + f'/chats/{old}/activate', headers=auth).raise_for_status()
        assert client.get(route).json()['jobs'][0]['id'] == first['job_id']
        third = {**turn('Continue old'), 'chat_id': old}
        client.post(route + '/jobs', headers=auth, json=third).raise_for_status()
        assert wait_chat(client, book_id, old, third['job_id'])['response'] == 'continued-old'
        assert 'old-answer' in json.dumps(seen[2]) and 'new-answer' not in json.dumps(seen[2])
        # Exact retry belongs to its original chat even after choosing another.
        assert client.post(route + '/jobs', headers=auth, json=second).json()['chat_id'] == new
        assert client.post(route + '/jobs', headers=auth, json={**second, 'chat_id': old}).status_code == 409
    with TestClient(create_app(root, library, agent_completion=complete)) as client:
        assert client.get(route).json()['chat']['id'] == old
        assert len(client.get(route, params={'chat_id': old}).json()['jobs']) == 2
        assert len(client.get(route, params={'chat_id': new}).json()['jobs']) == 1


@pytest.mark.skipif(not AgentService.available(), reason='Optional Nemor unavailable')
def test_book_metadata_and_exact_model_request_are_visible_without_credentials(tmp_path):
    root = make_book(tmp_path / 'book')
    manifest = json.loads((root / 'book.json').read_text())
    manifest.update(title='Actual book', subtitle='Author · Subtitle', authors=['Author'], description='A real annotation')
    (root / 'book.json').write_text(json.dumps(manifest))
    create_source(root)
    rename_working(root, 'Translation draft')
    sent = []
    def complete(*, messages, **kwargs):
        sent.append(copy.deepcopy(messages))
        if messages[-1]['role'] == 'user':
            snapshot = json.loads(messages[-1]['content'].split('\n')[-1])
            assert snapshot['book']['title'] == 'Actual book'
            assert snapshot['book']['description'] == 'A real annotation'
            assert snapshot['book']['subtitle'] == 'Author · Subtitle'
            assert snapshot['book']['view_title'] == 'Translation draft'
            assert snapshot['page']['path'] == 'one.html'
            return call('reading_context', {})
        context = json.loads(messages[-1]['content'])
        assert context['at_send']['book']['title'] == 'Actual book'
        return answer('I know the book')
    with TestClient(create_app(root, tmp_path / 'library', agent_completion=complete)) as client:
        book_id, auth = entry(client)['id'], headers(client)
        route = f'/api/books/{book_id}/agent'
        client.put('/api/agent/settings', headers=auth, json={'model':'test', 'api_token':'secret-model-token'}).raise_for_status()
        chat = client.get(route).json()['chat']['id']
        preview_payload = {'chat_id':chat, 'reader_id':'reader-one', 'message':'Draft', 'context':turn()['context']}
        assert client.post(route + '/context', json=preview_payload).status_code == 403
        preview = client.post(route + '/context', headers=auth, json=preview_payload).json()
        assert preview['last_request'] is None and preview['snapshot']['book']['authors'] == ['Author']
        assert preview['preview']['messages'][0]['role'] == 'system'
        assert {tool['function']['name'] for tool in preview['preview']['tools']} >= {'notes_list', 'notes_read', 'notes_create', 'notes_update', 'notes_delete'}
        assert client.get(route).json()['jobs'] == [] and sent == []
        payload = {**turn('What book is this?'), 'chat_id':chat}
        client.post(route + '/jobs', headers=auth, json=payload).raise_for_status()
        assert wait_chat(client, book_id, chat, payload['job_id'])['status'] == 'completed'
        debug = client.post(route + '/context', headers=auth, json=preview_payload)
        last = debug.json()['last_request']
        assert last['step'] == 2 and last['request']['messages'] == sent[-1]
        assert last['request']['messages'][-1]['role'] == 'tool'
        assert last['request']['model'] == 'test'
        assert 'secret-model-token' not in debug.text and 'Authorization' not in debug.text
        assert any(message.get('content') == 'I know the book' for message in debug.json()['preview']['messages'])
        # Latest metadata is fresh for the preview; the actual sent request is immutable.
        working = root / 'translation-draft'
        manifest_path = working / 'book.json'
        changed = json.loads(manifest_path.read_text()); changed['title'] = 'Renamed view'
        manifest_path.write_text(json.dumps(changed))
        refreshed = client.post(route + '/context', headers=auth, json=preview_payload).json()
        assert refreshed['snapshot']['book']['view_title'] == 'Renamed view'
        assert refreshed['last_request']['request'] == last['request']
        source = {**preview_payload, 'context':{**preview_payload['context'], 'version':'source'}}
        assert client.post(route + '/context', headers=auth, json=source).json()['snapshot']['book']['view_title'] == 'Actual book'


@pytest.mark.skipif(not AgentService.available(), reason='Optional Nemor unavailable')
def test_switching_chats_during_work_keeps_job_and_history_in_original_chat(tmp_path):
    started, release = threading.Event(), threading.Event()
    def complete(**kwargs):
        started.set();release.wait(5)
        return answer('Completed in original chat')
    with TestClient(create_app(make_book(tmp_path / 'book'), tmp_path / 'library', agent_completion=complete)) as client:
        book_id, auth = entry(client)['id'], headers(client)
        route = f'/api/books/{book_id}/agent'
        old = client.get(route).json()['chat']['id']
        payload = {**turn(), 'chat_id':old}
        try:
            client.post(route + '/jobs', headers=auth, json=payload).raise_for_status()
            assert started.wait(2)
            new = client.post(route + '/chats', headers=auth).json()['chat']['id']
            state = client.get(route).json()
            assert state['running_chat_id'] == old and state['jobs'] == []
            assert client.post(route + '/jobs', headers=auth, json={**turn('Other chat'), 'chat_id':new}).status_code == 409
        finally:
            release.set()
        assert wait_chat(client, book_id, old, payload['job_id'])['response'] == 'Completed in original chat'
        assert client.app.state.agent.store.session(book_id, new) == []
        assert any(row.get('content') == 'Completed in original chat' for row in client.app.state.agent.store.session(book_id, old))


def test_chat_routes_cannot_access_another_books_history(tmp_path):
    with TestClient(create_app(make_book(tmp_path / 'book'), tmp_path / 'library')) as client:
        book_id, auth = entry(client)['id'], headers(client)
        other = client.post('/api/library/create', headers=auth, json={'title':'Other'}).json()['id']
        chat = client.get(f'/api/books/{book_id}/agent').json()['chat']['id']
        route = f'/api/books/{other}/agent'
        assert client.get(route, params={'chat_id':chat}).status_code == 404
        assert client.post(route + '/chats/' + chat + '/activate', headers=auth).status_code == 404
        assert client.post(route + '/jobs', headers=auth, json={**turn(), 'chat_id':chat}).status_code == 404
        assert client.post(route + '/context', headers=auth, json={'chat_id':chat,'reader_id':'reader'}).status_code == 404
        assert client.post(route + '/chats').status_code == 403
