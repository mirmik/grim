"""Deterministic E2E completion, used only by the disposable test server."""
import json
import uuid


def completion(*, messages, **kwargs):
    last = messages[-1]
    if kwargs.get('config', {}).get('tool_choice') == 'none':
        return {'choices': [{'message': {'role': 'assistant', 'content': 'Сводка: обсуждаем текущую книгу. Продолжить работу с сохранёнными записками.'}, 'finish_reason': 'stop'}]}
    def call(name, args):
        return {'choices': [{'message': {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': uuid.uuid4().hex, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}
        ]}, 'finish_reason': 'tool_calls'}]}
    if last['role'] == 'user':
        if last.get('content', '').startswith('Покажи форматирование'):
            from pathlib import Path
            text = (Path(__file__).resolve().parent.parent / 'tests/fixtures/agent-markdown.md').read_text()
            return {'choices': [{'message': {'role':'assistant','content':text},'finish_reason':'stop'}]}
        if last.get('content', '').startswith('Поищи в интернете'):
            return call('web_search', {'query':'primary source research'})
        return call('book_read', {'path': 'chapters/oscillations.html'})
    name = messages[-2]['tool_calls'][0]['function']['name']
    result = json.loads(last['content'])
    if name == 'web_search':
        return call('fetch_webpage', {'url':result['results'][0]['url']})
    if name == 'fetch_webpage':
        text = ('Прочитан [Источник](https://example.org/research). '
                '[Статья](https://example.org/topic_(term)). '
                'Адрес: https://example.org/other. '
                '<img src=x onerror="alert(1)"> [текст](javascript:alert(1))')
        return {'choices': [{'message': {'role':'assistant','content':text},'finish_reason':'stop'}]}
    if name == 'book_read':
        return call('book_replace', {'path': 'chapters/oscillations.html', 'expected_sha256': result['sha256'],
            'target': 'Колебание — это изменение', 'replacement': 'Колебание — это периодическое изменение'})
    text = 'Не удалось изменить: ' + result['error'] if 'error' in result else 'Уточнение записано в книгу.'
    return {'choices': [{'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}]}


def fake_web():
    from server.web_tools import WebTools
    return WebTools(
        search_provider=lambda **_: [{'title':'Источник','href':'https://example.org/research','body':'Публичная статья'}],
        downloader=lambda url: {'url':url,'content_type':'text/html; charset=utf-8',
                                'data':'<title>Источник</title><article><p>Данные публичной статьи для чтения агентом.</p></article>'.encode()},
    )
