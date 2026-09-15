"""Real Nemor loop with deterministic completion; no model/network required."""
import json
import threading
import time
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from server.agent import AgentService, Settings, completion_adapter
from server.agent_store import AgentStore
from server.app import create_app
from server.book_tools import BookTools
from test_server import make_book, entry, headers


def answer(text):
    return {'choices': [{'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}]}


def call(name, args):
    return {'choices': [{'message': {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': uuid.uuid4().hex, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}
    ]}, 'finish_reason': 'tool_calls'}]}


def turn(message='Добавь пример'):
    return dict(job_id=uuid.uuid4().hex, message=message, reader_id='reader-one',
                context=dict(page_id='one', selection='First', visible_text='First', anchor='p', viewer_revision=0))


def wait_job(client, book_id, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = next(j for j in client.get(f'/api/books/{book_id}/agent').json()['jobs'] if j['id'] == job_id)
        if job['status'] not in ('queued', 'running', 'stopping'):
            return job
        time.sleep(.02)
    pytest.fail('Agent did not finish')


@pytest.mark.skipif(not AgentService.available(), reason='Install optional Nemor for runtime integration')
def test_real_loop_shared_files_context_history_and_restart(tmp_path):
    root = make_book(tmp_path / 'book')
    library = tmp_path / 'library'
    seen = []
    def complete(*, messages, **kwargs):
        seen.append(messages)
        last = messages[-1]
        if last['role'] == 'user':
            return call('reading_context', {})
        result = json.loads(last['content'])
        if messages[-2]['tool_calls'][0]['function']['name'] == 'reading_context':
            assert result['at_send']['selection'] == 'First'
            assert result['current']['selection'] == 'live selection'
            return call('book_read', {'path': 'one.html'})
        if messages[-2]['tool_calls'][0]['function']['name'] == 'book_read':
            return call('book_replace', dict(path='one.html', target='First', replacement='First + example', expected_sha256=result['sha256']))
        assert 'error' not in result, result
        return answer('Пример добавлен')

    with TestClient(create_app(root, library, agent_completion=complete)) as client:
        book_id, auth = entry(client)['id'], headers(client)
        context = dict(reader_id='reader-one', sequence=1, book_id=book_id, page_id='one', selection='live selection')
        assert client.post('/api/viewer/context', json=context, headers=auth).status_code == 200
        payload = turn()
        route = f'/api/books/{book_id}/agent/jobs'
        assert client.post(route, json=payload, headers=auth).status_code == 200
        job = wait_job(client, book_id, payload['job_id'])
        assert job['status'] == 'completed', job
        assert job['response'] == 'Пример добавлен'
        assert 'First + example' in (root / 'one.html').read_text()
        assert 'First + example' in client.get(f'/book/{book_id}/one.html').text
        assert client.get('/api/context', params={'reader_id': 'reader-one', 'book_id': book_id}).json()['context']['book']['root'] == str(root)
        assert client.post(route, json=payload, headers=auth).json() == job
        assert len(seen) == 4
        edits = client.get(f'/api/books/{book_id}/agent/history').json()['edits']
        assert len(edits) == 1 and edits[0]['status'] == 'applied'
        edit = client.get(f'/api/books/{book_id}/agent/history/{edits[0]["id"]}').json()
        assert 'First</p>' in edit['before_text'] and 'example' in edit['after_text']
        assert client.post(route, json={**payload, 'message': 'Другой запрос'}, headers=auth).status_code == 409

    def continued(*, messages, **kwargs):
        assert any(m.get('content') == 'Пример добавлен' for m in messages)
        return answer('Помню разговор')
    with TestClient(create_app(root, library, agent_completion=continued)) as client:
        assert client.get(f'/api/books/{book_id}/agent').json()['jobs'][0]['response'] == 'Пример добавлен'
        payload = turn('Что мы сделали?')
        client.post(route, json=payload, headers=headers(client))
        assert wait_job(client, book_id, payload['job_id'])['response'] == 'Помню разговор'


@pytest.mark.skipif(not AgentService.available(), reason='Install optional Nemor for runtime integration')
def test_external_edit_conflict_and_book_isolation(tmp_path):
    root = make_book(tmp_path / 'book')
    other = make_book(tmp_path / 'other', text='Other')
    def complete(*, messages, **kwargs):
        if messages[-1]['role'] == 'user':
            assert not any('Other conversation' in str(m) for m in messages)
            return call('book_read', {'path': 'one.html'})
        result = json.loads(messages[-1]['content'])
        if messages[-2]['tool_calls'][0]['function']['name'] == 'book_read':
            (root / 'one.html').write_text('External edit')
            return call('book_replace', dict(path='one.html', target='First', replacement='Local edit', expected_sha256=result['sha256']))
        assert 'error' in result
        return answer('Конфликт: перечитать книгу')
    with TestClient(create_app(root, tmp_path / 'library', agent_completion=complete)) as client:
        auth, book_id = headers(client), entry(client)['id']
        other_id = client.post('/api/library/add', json={'root': str(other)}, headers=auth).json()['id']
        client.app.state.agent.store.save_session(other_id, [{'role': 'user', 'content': 'Other conversation'}])
        payload = turn()
        client.post(f'/api/books/{book_id}/agent/jobs', json=payload, headers=auth)
        assert wait_job(client, book_id, payload['job_id'])['status'] == 'completed'
        assert (root / 'one.html').read_text() == 'External edit'
        assert 'Other' in (other / 'one.html').read_text()
        assert client.get(f'/api/books/{other_id}/agent').json()['jobs'] == []
        assert client.post(f'/api/books/{other_id}/agent/jobs/{payload["job_id"]}/stop', headers=auth).status_code == 404


@pytest.mark.skipif(not AgentService.available(), reason='Install optional Nemor for runtime integration')
def test_single_active_job_dedup_and_stop(tmp_path):
    root = make_book(tmp_path / 'book')
    started, release = threading.Event(), threading.Event()
    def complete(**kwargs):
        started.set()
        assert release.wait(5)
        return call('book_write', {'path': 'stopped.txt', 'content': 'should not run', 'expected_sha256': None})
    with TestClient(create_app(root, tmp_path / 'library', agent_completion=complete)) as client:
        book_id, auth, payload = entry(client)['id'], headers(client), turn()
        route = f'/api/books/{book_id}/agent/jobs'
        try:
            client.post(route, json=payload, headers=auth)
            assert started.wait(3)
            assert client.post(route, json=payload, headers=auth).status_code == 200
            assert client.post(route, json=turn(), headers=auth).status_code == 409
            assert client.post(route + '/' + payload['job_id'] + '/stop', headers=auth).json()['status'] == 'stopping'
        finally:
            release.set()
        assert wait_job(client, book_id, payload['job_id'])['status'] == 'cancelled'
        assert not (root / 'stopped.txt').exists()


def test_api_boundary_settings_and_missing_runtime(tmp_path, monkeypatch):
    root = make_book(tmp_path / 'book')
    monkeypatch.setattr(AgentService, 'available', staticmethod(lambda: False))
    with TestClient(create_app(root, tmp_path / 'library')) as client:
        auth, book_id = headers(client), entry(client)['id']
        settings = {'model': 'local-model', 'api_token': 'private-test-token'}
        assert client.put('/api/agent/settings', json=settings).status_code == 403
        assert client.put('/api/agent/settings', json=settings, headers={**auth, 'Origin': 'null'}).status_code == 403
        saved = client.put('/api/agent/settings', json=settings, headers=auth)
        assert saved.status_code == 200 and saved.json()['has_token']
        assert 'private-test-token' not in saved.text
        assert 'api_token' not in client.get('/api/agent/settings').json()
        assert client.put('/api/agent/settings', json={'model': 'changed'}, headers=auth).json()['has_token']
        assert not client.put('/api/agent/settings', json={'clear_token': True}, headers=auth).json()['has_token']
        assert client.post(f'/api/books/{book_id}/agent/jobs', json=turn()).status_code == 403
        assert client.post(f'/api/books/{book_id}/agent/jobs', json=turn(), headers=auth).status_code == 503
        assert client.post('/api/agent/probe').status_code == 403
        assert client.get(f'/book/{book_id}/one.html').status_code == 200
        assert client.get('/api/context').status_code == 200


def test_book_tools_paths_hashes_and_recovery(tmp_path):
    root = make_book(tmp_path / 'book')
    store = AgentStore(tmp_path)
    tools = BookTools(root, 'book', 'job', store, {}, lambda: None)
    (root / 'alias.html').symlink_to(root / 'one.html')
    for path in ('../other.html', '/tmp/a.html', 'alias.html', '.source/a.html', 'a/../../x.html'):
        with pytest.raises(ValueError):
            tools.write(dict(path=path, content='oops', expected_sha256=None))
    original = tools.read({'path': 'one.html'})
    with pytest.raises(ValueError, match='изменился'):
        tools.write(dict(path='one.html', content='oops', expected_sha256=None))
    with pytest.raises(KeyError):
        tools.write(dict(path='book.json', content='{"pages": []}', expected_sha256=tools.read({'path': 'book.json'})['sha256']))
    tools.write(dict(path='new.html', content='new', expected_sha256=None))
    assert tools.read({'path': 'one.html'}) == original
    payload = turn()
    store.submit('book', payload)
    store.update_job(payload['job_id'], 'running')
    recovered = AgentStore(tmp_path)
    assert recovered.job(payload['job_id'])['status'] == 'interrupted'
    assert recovered.submit('book', payload)[1] is False
    assert recovered.history('book')[0]['status'] == 'applied'
    assert recovered.path.stat().st_mode & 0o777 == 0o600


def test_model_transport(monkeypatch):
    def handle(request):
        assert request.url == 'http://model.test/v1/chat/completions'
        assert request.headers['authorization'] == 'Bearer secret'
        payload = json.loads(request.content)
        assert payload['model'] == 'test' and payload['stream'] is False
        assert payload['tool_choice'] == 'auto'
        return httpx.Response(200, json=answer('ok'))
    client_type = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: client_type(transport=httpx.MockTransport(handle), **kwargs))
    config = Settings(endpoint='http://model.test', model='test', api_token='secret').model_dump()
    result = completion_adapter(config)(messages=[], tools=[{'type': 'function'}], config={})
    assert result['choices'][0]['message']['content'] == 'ok'


@pytest.mark.skipif(not AgentService.available(), reason='Install optional Nemor for runtime integration')
def test_iteration_limit_is_not_success_and_orphan_call_is_not_replayed(tmp_path):
    root = make_book(tmp_path / 'book')
    def complete(*, messages, **kwargs):
        # Stored orphan tool call gets a synthetic result, never execution.
        interrupted = [m for m in messages if m.get('tool_call_id') == 'lost-call']
        assert len(interrupted) == 1 and 'interrupted' in interrupted[0]['content']
        return call('book_read', {'path': 'one.html'})
    with TestClient(create_app(root, tmp_path / 'library', agent_completion=complete)) as client:
        book_id, auth = entry(client)['id'], headers(client)
        client.app.state.agent.store.save_session(book_id, [{'role':'assistant', 'content':'', 'tool_calls':[
            {'id':'lost-call', 'type':'function', 'function':{'name':'book_write', 'arguments':json.dumps(
                dict(path='orphan.txt', content='never replay', expected_sha256=None))}}
        ]}])
        client.put('/api/agent/settings', json={'model':'fake', 'max_iterations':1}, headers=auth)
        payload = turn()
        client.post(f'/api/books/{book_id}/agent/jobs', json=payload, headers=auth)
        job = wait_job(client, book_id, payload['job_id'])
        assert job['status'] == 'failed' and 'предел шагов' in job['error'], job
        assert not (root / 'orphan.txt').exists()


def test_probe_and_transport_failures(tmp_path, monkeypatch):
    root = make_book(tmp_path / 'book')
    async_type, sync_type = httpx.AsyncClient, httpx.Client
    def handle(request):
        if request.url.path == '/v1/models':
            return httpx.Response(200, json={'data':[{'id':'local'}, {}, 'invalid']})
        return httpx.Response(401, text='Do not expose server body or private tokens')
    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: async_type(transport=transport, **kwargs))
    with TestClient(create_app(root, tmp_path / 'library')) as client:
        assert client.post('/api/agent/probe', headers=headers(client)).json() == {'models':['local']}
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: sync_type(transport=transport, **kwargs))
    with pytest.raises(ValueError, match='HTTP 401') as error:
        completion_adapter(Settings(model='test').model_dump())(messages=[], tools=[], config={})
    assert 'Do not expose' not in str(error.value)
