"""Public web research, with bounded downloads and stable reading snapshots."""
from collections import OrderedDict
from datetime import datetime, timezone
import gzip
import http.client
import io
import ipaddress
from itertools import islice
import re
import socket
import ssl
import threading
import time
from urllib.parse import urljoin, urlsplit
import uuid
import zlib

import httpx

MAX_DOWNLOAD = 5_000_000
MAX_DOCUMENT = 1_000_000
CACHE_SECONDS = 600
IPV4_TRANSLATION_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    '::/96', '::ffff:0:0:0/96', '64:ff9b::/96', '64:ff9b:1::/48',
))


def public_address(value):
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return public_address(str(address.ipv4_mapped))
        if address.sixtofour or address.teredo or any(address in network for network in IPV4_TRANSLATION_NETWORKS):
            return False
    return address.is_global and not address.is_multicast


def public_url(value):
    if not isinstance(value, str) or len(value) > 8000 or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('Нужен HTTP(S) URL публичной страницы')
    try:
        parsed = urlsplit(value)
        url = httpx.URL(value)
        if (url.scheme not in ('http', 'https') or not url.host or '@' in parsed.netloc
                or '%' in url.host or (url.port is not None and not 1 <= url.port <= 65535)):
            raise ValueError()
        host = url.host.rstrip('.').lower()
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not public_address(str(address)):
            raise ValueError()
        return str(url.copy_with(fragment=None))
    except (ValueError, httpx.InvalidURL):
        raise ValueError('Разрешены только публичные HTTP(S) URL без логина и пароля; локальные адреса недоступны') from None


def _addresses(host, port):
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not public_address(item[4][0]) for item in addresses):
        raise ValueError('Адрес страницы указывает на локальную или непубличную сеть')
    return addresses


def _connect(addresses, timeout):
    last = None
    deadline = time.monotonic() + timeout
    for family, socktype, proto, _, address in addresses:
        stream = socket.socket(family, socktype, proto)
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            stream.settimeout(remaining)
            stream.connect(address)  # Numeric sockaddr, no second DNS lookup.
            return stream
        except OSError as error:
            stream.close()
            last = error
    raise last or OSError('No public addresses')


