import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from server.app import create_app
from server.book_tools import BookTools
from server.versions import SOURCE, create_source, version_root
from test_server import make_book, entry, headers


def test_optional_snapshot_resources_context_notes_and_restart(tmp_path):
    root = make_book(tmp_path / 'book')
    (root / 'style.css').write_text('body { color: red }')
    (root / 'script.js').write_text('const original = true')
    (root / 'image.png').write_bytes(b'original image')
    library = tmp_path / 'library'
    with TestClient(create_app(root, library)) as client:
        book_id, auth = entry(client)['id'], headers(client)
        api = f'/api/books/{book_id}'
        assert client.get(api).json()['has_source'] is False
        assert client.get(api + '?version=source').status_code == 404
        assert client.post(api + '/working-copy').status_code == 403
        assert client.post(api + '/working-copy', headers=auth).status_code == 200
        assert client.post(api + '/working-copy', headers=auth).status_code == 409
        copy = version_root(root, 'working')
        for name in ('one.html', 'style.css', 'script.js', 'image.png'):
            original = (root / name).read_bytes()
            (copy / name).write_bytes(b'changed')
            response = client.get(f'/book-source/{book_id}/{name}?download=1')
            assert response.content == original
            assert 'sandbox allow-scripts' in response.headers['content-security-policy']
        # The original has its own outline, even when the working page disappears.
        (copy / 'book.json').write_text(json.dumps({'title': 'Changed', 'pages': []}))
        original = client.get(api + '?version=source').json()
        assert original['pages'][0]['id'] == 'one'
        assert original['root'] == str(root)
        assert original['working_root'] == str(copy)
        context = dict(book_id=book_id, reader_id='test', sequence=1, page_id='one', version='source')
        assert client.post('/api/viewer/context', json=context, headers=auth).status_code == 200
        saved = client.get('/api/context').json()['context']
        assert saved['version'] == 'source' and saved['book']['root'] == original['root']
        assert client.post('/api/viewer/context', json={**context, 'sequence': 2, 'version': 'working'}, headers=auth).status_code == 404
        note = dict(id='source-note', page_id='one', anchor=dict(exact='First', start=0, end=5))
        assert client.put(api + '/notes?version=source', json={'notes': [note]}, headers=auth).status_code == 200
        assert client.get(api + '/notes').json()['notes'] == []
        assert client.get(api + '/notes?version=source').json()['notes'][0]['id'] == 'source-note'
        assert not (root / SOURCE / 'book' / '.grim-notes.json').exists()
        for name in ('.grim-source/book/one.html', '.grim-source/index.json', '.grim-source-notes.json'):
            assert client.get(f'/book/{book_id}/{name}').status_code == 404
        (copy / 'alias.html').symlink_to(root / 'one.html')
        assert client.get(f'/book/{book_id}/alias.html').status_code == 404
    with TestClient(create_app(root, library)) as client:
        assert client.get(api).json()['has_source'] is True
        assert client.get(api + '?version=source').json()['title'] == 'Test'
        assert 'First' in client.get(f'/book-source/{book_id}/one.html').text
        assert client.get(api + '/notes?version=source').json()['notes'][0]['id'] == 'source-note'
        (root / 'one.html').write_text('tampered')
        assert client.get(f'/book-source/{book_id}/one.html').status_code == 409


def test_source_creation_failure_is_atomic(tmp_path, monkeypatch):
    root = make_book(tmp_path / 'book')
    (root / 'linked.html').symlink_to(root / 'one.html')
    with pytest.raises(HTTPException, match='симлинки'):
        create_source(root)
    assert not list(root.glob('.grim-source*'))
    (root / 'linked.html').unlink()
    from server import versions
    original = versions.content_files
    calls = 0
    def files(directory):
        nonlocal calls
        calls += 1
        if calls == 2:
            (root / 'one.html').write_text('edited while copying')
        yield from original(directory)
    monkeypatch.setattr(versions, 'content_files', files)
    with pytest.raises(HTTPException, match='изменилась'):
        create_source(root)
    assert not list(root.glob('.grim-source*'))


def test_tools_source_read_only_and_hash_validation(tmp_path):
    root = make_book(tmp_path / 'book')
    create_source(root)
    copy = version_root(root, 'working')
    (copy / 'one.html').write_text('Working')
    tools = BookTools(root, 'book', 'job', None, {}, lambda: None)
    assert tools.read({'path': 'one.html'})['text'] == 'Working'
    original = tools.read({'path': 'one.html', 'version': 'source'})
    assert 'First' in original['text']
    assert tools.search({'query': 'First', 'version': 'source'})['hits'][0]['path'] == 'one.html'
    assert tools.search({'query': 'First'})['hits'] == []
    for relative in ('.grim-source/book/one.html', 'alias.html'):
        if relative == 'alias.html':
            (copy / relative).symlink_to(root / 'one.html')
        with pytest.raises(ValueError):
            tools.write({'path': relative, 'content': 'bad', 'expected_sha256': original['sha256']})
    for operation in (tools.write, tools.replace):
        with pytest.raises(ValueError, match='только для чтения'):
            operation({'path': 'one.html', 'version': 'source'})
    (root / 'one.html').write_text('tampered')
    with pytest.raises(HTTPException, match='целостность'):
        tools.read({'path': 'one.html', 'version': 'source'})


