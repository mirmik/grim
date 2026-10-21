import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import socket
import threading

import pytest
from fastapi.testclient import TestClient

from server.agent import AgentService
from server.app import create_app
from server.web_tools import WebTools, download_public, extract_document, public_url
from test_agent import answer, call, turn, wait_job
from test_server import entry, headers, make_book


@pytest.mark.parametrize('url', [
    'file:///etc/passwd', 'ftp://example.org/file', 'http://user:secret@example.org/',
    'http://localhost/', 'http://LOCALHOST./', 'http://host.local/', 'http://127.0.0.1/',
    'http://10.1.2.3/', 'http://192.168.0.61/', 'http://169.254.169.254/',
    'http://[::1]/', 'http://[::ffff:127.0.0.1]/', 'http://[fe80::1%25eth0]/',
    'http://[64:ff9b::7f00:1]/', 'http://[::127.0.0.1]/', 'http://[::ffff:0:127.0.0.1]/',
    'http://224.0.0.1/', 'https://example.org/\r\nHeader:value',
    'https://example.org:99999/',
])
def test_private_and_non_http_urls_are_rejected(url):
    with pytest.raises(ValueError):
        public_url(url)


@pytest.fixture
def public_server(monkeypatch):
    seen, resolutions, connections = [], [], []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, dict(self.headers)))
            status, headers, data = 200, {'Content-Type':'text/html; charset=utf-8'}, b'<title>Article</title><p>Public article</p>'
            if self.path == '/redirect':
                status, headers = 302, {'Location':'/article'}
            elif self.path == '/private':
                status, headers = 302, {'Location':'http://127.0.0.1/private'}
            elif self.path == '/rebind':
                status, headers = 302, {'Location':'http://rebind.test/secret'}
            elif self.path == '/loop':
                status, headers = 302, {'Location':'/loop'}
            elif self.path == '/missing':
                status = 404
            elif self.path == '/gzip':
                data = gzip.compress(data)
                headers['Content-Encoding'] = 'gzip'
            elif self.path == '/bomb':
                data = gzip.compress(b'x' * 1001)
                headers['Content-Encoding'] = 'gzip'
            elif self.path == '/big':
                data = b'x' * 1001
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            if self.path != '/stream-big':
                self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            if self.path == '/stream-big':
                data = b'x' * 1001
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original_dns = socket.getaddrinfo
    def resolve(host, port, *args, **kwargs):
        if host in ('public.test', 'rebind.test'):
            resolutions.append(host)
            ip = '93.184.216.34' if host == 'public.test' else '127.0.0.1'
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port))]
        return original_dns(host, port, *args, **kwargs)
    def connect(addresses, timeout):
        connections.append(addresses)
        return socket.create_connection(('127.0.0.1', server.server_port), timeout=timeout)
    monkeypatch.setattr('server.web_tools.socket.getaddrinfo', resolve)
    monkeypatch.setattr('server.web_tools._connect', connect)
    try:
        yield seen, resolutions, connections
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_redirects_dns_pinning_and_no_credentials_cookies_or_proxy(public_server, monkeypatch):
    seen, resolutions, connections = public_server
    monkeypatch.setenv('HTTP_PROXY', 'http://localhost:1')
    monkeypatch.setenv('HTTPS_PROXY', 'http://localhost:1')
    result = download_public('http://public.test/redirect')
    assert result['url'] == 'http://public.test/article' and b'Public article' in result['data']
    assert resolutions == ['public.test', 'public.test']
    assert all(item[0][4][0] == '93.184.216.34' for item in connections)
    assert [path for path, _ in seen] == ['/redirect', '/article']
    for _, request_headers in seen:
        assert request_headers['Host'] == 'public.test'
        assert not any(name in request_headers for name in ['Authorization','Cookie','X-Grim-Viewer','Proxy-Authorization'])
    before = len(seen)
    for path in ['/private', '/rebind']:
        with pytest.raises(ValueError):
            download_public('http://public.test' + path)
    assert [path for path, _ in seen[before:]] == ['/private', '/rebind']