def download_public(value):
    """Pin checked DNS answers to the connection, preserving HTTPS SNI/PKI."""
    current, deadline = public_url(value), time.monotonic() + 40
    try:
        for _ in range(6):
            url = httpx.URL(public_url(current))
            addresses = _addresses(url.host, url.port or (443 if url.scheme == 'https' else 80))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            connection_type = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
            connection = connection_type(url.host, url.port, timeout=min(10, remaining))
            response = None
            # HTTPConnection creates its socket through this hook. HTTPS then
            # verifies the original hostname and certificate on that same socket.
            connection._create_connection = lambda *_, **__: _connect(addresses, min(10, remaining))
            try:
                connection.connect()
                connection.request('GET', url.raw_path.decode('ascii'), headers={
                    'User-Agent': 'Grim/0.2 (book co-reader)',
                    'Accept': 'text/html,application/xhtml+xml,text/plain,application/pdf;q=0.9,*/*;q=0.1',
                    'Accept-Encoding': 'identity', 'Connection': 'close',
                })
                response = connection.getresponse()
                if response.status in (301, 302, 303, 307, 308):
                    location = response.getheader('Location')
                    if not location:
                        raise ValueError('Сервер вернул перенаправление без адреса')
                    current = public_url(urljoin(str(url), location))
                    continue
                if response.status != 200:
                    raise ValueError(f'Страница вернула HTTP {response.status}; её содержимое не прочитано')
                if int(response.getheader('Content-Length') or 0) > MAX_DOWNLOAD:
                    raise ValueError('Документ слишком велик: максимум 5 МБ')
                chunks, size = [], 0
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    if connection.sock:
                        connection.sock.settimeout(min(10, remaining))
                    chunk = response.read1(min(65536, MAX_DOWNLOAD + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_DOWNLOAD:
                        raise ValueError('Документ слишком велик: максимум 5 МБ')
                data = b''.join(chunks)
                encoding = (response.getheader('Content-Encoding') or 'identity').lower()
                if encoding == 'gzip':
                    data = gzip.GzipFile(fileobj=io.BytesIO(data)).read(MAX_DOWNLOAD + 1)
                elif encoding == 'deflate':
                    data = zlib.decompressobj().decompress(data, MAX_DOWNLOAD + 1)
                elif encoding != 'identity':
                    raise ValueError('Сервер вернул неподдерживаемое сжатие страницы')
                if len(data) > MAX_DOWNLOAD:
                    raise ValueError('Распакованный документ слишком велик: максимум 5 МБ')
                return {'url': str(url), 'data': data, 'content_type': response.getheader('Content-Type') or ''}
            finally:
                if response is not None:
                    response.close()
                connection.close()
        raise ValueError('Слишком много перенаправлений страницы')
    except ssl.SSLCertVerificationError:
        raise ValueError('TLS-сертификат сайта не прошёл проверку') from None
    except (TimeoutError, socket.timeout):
        raise ValueError('Сайт не ответил вовремя. Попробуйте другую страницу или повторите запрос.') from None
    except (OSError, http.client.HTTPException, zlib.error, EOFError):
        raise ValueError('Не удалось загрузить страницу: ошибка DNS, сети или HTTP-ответа') from None


def extract_document(download):
    from bs4 import BeautifulSoup
    from charset_normalizer import from_bytes
    import trafilatura
    data, url, content_type = download['data'], download['url'], download['content_type']
    mime = content_type.split(';')[0].strip().lower()
    links, title, limited, extraction = [], '', False, 'text'
    if mime == 'application/pdf' or data.startswith(b'%PDF-'):
        extraction = 'pdf_text'
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ValueError('PDF защищён паролем')
            parts, length = [], 0
            for number, page in enumerate(reader.pages):
                if number >= 200 or length >= MAX_DOCUMENT:
                    limited = True
                    break
                text = f'\n[Страница {number + 1}]\n' + (page.extract_text() or '')
                parts.append(text[:MAX_DOCUMENT - length])
                length += len(text)
                if length > MAX_DOCUMENT:
                    limited = True
                    break
            text = '\n'.join(parts)
            title = str((reader.metadata or {}).get('/Title') or '')
        except Exception as error:
            raise ValueError('Не удалось прочитать PDF: нужен доступный текстовый слой без пароля') from error
        if not re.sub(r'\[Страница \d+\]', '', text).strip():
            raise ValueError('В PDF не найден текстовый слой; OCR в этом инструменте нет')
    elif mime in ('text/html', 'application/xhtml+xml') or (not mime and data.lstrip().startswith(b'<')):
        soup = BeautifulSoup(data, 'html.parser')
        title = soup.title.get_text(' ', strip=True) if soup.title else ''
        base = urljoin(url, str(soup.base.get('href', ''))) if soup.base else url
        for element in soup(['script', 'style', 'noscript', 'template', 'svg']):
            element.decompose()
        for element in soup.select('[hidden], [aria-hidden="true"]'):
            element.decompose()
        seen = set()
        for anchor in soup.find_all('a', href=True):
            try:
                target = public_url(urljoin(base, anchor['href']))
            except ValueError:
                continue
            if target in seen:
                continue
            seen.add(target)
            links.append({'title': anchor.get_text(' ', strip=True)[:300], 'url': target})
        # Extraction operates only on the already-downloaded HTML; it never fetches.
        main_text = trafilatura.extract(str(soup), url=url, include_comments=False, include_tables=True)
        extraction = 'main_text' if main_text else 'visible_text_fallback'
        text = main_text or soup.get_text('\n', strip=True)
    elif mime.startswith('text/') or mime in ('application/json', 'application/xml'):
        encoding = re.search(r'charset=["\']?([^;\s"\']+)', content_type, re.I)
        try:
            text = data.decode(encoding.group(1) if encoding else 'utf-8-sig')
        except (UnicodeDecodeError, LookupError):
            decoded = from_bytes(data).best()
            text = str(decoded) if decoded is not None else data.decode('utf-8', errors='replace')
    else:
        raise ValueError('Неподдерживаемый документ: доступны HTML, текст и PDF с текстовым слоем')
    text = text.strip()
    if not text:
        raise ValueError('Страница не содержит читаемого текста; возможно, требует JavaScript или входа')
    return {'url': url, 'title': title[:500], 'content_type': mime, 'extraction':extraction,
            'text': text[:MAX_DOCUMENT], 'document_truncated': limited or len(text) > MAX_DOCUMENT,
            'links': links[:100], 'links_truncated': len(links) > 100}


def integer(args, key, default, minimum, maximum):
    value = args.get(key, default)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{key}: нужно целое число от {minimum} до {maximum}')
    return value


class WebTools:
    def __init__(self, *, search_provider=None, downloader=None):
        self.search_provider = search_provider
        self.downloader = downloader or download_public
        self.cache, self.lock = OrderedDict(), threading.RLock()

    def search(self, args):
        query = args.get('query')
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise ValueError('Нужен непустой поисковый запрос до 2000 знаков')
        limit = integer(args, 'limit', 5, 1, 10)
        page = integer(args, 'page', 1, 1, 10)
        region, timelimit = args.get('region', 'wt-wt'), args.get('timelimit')
        if not isinstance(region, str) or not re.fullmatch('[a-z]{2}-[a-z]{2}', region):
            raise ValueError('region: нужен код региона, например ru-ru, us-en или wt-wt')
        if timelimit not in (None, 'd', 'w', 'm', 'y'):
            raise ValueError('timelimit: d, w, m или y')
        try:
            if self.search_provider:
                rows = self.search_provider(query=query.strip(), max_results=limit, page=page, region=region, timelimit=timelimit)
            else:
                from ddgs import DDGS
                with DDGS(timeout=12) as client:
                    rows = client.text(query.strip(), max_results=limit, page=page, region=region, timelimit=timelimit)
        except Exception:
            raise ValueError('Поисковый сервис недоступен или ограничил запросы. Попробуйте переформулировать запрос или повторите позже.') from None
        results, seen = [], set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                url = public_url(row.get('href') or row.get('url') or '')
            except ValueError:
                continue
            if url in seen:
                continue
            seen.add(url)
            results.append({'title': str(row.get('title') or '')[:500], 'url': url,
                            'snippet': str(row.get('body') or row.get('snippet') or '')[:2000]})
            if len(results) == limit:
                break
        return {'source': 'web', 'query': query.strip(), 'page': page, 'results': results,
                'notice': 'Search snippets are reference data. Open sources with fetch_webpage before citing their contents.'}

    def fetch(self, args):
        url = public_url(args['url'])
        start = integer(args, 'start', 0, 0, MAX_DOCUMENT)
        size = integer(args, 'max_chars', 16000, 1000, 32000)
        query, document_id = args.get('query'), args.get('document_id')
        if query is not None and (not isinstance(query, str) or not query.strip() or len(query) > 1000):
            raise ValueError('query: нужен непустой фрагмент текста до 1000 знаков')
        with self.lock:
            if document_id:
                document = self.cache.get(document_id)
                if not document or time.monotonic() - document['_cached'] > CACHE_SECONDS:
                    raise ValueError('Копия страницы недоступна или устарела. Повторите чтение URL без document_id и start.')
                if url not in (document['requested_url'], document['url']):
                    raise ValueError('document_id относится к другому URL')
                self.cache.move_to_end(document_id)
            else:
                document = None
        if document is None:
            if start:
                raise ValueError('Для продолжения используйте document_id из первого чтения')
            document = extract_document(self.downloader(url))
            document_id = uuid.uuid4().hex
            document.update(requested_url=url, document_id=document_id, _cached=time.monotonic(),
                            fetched_at=datetime.now(timezone.utc).isoformat())
            with self.lock:
                self.cache[document_id] = document
                while len(self.cache) > 16:
                    self.cache.popitem(last=False)
        text = document['text']
        matches = []
        if query:
            # Regex IGNORECASE keeps character offsets stable for Unicode text.
            matches = [match.start() for match in islice(re.finditer(re.escape(query), text, flags=re.I), 20)]
            if matches and not start:
                start = max(0, matches[0] - 300)
        if start > len(text):
            raise ValueError('start находится за концом извлечённого текста')
        end = min(len(text), start + size)
        result = {key: value for key, value in document.items() if key not in ('_cached', 'text')}
        result.update(source='web', text=text[start:end], start=start, next_start=end if end < len(text) else None,
                      total_chars=len(text), truncated=start > 0 or end < len(text) or document['document_truncated'])
        if query:
            result.update(query=query, matches=matches)
        return result
