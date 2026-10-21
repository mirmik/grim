import copy
import json
import threading
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from server.agent import AgentService, POLICY, completion_adapter
from server.agent_compaction import ANNOTATION
from server.app import create_app
from test_agent import answer, call, turn
from test_agent_chats import wait_chat
from test_server import make_book, entry, headers

pytestmark = pytest.mark.skipif(not AgentService.available(), reason='Optional Nemor unavailable')


def history():
    from nemor.core import Message
    messages = [Message('system', 'outdated instructions')]
    for i in range(4):
        messages.append(Message('user', f'Question {i}: ' + ('old context ' * 200 if i < 2 else 'recent'),
                                annotations={'grim.reading': {'page': i}}))
        if i == 3:
            messages.extend([
                Message('assistant', tool_calls=[{'id':'retained-call', 'type':'function', 'function':{'name':'notes_read', 'arguments':'{"name":"translation.md"}'}}]),
                Message('tool', 'Yatima → Ятима', tool_call_id='retained-call'),
            ])
        messages.append(Message('assistant', f'Answer {i}'))
    return [message.to_storage() for message in messages]


def seed(client, messages=None):
    book_id = entry(client)['id']
    route = f'/api/books/{book_id}/agent'
    chat = client.get(route).json()['chat']['id']
    client.app.state.agent.store.save_session(book_id, messages or history(), chat)
    return book_id, route, chat, route + f'/chats/{chat}'


def test_compaction_archives_raw_history_retains_exchanges_and_survives_restart(tmp_path):
    root, library = make_book(tmp_path / 'book'), tmp_path / 'library'
    seen = []
    def complete(*, messages, tools, config, **kwargs):
        assert config['tool_choice'] == 'none'
        assert tools and messages[-1]['role'] == 'user'
        seen.append(copy.deepcopy(messages))
        return answer('Переводим книгу. Yatima → Ятима. Стиль нейтральный. Продолжить главу.')
    with TestClient(create_app(root, library, agent_completion=complete)) as client:
        book_id, route, chat, operation = seed(client)
        store, auth = client.app.state.agent.store, headers(client)
        before = store.session(book_id, chat)
        other = client.post(route + '/chats', headers=auth).json()['chat']['id']
        payload = {'job_id': uuid.uuid4().hex}
        accepted = client.post(operation + '/compact', headers=auth, json=payload)
        assert accepted.status_code == 200 and accepted.json()['kind'] == 'compact'
        job = wait_chat(client, book_id, chat, payload['job_id'])
        assert job['status'] == 'completed' and 'Контекст сжат' in job['response'], job
        after = store.session(book_id, chat)
        assert after[0]['content'].startswith(POLICY)
        assert after[1]['_annotations'][ANNOTATION]
        assert after[2:] == before[5:]  # Last two entire exchanges, including tool pairs.
        assert store.session(book_id, other) == []
        assert 'outdated instructions' not in json.dumps(seen)
        archives = client.get(operation + '/archives', headers=auth).json()['archives']
        assert archives[0]['operation_id'] == payload['job_id']
        archived = client.get(operation + '/archives/' + payload['job_id'], headers=auth).json()
        assert archived['messages'] == before
        assert client.post(operation + '/compact', headers=auth, json=payload).json()['id'] == payload['job_id']
        assert len(seen) == 1
        actual = store.model_request(chat)['request']
        assert actual['messages'] == seen[0] and actual['tool_choice'] == 'none'
        assert client.get(route + '/history').json()['edits'] == []
        assert not (root / '.grim-agent-notes').exists()

    def continued(*, messages, **kwargs):
        assert any('Переводим книгу.' in (row.get('content') or '') for row in messages)
        assert 'old context old context' not in json.dumps(messages)
        return answer('Продолжаю перевод')
    with TestClient(create_app(root, library, agent_completion=continued)) as client:
        assert client.app.state.agent.store.session(book_id, chat) == after
        payload = {**turn('Продолжим'), 'chat_id': chat}
        client.post(route + '/jobs', headers=headers(client), json=payload).raise_for_status()
        assert wait_chat(client, book_id, chat, payload['job_id'])['response'] == 'Продолжаю перевод'
        assert client.get(operation + '/archives/' + archived['operation_id'], headers=headers(client)).json()['messages'] == before
        # A later compaction consumes the previous summary rather than treating
        # it as one of the two recent reader exchanges or accumulating summaries.
        second = {'job_id':uuid.uuid4().hex}
        client.post(operation + '/compact', headers=headers(client), json=second).raise_for_status()
        assert wait_chat(client, book_id, chat, second['job_id'])['status'] == 'completed'
        stored = client.app.state.agent.store.session(book_id, chat)
        assert sum(bool(row.get('_annotations', {}).get(ANNOTATION)) for row in stored) == 1
        assert len(client.get(operation + '/archives', headers=headers(client)).json()['archives']) == 2


@pytest.mark.parametrize('failure', ['empty', 'length', 'tools', 'oversize', 'network'])
def test_failed_or_unhelpful_summary_preserves_history(tmp_path, failure):
    def complete(**kwargs):
        if failure == 'network':
            raise ValueError('Model unavailable')
        if failure == 'tools':
            return call('notes_delete', {'name':'translation.md', 'expected_sha256':'0'*64})
        response = answer('' if failure == 'empty' else 'x' * 40_000 if failure == 'oversize' else 'truncated')
        if failure == 'length':
            response['choices'][0]['finish_reason'] = 'length'
        return response
    root = make_book(tmp_path / 'book')
    with TestClient(create_app(root, tmp_path / 'library', agent_completion=complete)) as client:
        book_id, route, chat, operation = seed(client)
        store, auth = client.app.state.agent.store, headers(client)
        before = store.session(book_id, chat)
        payload = {'job_id': uuid.uuid4().hex}
        client.post(operation + '/compact', headers=auth, json=payload).raise_for_status()
        job = wait_chat(client, book_id, chat, payload['job_id'])
        assert job['status'] == ('completed' if failure == 'oversize' else 'failed'), job
        assert store.session(book_id, chat) == before
        assert client.get(operation + '/archives', headers=auth).json()['archives'] == []
        assert (root / 'one.html').read_text().endswith('</html>')


