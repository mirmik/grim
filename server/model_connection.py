"""Optional SHA-256 certificate pinning on the connection carrying the request."""
import asyncio
import hashlib
import hmac
import http.client
import re
import socket
import ssl

import httpx


def normalize_fingerprint(value):
    value = re.sub(r'^sha-?256\s*(?:fingerprint\s*)?[:=]\s*', '', value.strip(), flags=re.I)
    value = re.sub(r'[\s:]', '', value).lower()
    if value and not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Fingerprint SHA-256 должен содержать 64 шестнадцатеричных знака (можно через двоеточие)')
    return value


class FingerprintMismatch(httpx.ConnectError):
    pass


class PinnedConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, fingerprint, timeout):
        # In pin mode the explicit certificate hash is the trust anchor; the
        # certificate's CA and DNS names are not used for authentication.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        super().__init__(host, port, timeout=timeout, context=context)
        self.fingerprint = bytes.fromhex(normalize_fingerprint(fingerprint))

    def connect(self):
        super().connect()
        actual = hashlib.sha256(self.sock.getpeercert(binary_form=True)).digest()
        if not hmac.compare_digest(actual, self.fingerprint):
            self.close()
            raise FingerprintMismatch('SHA-256 fingerprint сертификата не совпадает с указанным. Проверьте адрес и fingerprint.')
        # HTTPSConnection.send() can write HTTP headers/body only after this
        # method returns. A separate preflight connection would not suffice.


class PinnedTransport(httpx.BaseTransport):
    def __init__(self, fingerprint):
        self.fingerprint = normalize_fingerprint(fingerprint)
        if not self.fingerprint:
            raise ValueError('Для pinning требуется SHA-256 fingerprint')

    def handle_request(self, request):
        if request.url.scheme != 'https':
            raise httpx.UnsupportedProtocol('Fingerprint разрешён только для HTTPS', request=request)
        timeouts = request.extensions.get('timeout', {})
        connection = PinnedConnection(request.url.host, request.url.port or 443, self.fingerprint, timeouts.get('connect', 5))
        connected = False
        try:
            connection.connect()
            connected = True
            connection.sock.settimeout(timeouts.get('write', 5))
            connection.request(request.method, request.url.raw_path.decode('ascii'),
                               body=request.read(), headers=dict(request.headers))
            connection.sock.settimeout(timeouts.get('read', 5))
            response = connection.getresponse()
            return httpx.Response(response.status, headers=response.getheaders(), content=response.read(),
                                  extensions={'http_version': b'HTTP/1.1'}, request=request)
        except FingerprintMismatch:
            raise
        except (socket.timeout, TimeoutError) as error:
            kind = httpx.ReadTimeout if connected else httpx.ConnectTimeout
            raise kind('Сервер модели не ответил вовремя', request=request) from error
        except (ssl.SSLError, OSError) as error:
            raise httpx.ConnectError('Не удалось установить TLS-соединение', request=request) from error
        except http.client.HTTPException as error:
            raise httpx.RemoteProtocolError('Сервер не вернул корректный HTTP-ответ', request=request) from error
        finally:
            connection.close()


class AsyncPinnedTransport(httpx.AsyncBaseTransport):
    def __init__(self, fingerprint):
        self.transport = PinnedTransport(fingerprint)

    async def handle_async_request(self, request):
        await request.aread()
        return await asyncio.to_thread(self.transport.handle_request, request)


def model_client_options(settings, *, asynchronous=False):
    fingerprint = settings.get('tls_fingerprint', '')
    if not fingerprint:
        return {}  # HTTPX retains normal CA/hostname and environment handling.
    transport = AsyncPinnedTransport if asynchronous else PinnedTransport
    # Environment proxy mounts must not bypass the certificate-pinned transport.
    return {'transport': transport(fingerprint), 'trust_env': False}


def connection_error(error):
    """Useful diagnostics without echoing URLs, credentials or response bodies."""
    if isinstance(error, FingerprintMismatch):
        return str(error)
    cause, seen = error, set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if isinstance(cause, ssl.SSLCertVerificationError):
            if cause.verify_code in (62, 64):
                return 'Сертификат не выдан для указанного имени или IP. Проверьте адрес либо укажите доверенный SHA-256 fingerprint.'
            return 'TLS-сертификат сервера не прошёл проверку доверия или срока действия. Для частного сервера можно указать доверенный SHA-256 fingerprint.'
        if isinstance(cause, ssl.SSLError):
            return 'Не удалось установить TLS-соединение. Проверьте HTTPS и порт сервера.'
        cause = cause.__cause__ or cause.__context__
    if isinstance(error, httpx.TimeoutException):
        return 'Сервер модели не ответил вовремя. Проверьте адрес, порт и доступность сервера.'
    if isinstance(error, httpx.RemoteProtocolError):
        return 'Сервер закрыл соединение или вернул неверный HTTP-ответ. Проверьте http:// или https:// и порт сервера.'
    if isinstance(error, httpx.ConnectError):
        return 'Не удалось соединиться с сервером модели. Проверьте адрес, DNS, порт и запущен ли сервер.'
    return 'Ошибка соединения с сервером модели (' + type(error).__name__ + ').'