def test_mixed_dns_answers_are_rejected_before_connection(monkeypatch):
    addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 80)) for ip in ['93.184.216.34','10.0.0.1']]
    monkeypatch.setattr('server.web_tools.socket.getaddrinfo', lambda *args, **kwargs: addresses)
    monkeypatch.setattr('server.web_tools._connect', lambda *args: pytest.fail('Private DNS answer must not connect'))
    with pytest.raises(ValueError, match='непубличную'):
        download_public('http://public.test/')


def test_redirect_limit_status_and_wire_decompression_limits(public_server, monkeypatch):
    assert download_public('http://public.test/gzip')['data'].startswith(b'<title>')
    with pytest.raises(ValueError, match='перенаправлений'):
        download_public('http://public.test/loop')
    with pytest.raises(ValueError, match='HTTP 404'):
        download_public('http://public.test/missing')
    monkeypatch.setattr('server.web_tools.MAX_DOWNLOAD', 1000)
    for path in ['/big', '/stream-big', '/bomb']:
        with pytest.raises(ValueError, match='слишком велик'):
            download_public('http://public.test' + path)


def document(data, mime='text/html; charset=utf-8', url='https://example.org/article'):
    return {'url':url, 'data':data.encode() if isinstance(data, str) else data, 'content_type':mime}


def test_html_extraction_links_unicode_and_removal_of_executable_hidden_text():
    html = '''<html><head><title>Заголовок</title><base href="/manual/"></head><body>
        <script>steal_tokens()</script><style>secret_css</style><p hidden>hidden data</p>
        <article><h1>Глава</h1><p>Перевод термина зависит от контекста.</p>
        <p>Полезное пояснение для читателя.</p><a href="chapter2">Следующая глава</a>
        <a href="javascript:alert(1)">bad</a><a href="http://127.0.0.1/">private</a></article></body></html>'''
    result = extract_document(document(html))
    assert result['title'] == 'Заголовок' and 'Перевод' in result['text']
    assert all(text not in result['text'] for text in ['steal_tokens','secret_css','hidden data'])
    assert result['links'] == [{'title':'Следующая глава','url':'https://example.org/manual/chapter2'}]
    encoded = '<title>Книга</title><p>Русский текст</p>'.encode('cp1251')
    assert 'Русский текст' in extract_document(document(encoded, 'text/html; charset=windows-1251'))['text']
    assert extract_document(document('строка', 'text/plain; charset=utf-8'))['text'] == 'строка'
    with pytest.raises(ValueError, match='Неподдерживаемый'):
        extract_document(document(b'PNG', 'image/png'))


