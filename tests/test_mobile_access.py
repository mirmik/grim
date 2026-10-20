import hashlib
import time
from unittest.mock import patch

import pytest

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from server.mobile_access import MobileAccess, MobileAccessMiddleware

TOKEN = 'disposable-test-token-not-for-production-12345'


def test_direct_tls_config_requires_pair_and_private_owned_key(tmp_path, monkeypatch):
    token, cert, key = (tmp_path / name for name in ('token', 'cert.pem', 'key.pem'))
    token.write_text(TOKEN)
    token.chmod(0o600)
    cert.write_text('test certificate')
    key.write_text('test private key')
    key.chmod(0o600)
    monkeypatch.setenv('GRIM_MOBILE_PORT', '8444')
    monkeypatch.setenv('GRIM_ACCESS_TOKEN_FILE', str(token))
    monkeypatch.setenv('GRIM_MOBILE_TLS_CERT', str(cert))
    monkeypatch.delenv('GRIM_MOBILE_TLS_KEY', raising=False)
    with pytest.raises(ValueError, match='configured together'):
        MobileAccess.from_env()
    monkeypatch.setenv('GRIM_MOBILE_TLS_KEY', str(key))
    access = MobileAccess.from_env()
    assert access.tls_cert == str(cert) and access.tls_key == str(key)
    key.chmod(0o644)
    with pytest.raises(ValueError, match='mode 0600'):
        MobileAccess.from_env()


def client(access):
    async def content(request):
        return JSONResponse({'private': True})
    app = Starlette(routes=[Route('/{path:path}', content, methods=['GET', 'POST'])])
    return TestClient(MobileAccessMiddleware(app, access), base_url='https://testserver:8002')


def test_token_login_cookie_and_failed_login():
    access = MobileAccess(8002, hashlib.sha256(TOKEN.encode()).digest())
    with client(access) as browser:
        assert 'Токен доступа' in browser.get('/').text
        assert browser.get('/api/library').status_code == 401
        assert browser.post('/auth/token', data={'token': 'wrong'}).status_code == 401
        response = browser.post('/auth/token', data={'token': TOKEN}, follow_redirects=False)
        assert response.status_code == 303
        cookie = response.headers['set-cookie']
        assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie
        assert TOKEN not in cookie
        assert browser.get('/api/library').json() == {'private': True}


def test_existing_listener_stays_unchanged_but_host_header_cannot_bypass_auth():
    access = MobileAccess(8002, hashlib.sha256(TOKEN.encode()).digest())
    with client(access) as browser:
        assert browser.get('/api/library', headers={'host': 'testserver:8000'}).status_code == 401
        assert browser.get('https://testserver:8000/api/library').status_code == 200
        assert browser.get('http://testserver:8002/').status_code == 426
        assert browser.get('/api/library', headers={'authorization': 'Bearer '+TOKEN}).status_code == 200


def test_login_rejects_cross_site_and_oversized_input():
    access = MobileAccess(8002, hashlib.sha256(TOKEN.encode()).digest())
    with client(access) as browser:
        assert browser.post('/auth/token', data={'token': TOKEN}, headers={'origin': 'https://attacker.example'}).status_code == 403
        assert browser.post('/auth/token', data={'token': TOKEN}, headers={'sec-fetch-site': 'cross-site'}).status_code == 403
        assert browser.post('/auth/token', content='token='+'x'*3000).status_code == 413
        assert browser.post('/auth/token', data={'token': 'токен'}).status_code == 401


def test_sandbox_read_links_are_scoped_expiring_and_do_not_authorize_api_or_writes():
    access = MobileAccess(8002, hashlib.sha256(TOKEN.encode()).digest())
    book, other = 'a'*32, 'b'*32
    capability = access.book_access(book)
    path = f'/book/{book}/__grim_access_{capability}__/chapter.html'
    with client(access) as browser:
        assert browser.get(path).status_code == 200
        assert browser.get(path.replace(book, other)).status_code == 401
        assert browser.get(path.replace(capability, capability[:-1]+'z')).status_code == 401
        assert browser.post(path).status_code == 401
        assert browser.get('/api/library?access='+capability).status_code == 401
        with patch('server.mobile_access.time.time', return_value=time.time()+2*86400):
            assert browser.get(path).status_code == 401
        assert browser.get('/vendor/fonts/KaTeX_Main-Regular.woff2').status_code == 200


def test_expired_sessions_and_rotated_access_token_revoke_access():
    access = MobileAccess(8002, hashlib.sha256(TOKEN.encode()).digest())
    session = access.session()
    assert access.valid_session(session)
    with patch('server.mobile_access.time.time', return_value=time.time()+31*86400):
        assert not access.valid_session(session)
    assert not MobileAccess(8002, hashlib.sha256(b'new token').digest()).valid_session(session)
