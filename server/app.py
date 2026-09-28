"""Grim's local book viewer, external reader context and optional local agent."""
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent.parent


from server.library import Library, library_directory, manifest, page_map, safe_file
from server.notes import NOTES_FILE, NotesDocument, read_notes, write_notes


class ReaderUpdate(BaseModel):
    reader_id: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    sequence: int = Field(ge=0)


class ReadingContext(ReaderUpdate):
    book_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    page_id: str | None = Field(default=None, max_length=200)
    visible_text: str = Field(default='', max_length=24000)
    selection: str = Field(default='', max_length=12000)
    anchor: str = Field(default='', max_length=300)
    scroll_y: float = Field(default=0, ge=0, le=10000000)
    anchor_offset: float = Field(default=0, ge=-10000000, le=10000000)


class NewBook(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class AddBook(BaseModel):
    root: str = Field(min_length=1, max_length=4096)


def create_app(book_root: Path = None, library_dir: Path = None, *, agent_completion=None):
    contexts = {}
    reader_sequences = {}
    writer_token = secrets.token_urlsafe(32)
    states = {}
    library = None
    allowed_hosts = {'127.0.0.1', 'localhost', 'testserver'}
    allowed_hosts.update(host.strip().lower() for host in os.environ.get('GRIM_ALLOWED_HOSTS', '').split(',') if host.strip())

    def bridge_version():
        return str((BASE / 'server' / 'bridge.js').stat().st_mtime_ns)

    def inline_bridge():
        source = (BASE / 'server' / 'bridge.js').read_text(encoding='utf-8')
        return '<script>' + re.sub(r'</script', r'<\\/script', source, flags=re.IGNORECASE) + '</script>'

    def scan(root):
        result = {}
        for p in root.rglob('*'):
            try:
                relative = p.relative_to(root).as_posix()
                if relative in (NOTES_FILE, NOTES_FILE + '.tmp'):
                    continue
                if p.is_file() and p.resolve().is_relative_to(root):
                    st = p.stat()
                    result[relative] = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
        return result

    def state_for(book_id):
        if book_id not in states:
            states[book_id] = {'revision': 0, 'changed': [], 'signature': scan(library.root(book_id))}
        return states[book_id]

    async def watch():
        while True:
            for book_id in list(library.entries):
                state = state_for(book_id)
                signature = await asyncio.to_thread(scan, library.root(book_id))
                previous = state['signature']
                if signature != previous:
                    state['changed'] = sorted(k for k in signature.keys() | previous.keys() if signature.get(k) != previous.get(k))
                    state['signature'] = signature
                    state['revision'] += 1
            await asyncio.sleep(.45)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal library
        roots = [book_root.resolve()] if book_root else [BASE / 'demo']
        if not book_root and os.environ.get('GRIM_BOOK'):
            roots.append(Path(os.environ['GRIM_BOOK']).resolve())
        library = Library(library_dir or library_directory(), roots)
        app.state.library = library
        from .agent import AgentService
        def agent_context(reader_id, book_id):
            import copy
            context = contexts.get(reader_id)
            return copy.deepcopy(context) if context and context['book']['id'] == book_id else None
        app.state.agent = AgentService(library, agent_context, agent_completion)
        for book_id in library.entries:
            state_for(book_id)
        task = asyncio.create_task(watch())
        try:
            yield
        finally:
            await app.state.agent.shutdown()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title='Grim library and reading context', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def require_viewer(request):
        if not secrets.compare_digest(request.headers.get('x-grim-viewer', ''), writer_token):
            raise HTTPException(403, 'Viewer token required')

    from .agent import agent_router
    app.include_router(agent_router(require_viewer))

    def accept_update(payload):
        # A late request from the previously opened book cannot replace newer context.
        if payload.sequence <= reader_sequences.get(payload.reader_id, -1):
            return False
        reader_sequences[payload.reader_id] = payload.sequence
        return True

    @app.middleware('http')
    async def boundary(request: Request, call_next):
        # Host check defeats browser DNS rebinding. No cross-origin API access,
        # including the opaque (Origin: null) book sandbox. CLI requests work.
        host = request.url.hostname
        if host is None or host.lower() not in allowed_hosts:
            return JSONResponse({'detail': 'Local host required'}, status_code=403)
        if request.url.path.startswith('/api/'):
            origin = request.headers.get('origin')
            if (origin and origin != f'{request.url.scheme}://{request.headers.get("host")}') or request.headers.get('sec-fetch-site') in ('cross-site', 'same-site'):
                return JSONResponse({'detail': 'Same-origin viewer or local agent required'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if request.url.path.startswith(('/book/', '/vendor/')):
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Content-Security-Policy'] = "sandbox allow-scripts allow-downloads; default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'none'; frame-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'"
        elif request.url.path == '/':
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    @app.get('/api/library')
    async def get_library():
        library.discover()
        return {'books': [library.describe(k) for k in library.entries], 'writer_token': writer_token,
                'new_books_root': str(library.directory / 'books')}

    @app.post('/api/library/create')
    async def create_book(payload: NewBook, request: Request):
        require_viewer(request)
        try:
            result = library.create(payload.title)
            state_for(result['id'])
            return result
        except OSError as exc:
            raise HTTPException(422, f'Не удалось создать книгу: {exc}') from exc

    @app.post('/api/library/add')
    async def add_book(payload: AddBook, request: Request):
        require_viewer(request)
        try:
            result = library.register(Path(payload.root))
            state_for(result['id'])
            return result
        except OSError as exc:
            raise HTTPException(422, f'Не удалось подключить папку: {exc}') from exc

    @app.get('/api/books/{book_id}')
    async def get_book(book_id: str):
        root = library.root(book_id)
        return {**manifest(root), 'id': book_id, 'root': str(root),
                'writer_token': writer_token, 'revision': state_for(book_id)['revision'],
                'bridge_version': bridge_version()}

    @app.get('/api/books/{book_id}/notes')
    async def get_notes(book_id: str):
        return read_notes(library.root(book_id))

    @app.put('/api/books/{book_id}/notes')
    async def put_notes(book_id: str, payload: NotesDocument, request: Request):
        require_viewer(request)
        write_notes(library.root(book_id), payload)
        return payload

    @app.get('/api/context')
    async def get_context(reader_id: str = None, book_id: str = None):
        if book_id:
            library.root(book_id)
        cutoff = time.time() - 1800
        for key in list(contexts):
            if contexts[key]['last_seen'] < cutoff:
                del contexts[key]
        candidates = {k: c for k, c in contexts.items() if not book_id or c['book']['id'] == book_id}
        context = candidates.get(reader_id) if reader_id else max(candidates.values(), key=lambda c: c['last_seen'], default=None)
        return {'context': context, 'readers': [{'reader_id': k, 'book_id': c['book']['id'], 'updated_at': c['updated_at']} for k, c in candidates.items()]}

    @app.post('/api/viewer/context', include_in_schema=False)
    async def update_context(payload: ReadingContext, request: Request):
        require_viewer(request)
        root = library.root(payload.book_id)
        data = manifest(root)
        pages = page_map(data)
        page = pages.get(payload.page_id)
        if payload.page_id is not None and not page:
            raise HTTPException(404, 'Unknown page in this book')
        if payload.page_id is None and pages:
            raise HTTPException(422, 'A non-empty book requires a page')
        if not accept_update(payload):
            return {'ok': True, 'ignored': True}
        if payload.reader_id not in contexts and len(contexts) >= 100:
            del contexts[min(contexts, key=lambda k: contexts[k]['last_seen'])]
        contexts[payload.reader_id] = {
            **payload.model_dump(exclude={'page_id', 'book_id'}),
            'book': {'id': payload.book_id, 'title': data['title'], 'root': str(root)},
            'page': page, 'updated_at': datetime.now(timezone.utc).isoformat(),
            'last_seen': time.time(), 'revision': state_for(payload.book_id)['revision']}
        return {'ok': True}

    @app.post('/api/viewer/idle', include_in_schema=False)
    async def idle(payload: ReaderUpdate, request: Request):
        require_viewer(request)
        if accept_update(payload):
            contexts.pop(payload.reader_id, None)
        return {'ok': True}

    @app.get('/api/books/{book_id}/events')
    async def events(book_id: str, request: Request):
        library.root(book_id)
        state = state_for(book_id)
        async def generate():
            last = -1
            while not await request.is_disconnected():
                if last != state['revision']:
                    last = state['revision']
                    yield f'data: {json.dumps({"book_id": book_id, "revision": last, "changed": state["changed"]})}\n\n'
                else:
                    yield ': keepalive\n\n'
                await asyncio.sleep(.5)
        return StreamingResponse(generate(), media_type='text/event-stream', headers={'X-Accel-Buffering':'no'})

    @app.get('/bridge.js')
    async def bridge():
        return FileResponse(BASE / 'server' / 'bridge.js', media_type='text/javascript')

    @app.get('/bridge-{version}.js')
    async def versioned_bridge(version: str):
        bridge_file = BASE / 'server' / 'bridge.js'
        if version != bridge_version():
            raise HTTPException(status_code=404, detail='Unknown bridge version')
        return FileResponse(
            bridge_file,
            media_type='text/javascript',
            headers={'Cache-Control': 'public, max-age=31536000, immutable'},
        )

    @app.get('/vendor/{path:path}')
    async def vendor(path: str):
        return FileResponse(safe_file(BASE / 'node_modules' / 'katex' / 'dist', path))

    @app.get('/book/{book_id}/{path:path}')
    async def book_file(book_id: str, path: str, download: bool = False):
        # The live iframe uses a synthetic filename so reverse proxies that
        # ignore query parameters cannot keep serving an old injected bridge.
        versioned_name = re.match(r'^(.*?/)?__grim_v_[a-zA-Z0-9]+_\d+__([^/]+)$', path)
        if versioned_name:
            path = (versioned_name.group(1) or '') + versioned_name.group(2)
        if path == NOTES_FILE:
            raise HTTPException(404, 'Файл не найден в папке книги')
        file = safe_file(library.root(book_id), path)
        if download:
            return FileResponse(file, filename=file.name, media_type='application/octet-stream')
        if file.suffix.lower() in ('.html', '.htm'):
            source = file.read_text(encoding='utf-8')
            # Insert first so page scripts cannot accidentally prevent bridge setup.
            # Keep it inline: an authenticated reverse proxy may reject a
            # subresource request from this deliberately opaque sandbox frame.
            bridge = inline_bridge()
            if '<head>' in source:
                source = source.replace('<head>', '<head>' + bridge, 1)
            else:
                source = bridge + source
            return HTMLResponse(source)
        return FileResponse(file)

    @app.get('/')
    async def index():
        if not (BASE / 'dist' / 'index.html').exists():
            return HTMLResponse('Run npm install && npm run build first.', status_code=503)
        return FileResponse(BASE / 'dist' / 'index.html')

    @app.get('/assets/{path:path}')
    async def assets(path: str):
        return FileResponse(safe_file(BASE / 'dist' / 'assets', path))

    return app


app = create_app()