def test_text_pdf_and_missing_text_layer():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject({NameObject('/Type'):NameObject('/Font'), NameObject('/Subtype'):NameObject('/Type1'), NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 10 100 Td (Public paper text) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    result = extract_document(document(output.getvalue(), 'application/pdf'))
    assert 'Public paper text' in result['text'] and '[Страница 1]' in result['text']
    blank = PdfWriter();blank.add_blank_page(width=200, height=200)
    output = io.BytesIO();blank.write(output)
    with pytest.raises(ValueError, match='OCR'):
        extract_document(document(output.getvalue(), 'application/pdf'))


def test_stable_snapshot_continuation_find_and_expiration(monkeypatch):
    calls = []
    text = 'начало ' * 400 + 'нужный термин' + ' продолжение' * 400
    def download(url):
        calls.append(url)
        return document(text, 'text/plain', url)
    web = WebTools(downloader=download)
    first = web.fetch({'url':'https://example.org/article','max_chars':1000})
    second = web.fetch({'url':first['url'],'document_id':first['document_id'],'start':first['next_start'],'max_chars':1000})
    assert first['text'] + second['text'] == text[:2000]
    assert calls == ['https://example.org/article']
    found = web.fetch({'url':first['url'],'document_id':first['document_id'],'query':'НУЖНЫЙ ТЕРМИН','max_chars':1000})
    assert 'нужный термин' in found['text'] and found['matches'] == [2800]
    with pytest.raises(ValueError, match='другому URL'):
        web.fetch({'url':'https://example.org/other','document_id':first['document_id']})
    with pytest.raises(ValueError, match='продолжения'):
        web.fetch({'url':first['url'],'start':1000})
    monkeypatch.setattr('server.web_tools.CACHE_SECONDS', -1)
    with pytest.raises(ValueError, match='устарела'):
        web.fetch({'url':first['url'],'document_id':first['document_id']})


def test_search_parameters_sources_limits_and_error_handling():
    observed = []
    def search(**kwargs):
        observed.append(kwargs)
        return [{'title':'Article','href':'https://example.org/','body':'Snippet'},
                {'title':'Duplicate','href':'https://example.org/','body':'duplicate'},
                {'href':'http://127.0.0.1/private','body':'bad'}, {'href':'javascript:alert(1)'}]
    web = WebTools(search_provider=search)
    result = web.search({'query':' site:example.org перевод ', 'region':'ru-ru','timelimit':'m','page':2,'limit':3})
    assert observed == [{'query':'site:example.org перевод','max_results':3,'page':2,'region':'ru-ru','timelimit':'m'}]
    assert result['results'] == [{'title':'Article','url':'https://example.org/','snippet':'Snippet'}]
    for args in [{'query':''},{'query':'q','limit':100},{'query':'q','page':False},{'query':'q','timelimit':'bad'}]:
        with pytest.raises(ValueError):
            web.search(args)
    def unavailable(**kwargs):
        raise RuntimeError('sensitive provider internals')
    with pytest.raises(ValueError, match='Поисковый сервис') as error:
        WebTools(search_provider=unavailable).search({'query':'q'})
    assert 'sensitive' not in str(error.value)


@pytest.mark.skipif(not AgentService.available(), reason='Optional Nemor unavailable')
def test_real_agent_loop_search_read_continue_and_cite_without_book_edits(tmp_path):
    text = 'Read source data. ' * 200
    web = WebTools(search_provider=lambda **_: [{'title':'Primary source','href':'https://example.org/article','body':'Snippet'}],
                   downloader=lambda url: document(text, 'text/plain', url))
    def complete(*, messages, **kwargs):
        if messages[-1]['role'] == 'user':
            assert 'fetch_webpage' in messages[0]['content']
            return call('web_search', {'query':'primary source'})
        name = messages[-2]['tool_calls'][0]['function']['name']
        result = json.loads(messages[-1]['content'])
        assert 'error' not in result, result
        if name == 'web_search':
            return call('fetch_webpage', {'url':result['results'][0]['url'],'max_chars':1000})
        if result['start'] == 0:
            return call('fetch_webpage', {'url':result['url'],'document_id':result['document_id'],'start':result['next_start'],'max_chars':1000})
        assert result['start'] == 1000 and result['source'] == 'web'
        return answer('Прочитано: [Primary source](https://example.org/article).')
    root = make_book(tmp_path / 'book')
    before = (root / 'one.html').read_bytes()
    with TestClient(create_app(root, tmp_path / 'library', agent_completion=complete, agent_web=web)) as client:
        book_id = entry(client)['id']
        payload = turn('Найди источник и прочитай')
        client.post(f'/api/books/{book_id}/agent/jobs', headers=headers(client), json=payload).raise_for_status()
        job = wait_job(client, book_id, payload['job_id'])
        assert job['status'] == 'completed', job
        assert [event['name'] for event in job['events']] == ['web_search','fetch_webpage','fetch_webpage']
        assert 'https://example.org/article' in job['response']
        assert (root / 'one.html').read_bytes() == before
        actual = client.app.state.agent.store.model_request(job['chat_id'])['request']
        assert {'web_search','fetch_webpage'} <= {tool['function']['name'] for tool in actual['tools']}
        assert json.loads(actual['messages'][-1]['content'])['start'] == 1000
