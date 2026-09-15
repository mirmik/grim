"""Deterministic E2E completion, used only by the disposable test server."""
import json
import uuid


def completion(*, messages, **kwargs):
    last = messages[-1]
    def call(name, args):
        return {'choices': [{'message': {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': uuid.uuid4().hex, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}
        ]}, 'finish_reason': 'tool_calls'}]}
    if last['role'] == 'user':
        return call('book_read', {'path': 'chapters/oscillations.html'})
    name = messages[-2]['tool_calls'][0]['function']['name']
    result = json.loads(last['content'])
    if name == 'book_read':
        return call('book_replace', {'path': 'chapters/oscillations.html', 'expected_sha256': result['sha256'],
            'target': 'Колебание — это изменение', 'replacement': 'Колебание — это периодическое изменение'})
    text = 'Не удалось изменить: ' + result['error'] if 'error' in result else 'Уточнение записано в книгу.'
    return {'choices': [{'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}]}
