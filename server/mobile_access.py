"""Optional token-protected listener; the original web listener stays unchanged."""
import asyncio
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import logging
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import time
from urllib.parse import parse_qs

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from server.access_tokens import AccessTokens

COOKIE = 'grim-mobile-session'
ACCESS_VALUE = r'[0-9]+\.(?:(?:legacy|[a-f0-9]{32})\.)?[a-f0-9]{64}'
CAPABILITY = re.compile(r'^__grim_access_(' + ACCESS_VALUE + r')__$')
BOOK_URL = re.compile(r'^/book(?:-source)?/([a-f0-9]{32})/(?:__grim_source__/)?__grim_access_(' + ACCESS_VALUE + r')__(?:/|$)')
LOGIN = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Grim — подключение</title><style>
body{margin:0;background:#17211d;color:#e0e9df;font:16px/1.5 system-ui,sans-serif}main{max-width:420px;margin:12vh auto;padding:24px}h1{font:36px Georgia,serif}label{display:block;margin:24px 0 8px}input,button{box-sizing:border-box;width:100%;min-height:48px;padding:12px;border-radius:6px;font:inherit}input{background:#233329;color:inherit;border:1px solid #49614d}button{margin-top:14px;border:0;background:#426b50;color:white}.error{color:#f2cf8e}p{color:#a8b8aa}</style></head><body><main><h1>Подключиться к Grim</h1><p>Введите токен доступа к вашей библиотеке.</p>ERROR<form method="post" action="/auth/token"><label for="access-token">Токен доступа</label><input id="access-token" name="token" type="password" autocomplete="off" required maxlength="512"><button>Подключиться</button></form></main></body></html>'''


@dataclass
class MobileAccess:
    port: int
    secret: bytes
    host: str = '127.0.0.1'
    proxies: str = '127.0.0.1'
    origins: tuple = ()
    tls_cert: str | None = None
    tls_key: str | None = None
    tokens: AccessTokens | None = None

    @classmethod
    def from_env(cls):
        port = os.environ.get('GRIM_MOBILE_PORT')
        if not port:
            return None
        port = int(port)
        if not 1 <= port <= 65535 or port == int(os.environ.get('GRIM_PORT', '8000')):
            raise ValueError('GRIM_MOBILE_PORT must be a separate valid port')
        path = Path(os.environ['GRIM_ACCESS_TOKEN_FILE'])
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('GRIM_ACCESS_TOKEN_FILE must be owned by this user and mode 0600')
        token = path.read_bytes().strip()
        if len(token) < 32 or len(token) > 512 or any(chr(c).isspace() for c in token):
            raise ValueError('Access token must contain 32–512 non-whitespace bytes')
        cert, key = os.environ.get('GRIM_MOBILE_TLS_CERT'), os.environ.get('GRIM_MOBILE_TLS_KEY')
        if bool(cert) != bool(key):
            raise ValueError('GRIM_MOBILE_TLS_CERT and GRIM_MOBILE_TLS_KEY must be configured together')
        if cert:
            if not Path(cert).is_file():
                raise ValueError('GRIM_MOBILE_TLS_CERT must be a certificate file')
            key_info = Path(key).stat()
            if not stat.S_ISREG(key_info.st_mode) or key_info.st_uid != os.getuid() or key_info.st_mode & 0o077:
                raise ValueError('GRIM_MOBILE_TLS_KEY must be owned by this user and mode 0600')
        registry = Path(os.environ.get('GRIM_ACCESS_TOKENS_FILE', str(path.with_name('access-tokens.json'))))
        return cls(port, hashlib.sha256(token).digest(), os.environ.get('GRIM_MOBILE_HOST', '127.0.0.1'), os.environ.get('GRIM_MOBILE_TRUSTED_PROXIES', '127.0.0.1'), tuple(value.strip().rstrip('/') for value in os.environ.get('GRIM_ALLOWED_ORIGINS', '').split(',') if value.strip()), cert, key, AccessTokens(registry, hashlib.sha256(token).hexdigest()))

    def protected(self, scope):
        return not scope.get('server') or scope['server'][1] == self.port

    def sign(self, purpose, value):
        key = hmac.new(self.tokens.signing_key, self.secret, hashlib.sha256).digest() if self.tokens else self.secret
        return hmac.new(key, (purpose + '\n' + value).encode(), hashlib.sha256).hexdigest()

    def legacy_signature(self, purpose, value):
        return hmac.new(self.secret, (purpose + '\n' + value).encode(), hashlib.sha256).hexdigest()

    def authenticate_token(self, value):
        if self.tokens:
            return self.tokens.authenticate(value)
        return 'legacy' if hmac.compare_digest(hashlib.sha256(value.encode()).digest(), self.secret) else None

    def active_token(self, token_id):
        return self.tokens.active(token_id) if self.tokens else token_id == 'legacy'

    def session(self, token_id='legacy'):
        value = f'{int(time.time()) + 30*86400}.{secrets.token_hex(16)}'
        if self.tokens:
            value = token_id + '.' + value
        return value + '.' + self.sign('session', value)

    def session_identity(self, value):
        try:
            data, signature = value.rsplit('.', 1)
            parts = data.split('.')
            # Three-part cookies issued before the token panel belong to legacy.
            token_id, expires = (parts[0], parts[1]) if len(parts) == 3 else ('legacy', parts[0])
            valid = hmac.compare_digest(signature, self.sign('session', data))
            if token_id == 'legacy':
                valid = valid or hmac.compare_digest(signature, self.legacy_signature('session', data))
            if int(expires) > time.time() and self.active_token(token_id) and valid:
                return token_id
        except (ValueError, TypeError, AttributeError):
            pass
        return None

    def valid_session(self, value):
        return self.session_identity(value) is not None

    def book_access(self, book_id, token_id='legacy'):
        # Read-only, book-scoped URLs let opaque sandbox media/font requests
        # work without third-party cookies or credentialed CORS from Origin:null.
        expires = str(int(time.time()) + 86400)
        if self.tokens:
            return expires + '.' + token_id + '.' + self.sign('book:' + book_id + ':' + token_id, expires)
        return expires + '.' + self.sign('book:' + book_id, expires)

    def valid_book_access(self, book_id, value):
        try:
            parts = value.split('.')
            if len(parts) == 3:
                expires, token_id, signature = parts
                purpose = 'book:' + book_id + ':' + token_id
            else:
                expires, signature = parts
                token_id, purpose = 'legacy', 'book:' + book_id
            valid = hmac.compare_digest(signature, self.sign(purpose, expires))
            if token_id == 'legacy':
                valid = valid or hmac.compare_digest(signature, self.legacy_signature(purpose, expires))
            return self.active_token(token_id) and int(expires) > time.time() and valid
        except (ValueError, AttributeError, TypeError):
            return False


class MobileAccessMiddleware:
    def __init__(self, app, access):
        self.app, self.access = app, access

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not self.access.protected(scope):
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        path = request.url.path
        # Direct TLS is preferred. In proxy mode Uvicorn accepts forwarded
        # headers only from the configured trusted peer.
        if request.url.scheme != 'https':
            return await JSONResponse({'detail': 'HTTPS required'}, 426)(scope, receive, send)
        response = None
        if path == '/auth/token' and request.method == 'POST':
            origin = request.headers.get('origin')
            if (origin and origin.rstrip('/') not in (str(request.base_url).rstrip('/'), *self.access.origins)) or request.headers.get('sec-fetch-site') in ('cross-site', 'same-site'):
                logging.getLogger(__name__).warning('Mobile login origin rejected: origin=%r base=%r fetch_site=%r',
                    origin, str(request.base_url), request.headers.get('sec-fetch-site'))
                response = JSONResponse({'detail': 'Same-origin login required'}, 403)
            else:
                data = bytearray()
                async for chunk in request.stream():
                    data.extend(chunk)
                    if len(data) > 2048:
                        response = JSONResponse({'detail': 'Request too large'}, 413); break
                if response is None:
                    token = parse_qs(data.decode('utf-8', errors='replace')).get('token', [''])[0]
                    token_id = self.access.authenticate_token(token)
                    if token_id:
                        response = RedirectResponse('/', 303)
                        # The app's bundled launcher navigates here from another
                        # origin. Lax includes the session on that top-level GET;
                        # Strict would show login again despite a persisted cookie.
                        response.set_cookie(COOKIE, self.access.session(token_id), max_age=30*86400, secure=True, httponly=True, samesite='lax')
                        if self.access.tokens:
                            self.access.tokens.touch(token_id)
                    else:
                        response = HTMLResponse(LOGIN.replace('ERROR', '<p class="error">Токен не принят. Проверьте его и попробуйте снова.</p>'), 401)
        else:
            bearer = request.headers.get('authorization', '')
            token_id = self.access.session_identity(request.cookies.get(COOKIE, ''))
            if token_id is None and bearer.startswith('Bearer '):
                token_id = self.access.authenticate_token(bearer[7:])
            book = BOOK_URL.match(path)
            scoped_read = request.method in ('GET', 'HEAD') and book and self.access.valid_book_access(book[1], book[2])
            public_asset = request.method in ('GET', 'HEAD') and path.startswith(('/vendor/', '/assets/'))
            if token_id or scoped_read or public_asset:
                if token_id:
                    scope['grim.access_token_id'] = token_id
                    if self.access.tokens:
                        self.access.tokens.touch(token_id)
                return await self.app(scope, receive, send)
            response = HTMLResponse(LOGIN.replace('ERROR', '')) if path == '/' and request.method == 'GET' else JSONResponse({'detail': 'Access token required'}, 401)
        # HTML form navigation needs a same-origin referrer policy so Chromium
        # retains its Origin instead of serializing it as null. Book URLs and
        # normal reader responses continue to use no-referrer.
        response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'same-origin' if isinstance(response, HTMLResponse) else 'no-referrer', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})
        return await response(scope, receive, send)


@asynccontextmanager
async def mobile_listener(app, access):
    if access is None:
        yield; return
    import uvicorn
    class SecondaryServer(uvicorn.Server):
        @contextmanager
        def capture_signals(self):
            yield
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((access.host, access.port)); sock.listen(128); sock.setblocking(False)
    server = SecondaryServer(uvicorn.Config(app, host=access.host, port=access.port, lifespan='off', access_log=False,
        proxy_headers=not bool(access.tls_cert), forwarded_allow_ips=access.proxies,
        ssl_certfile=access.tls_cert, ssl_keyfile=access.tls_key, timeout_graceful_shutdown=2))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started:
            if task.done():
                await task
                raise RuntimeError('Mobile listener failed to start')
            await asyncio.sleep(.01)
        yield
    finally:
        server.should_exit = True
        await task
        sock.close()
