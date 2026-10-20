from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import socket
import time

import pytest
from fastapi.testclient import TestClient

from server.access_tokens import AccessTokens
from server.app import create_app
from server.mobile_access import MobileAccess, COOKIE

INITIAL = 'disposable-initial-test-credential-123456789'
INITIAL_HASH = hashlib.sha256(INITIAL.encode()).hexdigest()


def test_hash_only_storage_revoke_and_restart(tmp_path):
    path = tmp_path / 'tokens.json'
    tokens = AccessTokens(path, INITIAL_HASH)
    created = tokens.create('Основной смартфон')
    token, entry = created['token'], created['entry']
    assert tokens.authenticate(token) == entry['id']
    assert tokens.authenticate(INITIAL) == 'legacy'
    assert token not in path.read_text() and INITIAL not in path.read_text()
    assert 'hash' not in json.dumps(tokens.list()) and token not in json.dumps(tokens.list())
    assert path.stat().st_mode & 0o777 == 0o600
    tokens.touch(entry['id'])
    assert tokens.list()[0]['last_used_at'] is not None
    tokens.revoke(entry['id'])
    tokens.revoke('legacy')
    restarted = AccessTokens(path, INITIAL_HASH)
    assert restarted.authenticate(token) is None and restarted.authenticate(INITIAL) is None
    assert not restarted.active(entry['id'])
    restarted.revoke(entry['id'])  # Repeated revoke is harmless.
    with pytest.raises(KeyError):
        restarted.revoke('missing')


def test_registry_permissions_and_failed_write_preserve_active_state(tmp_path, monkeypatch):
    path = tmp_path / 'tokens.json'
    tokens = AccessTokens(path, INITIAL_HASH)
    original = path.read_bytes()
    def fail(*args):
        raise OSError('simulated full disk')
    monkeypatch.setattr('server.access_tokens.os.replace', fail)
    with pytest.raises(OSError):
        tokens.revoke('legacy')
    assert tokens.active('legacy') and path.read_bytes() == original
    assert not list(tmp_path.glob('.access-tokens-*'))
    path.chmod(0o644)
    with pytest.raises(ValueError, match='0600'):
        AccessTokens(path, INITIAL_HASH)


def test_concurrent_token_creation_does_not_lose_credentials(tmp_path):
    path = tmp_path / 'tokens.json'
    tokens = AccessTokens(path, INITIAL_HASH)
    with ThreadPoolExecutor(max_workers=4) as pool:
        created = list(pool.map(tokens.create, [f'Device {i}' for i in range(12)]))
    restarted = AccessTokens(path, INITIAL_HASH)
    assert len(restarted.list()) == 13
    assert all(restarted.authenticate(item['token']) == item['entry']['id'] for item in created)


def test_access_credential_cannot_forge_another_devices_session_or_book_link(tmp_path):
    tokens = AccessTokens(tmp_path/'tokens.json', INITIAL_HASH)
    victim = tokens.create('Victim')['entry']['id']
    current = MobileAccess(8444, bytes.fromhex(INITIAL_HASH), tokens=tokens)
    former_holder = MobileAccess(8444, bytes.fromhex(INITIAL_HASH))
    expires = str(int(time.time())+86400)
    data = f'{victim}.{expires}.0123456789abcdef0123456789abcdef'
    forged_cookie = data+'.'+former_holder.sign('session',data)
    book = 'a'*32
    forged_link = expires+'.'+victim+'.'+former_holder.sign('book:'+book+':'+victim,expires)
    assert not current.valid_session(forged_cookie)
    assert not current.valid_book_access(book, forged_link)
    valid = current.session(victim)
    assert current.valid_session(valid)
    assert MobileAccess(8444, bytes.fromhex(INITIAL_HASH), tokens=AccessTokens(tmp_path/'tokens.json',INITIAL_HASH)).valid_session(valid)
    assert (tmp_path/'tokens.key').stat().st_mode & 0o777 == 0o600
    (tmp_path/'tokens.key').unlink()
    with pytest.raises(ValueError,match='signing key missing'):
        AccessTokens(tmp_path/'tokens.json',INITIAL_HASH)


@pytest.fixture
def configured(tmp_path, monkeypatch):
    token = tmp_path / 'initial.token'
    token.write_text(INITIAL)
    token.chmod(0o600)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    monkeypatch.setenv('GRIM_MOBILE_PORT', str(port))
    monkeypatch.setenv('GRIM_MOBILE_HOST', '127.0.0.1')
    monkeypatch.setenv('GRIM_ACCESS_TOKEN_FILE', str(token))
    monkeypatch.setenv('GRIM_ACCESS_TOKENS_FILE', str(tmp_path / 'registry.json'))
    monkeypatch.delenv('GRIM_MOBILE_TLS_CERT', raising=False)
    monkeypatch.delenv('GRIM_MOBILE_TLS_KEY', raising=False)
    book = tmp_path / 'book'
    book.mkdir()
    (book / 'book.json').write_text(json.dumps({'title':'Test', 'pages':[{'id':'one','title':'One','path':'one.html'}]}))
    (book / 'one.html').write_text('<html><body>Private chapter</body></html>')
    return book, tmp_path / 'library', f'https://testserver:{port}'