def test_agent_receives_source_snapshot_when_working_outline_differs(tmp_path):
    from test_agent import answer, call, wait_job, turn
    from server.agent import AgentService
    if not AgentService.available():
        pytest.skip('Optional Nemor unavailable')
    root = make_book(tmp_path / 'book')
    create_source(root)
    (version_root(root, 'working') / 'book.json').write_text(json.dumps({'title': 'Working', 'pages': []}))
    def complete(*, messages, **kwargs):
        if messages[-1]['role'] == 'user':
            return call('reading_context', {})
        result = json.loads(messages[-1]['content'])
        if messages[-2]['tool_calls'][0]['function']['name'] == 'reading_context':
            assert result['at_send']['version'] == 'source'
            return call('book_read', {'path': 'one.html', 'version': 'source'})
        assert 'First' in result['text']
        return answer('Прочитал оригинал')
    with TestClient(create_app(root, tmp_path / 'library', agent_completion=complete)) as client:
        book_id = entry(client)['id']
        payload = turn('Объясни оригинал')
        payload['context']['version'] = 'source'
        response = client.post(f'/api/books/{book_id}/agent/jobs', json=payload, headers=headers(client))
        assert response.status_code == 200
        result = wait_job(client, book_id, payload['job_id'])
        assert result['status'] == 'completed', result
        assert result['context']['version'] == 'source'


def test_main_is_default_and_keeps_notes_when_copy_is_created(tmp_path):
    root = make_book(tmp_path / 'book')
    with TestClient(create_app(root, tmp_path / 'library')) as client:
        book_id, auth = entry(client)['id'], headers(client)
        api = f'/api/books/{book_id}'
        note = dict(id='main-note', page_id='one', text='Before copy', anchor=dict(exact='First', start=0, end=5))
        client.put(api+'/notes', json={'notes':[note]}, headers=auth).raise_for_status()
        created = client.post(api+'/working-copy', headers=auth).json()
        assert created['version'] == 'source'
        assert created['content_prefix'] == f'/book/{book_id}/__grim_source__/'
        copy=version_root(root,'working')
        (copy/'one.html').write_text('Edited copy')
        outline=json.loads((copy/'book.json').read_text())
        outline['title']='Copy title'
        (copy/'book.json').write_text(json.dumps(outline))
        assert entry(client)['title']=='Test'
        main = client.get(api).json()
        working = client.get(api+'?version=working').json()
        assert main['version'] == 'source' and working['version'] == 'working'
        assert 'First' in client.get(main['content_prefix']+'one.html').text
        assert 'Edited copy' in client.get(working['content_prefix']+'one.html').text
        assert client.get(api+'/notes?version=source').json()['notes'][0]['text'] == 'Before copy'
        assert client.get(main['content_prefix']+'one.html?download=1').headers['content-disposition'].startswith('attachment;')


def test_rename_working_copy_moves_folder_and_keeps_main_notes_and_urls(tmp_path):
    root = make_book(tmp_path / 'book')
    with TestClient(create_app(root, tmp_path / 'library')) as client:
        book_id, auth = entry(client)['id'], headers(client)
        api = f'/api/books/{book_id}'
        client.post(api+'/working-copy',headers=auth).raise_for_status()
        copy=version_root(root,'working')
        (copy/'one.html').write_text('Copy text')
        assert copy.name=='рабочая-копия'
        assert client.patch(api+'/working-copy',json={'title':'Перевод'}).status_code==403
        result=client.patch(api+'/working-copy',json={'title':'Перевод'},headers=auth)
        assert result.status_code==200,result.text
        assert result.json()['working_name']=='Перевод'
        assert version_root(root,'working')==root/'перевод'
        assert not copy.exists()
        assert (root/'one.html').read_text().find('First')>=0
        assert client.get(f'/book/{book_id}/one.html').text.endswith('Copy text')
        assert client.get(api).json()['title']=='Test'
        assert client.get(api+'?version=working').json()['title']=='Перевод'
        assert client.patch(api+'/working-copy',json={'title':'  '},headers=auth).status_code==422
        assert client.patch(api+'/working-copy',json={'title':'book.json'},headers=auth).status_code==200
        assert (root/'book.json').is_file()


def test_tools_edit_only_visible_copy_and_follow_renames(tmp_path):
    from server.agent_store import AgentStore
    from server.versions import rename_working, source_file
    root=make_book(tmp_path/'book')
    create_source(root)
    store=AgentStore(tmp_path)
    tools=BookTools(root,'book','job',store,{},lambda:None)
    before=tools.read({'path':'one.html'})
    tools.write({'path':'one.html','content':'<p>Edited copy</p>','expected_sha256':before['sha256']})
    assert 'First' in source_file(root,'one.html').read_text()
    outline=tools.read({'path':'book.json'})
    tools.write({'path':'book.json','content':outline['text'],'expected_sha256':outline['sha256']})
    rename_working(root,'Перевод')
    assert tools.read({'path':'one.html'})['text']=='<p>Edited copy</p>'
