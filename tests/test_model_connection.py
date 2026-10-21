"""Real TLS: a rejected certificate must never receive HTTP or a bearer token."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import ssl
import subprocess
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from server.agent import Settings, completion_adapter
from server.app import create_app
from server.model_connection import connection_error
from test_server import make_book, headers

TOKEN = 'private-disposable-model-token'


@pytest.fixture
def tls_model(tmp_path):
    cert, key = tmp_path / 'cert.pem', tmp_path / 'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-subj', '/CN=model.test', '-addext', 'subjectAltName=DNS:model.test',
                    '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
    fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get('Authorization'), None))
            self.reply({'data': [{'id': 'tls-model'}]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path, self.headers.get('Authorization'), body))
            self.reply({'choices': [{'message': {'role': 'assistant', 'content': 'TLS works'}}]})

        def reply(self, payload):
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {'endpoint': f'https://127.0.0.1:{server.server_port}/v1', 'tls_fingerprint': fingerprint,
               'requests': requests, 'cert': cert, 'context': context}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def configure(client, config):
    payload = {key: value for key, value in config.items() if key in ('endpoint', 'tls_fingerprint')}
    payload.update(model='tls-model', api_token=TOKEN)
    response = client.put('/api/agent/settings', headers=headers(client), json=payload)
    response.raise_for_status()
    assert TOKEN not in response.text
    return response.json()


def test_pinned_probe_completion_and_settings_survive_restart(tmp_path, tls_model, monkeypatch):
    # A proxy from the process environment must never replace the pin transport.
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setenv('NO_PROXY', '')
    root, library = make_book(tmp_path / 'book'), tmp_path / 'library'
    formatted = ':'.join(tls_model['tls_fingerprint'][i:i+2].upper() for i in range(0, 64, 2))
    with TestClient(create_app(root, library)) as client:
        saved = configure(client, {**tls_model, 'tls_fingerprint': 'SHA256 Fingerprint=' + formatted})
        assert saved['tls_fingerprint'] == tls_model['tls_fingerprint']
        response = client.post('/api/agent/probe', headers=headers(client))
        assert response.status_code == 200, response.text
        assert response.json() == {'models': ['tls-model']}
        config = client.app.state.agent.config()
        result = completion_adapter(config)(messages=[{'role': 'user', 'content': 'Hello'}], tools=[], config={})
        assert result['choices'][0]['message']['content'] == 'TLS works'
    assert [row[0] for row in tls_model['requests']] == ['/v1/models', '/v1/chat/completions']
    assert all(row[1] == 'Bearer ' + TOKEN for row in tls_model['requests'])
    with TestClient(create_app(root, library)) as client:
        assert client.get('/api/agent/settings').json()['tls_fingerprint'] == tls_model['tls_fingerprint']
        assert client.app.state.agent.config()['api_token'] == TOKEN


def test_wrong_or_rotated_pin_never_sends_http_headers(tmp_path, tls_model):
    root = make_book(tmp_path / 'book')
    wrong = '0' * 64 if tls_model['tls_fingerprint'] != '0' * 64 else '1' * 64
    with TestClient(create_app(root, tmp_path / 'library')) as client:
        configure(client, {**tls_model, 'tls_fingerprint': wrong})
        response = client.post('/api/agent/probe', headers=headers(client))
        assert response.status_code == 502 and 'fingerprint' in response.json()['detail']
        with pytest.raises(ValueError, match='fingerprint') as error:
            completion_adapter(client.app.state.agent.config())(messages=[], tools=[], config={})
        assert TOKEN not in str(error.value) and TOKEN not in response.text
        assert tls_model['requests'] == []


def test_no_pin_retains_ca_and_hostname_verification(tmp_path, tls_model, monkeypatch):
    root = make_book(tmp_path / 'book')
    with TestClient(create_app(root, tmp_path / 'library')) as client:
        configure(client, {**tls_model, 'tls_fingerprint': ''})
        response = client.post('/api/agent/probe', headers=headers(client))
        assert response.status_code == 502 and 'доверия' in response.json()['detail']
        monkeypatch.setenv('SSL_CERT_FILE', str(tls_model['cert']))
        response = client.post('/api/agent/probe', headers=headers(client))
        assert response.status_code == 502 and 'имени или IP' in response.json()['detail']
        assert tls_model['requests'] == []


def test_certificate_rotation_requires_a_new_pin(tmp_path, tls_model):
    with TestClient(create_app(make_book(tmp_path / 'book'), tmp_path / 'library')) as client:
        configure(client, tls_model)
        assert client.post('/api/agent/probe', headers=headers(client)).status_code == 200
        tls_model['requests'].clear()
        cert, key = tmp_path / 'rotated-cert.pem', tmp_path / 'rotated-key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=model.test', '-keyout', str(key), '-out', str(cert)],
                       check=True, capture_output=True)
        tls_model['context'].load_cert_chain(cert, key)
        response = client.post('/api/agent/probe', headers=headers(client))
        assert response.status_code == 502 and 'fingerprint' in response.json()['detail']
        assert tls_model['requests'] == []


@pytest.mark.parametrize('value', ['x' * 64, 'aa:bb', 'a' * 63, 'a' * 65, 'SHA1:' + 'a' * 64])
def test_invalid_fingerprints(value):
    with pytest.raises(ValueError, match='64'):
        Settings(endpoint='https://model.test', tls_fingerprint=value)


def test_http_pin_validation_does_not_echo_api_token(tmp_path):
    with TestClient(create_app(make_book(tmp_path / 'book'), tmp_path / 'library')) as client:
        response = client.put('/api/agent/settings', headers=headers(client), json={
            'endpoint': 'http://model.test', 'tls_fingerprint': 'a' * 64, 'api_token': TOKEN})
        assert response.status_code == 422 and 'https://' in response.text
        assert TOKEN not in response.text


@pytest.mark.parametrize(('error', 'text'), [(httpx.ConnectTimeout('secret'), 'вовремя'),
    (httpx.ConnectError('secret'), 'DNS'), (httpx.RemoteProtocolError('secret'), 'https://')])
def test_connection_errors_are_actionable_and_redacted(error, text):
    assert text in connection_error(error)
    assert 'secret' not in connection_error(error)


@pytest.mark.parametrize(('status', 'body', 'expected'), [(401, 'secret body', 'HTTP 401'),
    (302, 'secret body', 'HTTP 302'), (200, 'secret body', 'некорректный JSON'),
    (200, '{"secret":"body"}', 'списка моделей')])
def test_probe_response_errors_keep_the_reason_and_hide_the_body(tmp_path, monkeypatch, status, body, expected):
    client_type = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(status, content=body))
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: client_type(transport=transport, **kwargs))
    with TestClient(create_app(make_book(tmp_path / 'book'), tmp_path / 'library')) as client:
        response = client.post('/api/agent/probe', headers=headers(client))
        assert response.status_code == 502 and expected in response.json()['detail']
        assert 'secret' not in response.text