def test_short_history_does_not_call_model_and_refresh_is_explicit_and_automatic(tmp_path):
    def no_model(**kwargs):
        pytest.fail('No model call expected')
    with TestClient(create_app(make_book(tmp_path / 'book'), tmp_path / 'library', agent_completion=no_model)) as client:
        book_id, route, chat, operation = seed(client, history()[:3])
        store, auth = client.app.state.agent.store, headers(client)
        before = store.session(book_id, chat)
        client.put('/api/agent/settings', headers=auth, json={'system_prompt':'Новые указания', 'model':'test'}).raise_for_status()
        assert client.post(operation + '/refresh-system').status_code == 403
        updated = client.post(operation + '/refresh-system', headers=auth)
        assert updated.status_code == 200
        current = store.session(book_id, chat)
        assert current[0]['content'] == POLICY + '\nНовые указания'
        assert current[1:] == before[1:] and current.count(current[0]) == 1
        assert client.get(route).json()['jobs'] == []
        client.put('/api/agent/settings', headers=auth, json={'system_prompt':'Ещё новее', 'model':'test'}).raise_for_status()
        preview = client.post(route + '/context', headers=auth, json={'chat_id':chat, 'reader_id':'test'}).json()
        assert preview['preview']['messages'][0]['content'].endswith('Ещё новее')
        payload = {'job_id':uuid.uuid4().hex}
        assert client.post(operation + '/compact', json=payload).status_code == 403
        client.post(operation + '/compact', headers=auth, json=payload).raise_for_status()
        job = wait_chat(client, book_id, chat, payload['job_id'])
        assert job['status'] == 'completed' and 'пока нечего' in job['response']
        assert store.session(book_id, chat) == current


def test_cancel_and_session_exclusion_while_compaction_runs(tmp_path):
    started, release = threading.Event(), threading.Event()
    def complete(**kwargs):
        started.set()
        release.wait(8)
        return answer('Saved summary')
    with TestClient(create_app(make_book(tmp_path / 'book'), tmp_path / 'library', agent_completion=complete)) as client:
        book_id, route, chat, operation = seed(client)
        store, auth = client.app.state.agent.store, headers(client)
        before = store.session(book_id, chat)
        payload = {'job_id':uuid.uuid4().hex}
        try:
            client.post(operation + '/compact', headers=auth, json=payload).raise_for_status()
            assert started.wait(3)
            assert client.post(operation + '/refresh-system', headers=auth).status_code == 409
            assert client.post(operation + '/compact', headers=auth, json={'job_id':uuid.uuid4().hex}).status_code == 409
            assert client.post(route + '/jobs', headers=auth, json=turn()).status_code == 409
            other = client.post(route + '/chats', headers=auth).json()['chat']['id']
            assert client.post(route + f'/chats/{other}/refresh-system', headers=auth).status_code == 409
            stopped = client.post(route + f"/jobs/{payload['job_id']}/stop", headers=auth).json()
            assert stopped['status'] == 'stopping'
        finally:
            release.set()
        assert wait_chat(client, book_id, chat, payload['job_id'])['status'] == 'cancelled'
        assert store.session(book_id, chat) == before
        assert store.archives(book_id, chat) == []


def test_session_changed_during_summary_is_not_overwritten_and_books_are_isolated(tmp_path):
    def complete(**kwargs):
        store.save_session(book_id, [{'role':'user','content':'external session update'}], chat)
        return answer('Saved summary')
    with TestClient(create_app(make_book(tmp_path / 'book'), tmp_path / 'library', agent_completion=complete)) as client:
        book_id, route, chat, operation = seed(client)
        store, auth = client.app.state.agent.store, headers(client)
        other = client.post('/api/library/create', headers=auth, json={'title':'Other'}).json()['id']
        foreign = f'/api/books/{other}/agent/chats/{chat}'
        assert client.post(foreign + '/refresh-system', headers=auth).status_code == 404
        assert client.post(foreign + '/compact', headers=auth, json={'job_id':uuid.uuid4().hex}).status_code == 404
        assert client.get(foreign + '/archives', headers=auth).status_code == 404
        payload = {'job_id':uuid.uuid4().hex}
        client.post(operation + '/compact', headers=auth, json=payload).raise_for_status()
        job = wait_chat(client, book_id, chat, payload['job_id'])
        assert job['status'] == 'failed' and 'изменился' in job['error']
        assert store.session(book_id, chat)[0]['content'] == 'external session update'
        assert store.archives(book_id, chat) == []


def test_completion_transport_forbids_tools_for_compaction(monkeypatch):
    sent = []
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=answer('summary'))
    monkeypatch.setattr('server.agent.model_client_options', lambda _: {'transport':httpx.MockTransport(handler)})
    settings = {'endpoint':'http://model/v1', 'model':'test', 'max_tokens':512, 'timeout_seconds':2}
    completion_adapter(settings)(messages=[{'role':'user','content':'Summarize'}], tools=[{'type':'function'}], config={'tool_choice':'none'})
    assert sent[0]['tool_choice'] == 'none' and sent[0]['max_tokens'] == 512
