import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from server.agent import AgentService
from server.agent_notes import AgentNotes, DIRECTORY, MAX_BYTES, NoteError
from server.app import create_app
from server.versions import create_source, rename_working, source_index, version_root
from test_agent import answer, call, turn, wait_job
from test_server import make_book, entry, headers


def test_plain_files_conflicts_and_complete_unicode_reads(tmp_path):
    notes = AgentNotes(tmp_path)
    assert notes.list() == {'notes': []}
    assert not (tmp_path / DIRECTORY).exists()
    first = notes.create('Перевод.md', 'Ятима — персонаж\n')
    file = tmp_path / DIRECTORY / 'Перевод.md'
    assert file.read_text() == first['content']
    assert notes.read('Перевод.md') == first
    with pytest.raises(NoteError, match='уже существует'):
        notes.create('Перевод.md', 'accidental overwrite')
    file.write_text('Изменено внешним агентом')
    with pytest.raises(NoteError, match='изменилась'):
        notes.update('Перевод.md', 'stale update', first['sha256'])
    with pytest.raises(NoteError, match='изменилась'):
        notes.delete('Перевод.md', first['sha256'])
    current = notes.read('Перевод.md')
    updated = notes.update('Перевод.md', 'я' * (MAX_BYTES // 2), current['sha256'])
    assert notes.read('Перевод.md') == updated
    assert updated['bytes'] == MAX_BYTES
    with pytest.raises(NoteError, match='не более'):
        notes.update('Перевод.md', updated['content'] + 'я', updated['sha256'])
    notes.delete('Перевод.md', updated['sha256'])
    assert not file.exists() and notes.list() == {'notes': []}


@pytest.mark.parametrize('name', ['', ' ', '../escape.md', '/tmp/escape.md', 'a/b', 'a\\b', '.hidden', 'a\x00b', 'a\nb', 'я' * 101])
def test_invalid_names_cannot_create_files(tmp_path, name):
    with pytest.raises(NoteError):
        AgentNotes(tmp_path).create(name, 'text')
    assert not (tmp_path / DIRECTORY).exists()


def test_symlinks_special_files_and_invalid_external_files_are_not_notes(tmp_path):
    notes = AgentNotes(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (tmp_path / DIRECTORY).symlink_to(outside, target_is_directory=True)
    with pytest.raises(NoteError, match='обычной папкой'):
        notes.list()
    with pytest.raises(NoteError):
        notes.create('escape.md', 'text')
    (tmp_path / DIRECTORY).unlink()
    notes.create('ok.md', 'ok')
    directory = tmp_path / DIRECTORY
    (outside / 'secret').write_text('private')
    (directory / 'link.md').symlink_to(outside / 'secret')
    os.mkfifo(directory / 'pipe')
    (directory / 'subdir').mkdir()
    (directory / 'binary').write_bytes(b'\xff')
    (directory / 'huge').write_bytes(b'x' * (MAX_BYTES + 1))
    assert 'link.md' not in [note['name'] for note in notes.list()['notes']]
    for name in ['link.md', 'pipe', 'subdir', 'binary', 'huge']:
        with pytest.raises(NoteError):
            notes.read(name)
    assert (outside / 'secret').read_text() == 'private'


def test_http_crud_auth_book_isolation_and_watcher(tmp_path):
    root = make_book(tmp_path / 'book')
    with TestClient(create_app(root, tmp_path / 'library')) as client:
        book_id, auth = entry(client)['id'], headers(client)
        route = f'/api/books/{book_id}/agent/notes'
        revision = client.get(f'/api/books/{book_id}').json()['revision']
        assert client.get(route).json() == {'notes': []}
        assert client.post(route, json={'name': 'translation.md', 'content': 'agreed'}).status_code == 403
        created = client.post(route, headers=auth, json={'name': 'translation.md', 'content': 'agreed'})
        assert created.status_code == 201
        note = created.json()
        path = route + '/translation.md'
        assert client.get(path).json() == note
        assert client.get(route).json()['notes'][0]['name'] == 'translation.md'
        assert client.post(route, headers=auth, json={'name': 'translation.md', 'content': 'overwrite'}).status_code == 409
        assert client.post(route, headers=auth, json={'name': '../escape', 'content': 'bad'}).status_code == 422
        # Ordinary files can be changed outside the API. Stale writes/deletes fail.
        (root / DIRECTORY / 'translation.md').write_text('external')
        edit = {'content': 'updated', 'expected_sha256': note['sha256']}
        assert client.put(path, json=edit).status_code == 403
        assert client.put(path, headers=auth, json=edit).status_code == 409
        assert client.request('DELETE', path, headers=auth, json={'expected_sha256': note['sha256']}).status_code == 409
        edit['expected_sha256'] = client.get(path).json()['sha256']
        updated = client.put(path, headers=auth, json=edit).json()
        assert updated['content'] == 'updated'
        other = client.post('/api/library/create', headers=auth, json={'title': 'Other'}).json()['id']
        assert client.get(f'/api/books/{other}/agent/notes').json() == {'notes': []}
        assert client.get(f'/api/books/{other}/agent/notes/translation.md').status_code == 404
        assert client.get('/api/books/unknown/agent/notes').status_code == 404
        assert client.request('DELETE', path, json={'expected_sha256': updated['sha256']}).status_code == 403
        assert client.request('DELETE', path, headers=auth, json={'expected_sha256': updated['sha256']}).json()['deleted']
        assert client.get(path).status_code == 404
        # A persistent note change alone must not reload the book iframe.
        client.post(route, headers=auth, json={'name': 'keep.md', 'content': 'retained'}).raise_for_status()
        time.sleep(1)
        assert client.get(f'/api/books/{book_id}').json()['revision'] == revision


def test_notes_remain_shared_when_working_copy_is_created_and_renamed(tmp_path):
    root = make_book(tmp_path / 'book')
    notes = AgentNotes(root)
    first = notes.create('context.md', 'Shared book context')
    create_source(root)
    assert not any(DIRECTORY in path for path in source_index(root)['files'])
    assert not (version_root(root, 'working') / DIRECTORY).exists()
    rename_working(root, 'Перевод')
    assert AgentNotes(root).read('context.md') == first


@pytest.mark.skipif(not AgentService.available(), reason='Optional Nemor unavailable')
def test_agent_manages_notes_and_recovers_them_in_new_chat_after_restart(tmp_path):
    root, library = make_book(tmp_path / 'book'), tmp_path / 'library'
    step = 0
    def complete(*, messages, **kwargs):
        nonlocal step
        result = json.loads(messages[-1]['content']) if messages[-1]['role'] == 'tool' else {}
        assert 'error' not in result, result
        step += 1
        if step == 1:
            assert 'notes_list' in messages[0]['content']
            return call('notes_create', {'name': 'translation.md', 'content': 'Yatima → Ятима'})
        if step == 2:
            return call('notes_read', {'name': 'translation.md'})
        if step == 3:
            return call('notes_update', {'name': 'translation.md', 'content': 'Yatima → Ятима; стиль: нейтральный', 'expected_sha256': result['sha256']})
        if step == 4:
            return call('notes_create', {'name': 'scratch.txt', 'content': 'temporary'})
        if step == 5:
            return call('notes_delete', {'name': 'scratch.txt', 'expected_sha256': result['sha256']})
        if step == 6:
            return call('notes_list', {})
        assert [note['name'] for note in result['notes']] == ['translation.md']
        return answer('Договорённости сохранены')
    with TestClient(create_app(root, library, agent_completion=complete)) as client:
        book_id = entry(client)['id']
        route = f'/api/books/{book_id}/agent'
        payload = turn('Сохрани переводческие решения')
        client.post(route + '/jobs', headers=headers(client), json=payload).raise_for_status()
        job = wait_job(client, book_id, payload['job_id'])
        assert job['status'] == 'completed', job
        assert {event['name'] for event in job['events']} >= {'notes_create', 'notes_read', 'notes_update', 'notes_delete', 'notes_list'}
        assert client.get(route + '/history').json()['edits'] == []

    def recovered(*, messages, **kwargs):
        assert 'Договорённости сохранены' not in json.dumps(messages, ensure_ascii=False)
        if messages[-1]['role'] == 'user':
            return call('notes_list', {})
        result = json.loads(messages[-1]['content'])
        if 'notes' in result:
            return call('notes_read', {'name': result['notes'][0]['name']})
        assert result['content'] == 'Yatima → Ятима; стиль: нейтральный'
        return answer('Продолжаю с сохранёнными решениями')
    with TestClient(create_app(root, library, agent_completion=recovered)) as client:
        client.post(route + '/chats', headers=headers(client)).raise_for_status()
        payload = turn('Продолжим перевод')
        client.post(route + '/jobs', headers=headers(client), json=payload).raise_for_status()
        job = wait_job(client, book_id, payload['job_id'])
        assert job['status'] == 'completed', job
        assert job['response'] == 'Продолжаю с сохранёнными решениями'