def test_management_authority_csrf_and_credential_redaction(configured):
    book, library, mobile = configured
    with TestClient(create_app(book, library), base_url='http://testserver:8000') as web:
        bootstrap = web.get('/api/library').json()
        assert bootstrap['can_manage_access']
        headers = {'X-Grim-Viewer':bootstrap['writer_token']}
        assert web.get('/api/access-tokens').status_code == 403
        for origin in ('https://attacker.example', 'null'):
            assert web.post('/api/access-tokens', headers={**headers, 'Origin':origin}, json={'name':'Bad'}).status_code == 403
        assert web.post('/api/access-tokens', headers={**headers,'Sec-Fetch-Site':'same-site'}, json={'name':'Bad'}).status_code == 403
        for name in ('   ', 'line\nbreak', 'x'*81):
            assert web.post('/api/access-tokens', headers=headers, json={'name':name}).status_code == 422
        created = web.post('/api/access-tokens', headers=headers, json={'name':'Phone'})
        assert created.status_code == 201 and created.headers['cache-control'] == 'no-store'
        raw = created.json()['token']
        listing = web.get('/api/access-tokens', headers=headers)
        assert raw not in listing.text and 'hash' not in listing.text
        credential = {'Authorization':'Bearer '+raw, **headers, 'Host':'testserver:8000'}
        assert not web.get(mobile+'/api/library', headers=credential).json()['can_manage_access']
        for method in ('get', 'post', 'delete'):
            path = '/api/access-tokens' + ('/legacy' if method == 'delete' else '')
            args = {'json':{'name':'Escalation'}} if method == 'post' else {}
            assert getattr(web, method)(mobile+path, headers=credential, **args).status_code == 403


def test_revocation_invalidates_bearer_cookie_and_sandbox_links_only_for_one_device(configured):
    book, library, mobile = configured
    with TestClient(create_app(book, library), base_url='http://testserver:8000') as web:
        bootstrap = web.get('/api/library').json()
        headers = {'X-Grim-Viewer':bootstrap['writer_token']}
        first = web.post('/api/access-tokens', headers=headers, json={'name':'First'}).json()
        second = web.post('/api/access-tokens', headers=headers, json={'name':'Second'}).json()
        bearer = {'Authorization':'Bearer '+first['token']}
        assert web.post(mobile+'/auth/token', data={'token':first['token']}, follow_redirects=False).status_code == 303
        cookie = web.cookies.get(COOKIE)
        book_id = bootstrap['books'][0]['id']
        prefix = web.get(mobile+'/api/books/'+book_id).json()['content_prefix']
        web.cookies.clear()
        assert web.get(mobile+prefix+'one.html').status_code == 200
        assert web.delete('/api/access-tokens/'+first['entry']['id'], headers=headers).status_code == 200
        assert web.get(mobile+'/api/library', headers=bearer).status_code == 401
        assert web.get(mobile+'/api/library', headers={'Cookie':COOKIE+'='+cookie}).status_code == 401
        assert web.get(mobile+prefix+'one.html').status_code == 401
        assert web.post(mobile+'/auth/token', data={'token':first['token']}, follow_redirects=False).status_code == 401
        assert web.get(mobile+'/api/library', headers={'Authorization':'Bearer '+second['token']}).status_code == 200
        assert web.get(mobile+'/api/library', headers={'Authorization':'Bearer '+INITIAL}).status_code == 200
    with TestClient(create_app(book, library), base_url=mobile) as restarted:
        assert restarted.get('/api/library', headers=bearer).status_code == 401
        assert restarted.get('/api/library', headers={'Authorization':'Bearer '+second['token']}).status_code == 200


def test_migration_keeps_old_cookie_and_links_but_legacy_revoke_disables_them(configured):
    book, library, mobile = configured
    old = MobileAccess(int(mobile.rsplit(':',1)[1]), hashlib.sha256(INITIAL.encode()).digest())
    cookie = old.session()
    with TestClient(create_app(book, library), base_url='http://testserver:8000') as web:
        bootstrap = web.get('/api/library').json()
        headers = {'X-Grim-Viewer':bootstrap['writer_token']}
        book_id = bootstrap['books'][0]['id']
        path = f'/book/{book_id}/__grim_access_{old.book_access(book_id)}__/one.html'
        assert web.get(mobile+'/api/library', headers={'Cookie':COOKIE+'='+cookie}).status_code == 200
        assert web.get(mobile+path).status_code == 200
        assert web.delete('/api/access-tokens/legacy', headers=headers).status_code == 200
        assert web.get(mobile+'/api/library', headers={'Cookie':COOKIE+'='+cookie}).status_code == 401
        assert web.get(mobile+path).status_code == 401

