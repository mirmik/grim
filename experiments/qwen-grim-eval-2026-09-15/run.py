"""Local writing experiment. PyYAML is needed only for the config auth fallback."""
import argparse
import json
import os
import ssl
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = 'qwen3.8-27b-uncensored-q4-mtp'
BASE = 'http://192.168.0.173:8096'


def context(name):
    return (ROOT / 'context' / name).read_text()


SYSTEM = '''Ты пишешь учебную книгу Grim на русском языке для читателя, знакомого с производными, векторами и матрицами. Верни только запрошенный материал в Markdown с LaTeX. Не выдумывай ссылки. Математическая корректность важнее уверенного тона. Если нужна иллюстрация, укажи рядом точное описание и подпись; сами изображения сейчас не создавай.

Редакционные требования проекта:
''' + context('how-to-write-learning-materials.md')


def samples(names):
    return '\n\n'.join('=== КОНТЕКСТ КНИГИ: ' + n + ' ===\n' + context(n + '.txt') for n in names)


CONTINUATION = samples(['introduction', 'vector-fields-and-comparison', 'covariant-derivative-and-connection']) + '''

ЗАДАНИЕ: Напиши следующую главу «Параллельный перенос» объёмом примерно 1200–1600 русских слов, сопоставимую с существующими главами по глубине и тону. Читатель уже прочёл приведённые главы. Продолжай книгу последовательно: объясни, как по начальному вектору построить поле вдоль заданного пути, выведи координатное уравнение, объясни сохранение длин и углов и зависимость от пути. Дай один законченный наглядный пример переноса на сфере с вычисленным результатом и описанием рисунка. Заверши переходом к будущей главе о геодезических. Это должна быть готовая проза главы, а не план и не конспект. Не пересказывай заново большие куски предыдущей главы.'''

CASES = {
    '01_parallel_a': (CONTINUATION, 42, 18000),
    '02_parallel_b': (CONTINUATION, 43, 18000),
    '03_connection': (samples(['introduction', 'vector-fields-and-comparison']) + '''

ЗАДАНИЕ: Напиши главу «Ковариантная производная и связность Леви-Чивиты» (примерно 1200–1600 русских слов). Это следующая глава после приведённой главы о векторных полях. Объясни связность как правило сравнения, смысл согласованности с метрикой и отсутствия кручения; сформулируй существование и единственность связности Леви-Чивиты; выведи символы Кристоффеля через метрику и формулу производной поля. Читатель должен понимать, зачем нужны два требования и откуда берутся формулы. Закончи переходом к параллельному переносу. Соблюдай уровень, обозначения и характер изложения книги. Нужна готовая глава, а не план.''', 42, 18000),
    '04_calculations': ('''Напиши два небольших учебных разбора в стиле Grim: интуиция, вычисления, геометрический вывод. Объём суммарно 700–1100 слов. Все результаты вычисли, не ограничивайся общими формулами.

1. Плоскость в полярных координатах (r,θ), r>0: ds²=dr²+r²dθ². В координатном базисе (∂r,∂θ) найди ненулевые символы Кристоффеля. Постоянный декартов вектор V=(1,0) запиши в этом базисе и вычисли ∇_{∂r}V и ∇_{∂θ}V. Объясни, как соотносятся полученные коэффициенты с кривизной плоскости. Затем для ортонормированного базиса E1=∂r, E2=(1/r)∂θ вычисли ∇_{E1}E2−∇_{E2}E1 и кручение T(E1,E2).

2. Регулярная поверхность r(u,v)=(u+v,v,((u+v)²+2v²)/2), нормаль выбрана с положительной третьей компонентой. В точке (0,0) найди матрицы первой и второй фундаментальных форм, оператора формы S=−dn, главные кривизны и главные направления. Объясни, в каком смысле оператор формы симметричен, и вычисли нормальную кривизну направления с координатными компонентами (1,0).''', 42, 14000),
    '05_editor': ('''Ты научный редактор Grim. Ниже черновик автора. Проверь каждый из 8 пунктов: верно, неверно или нужны условия. Дай короткое математическое обоснование и готовую исправленную формулировку для учебника. Не считай, что все пункты обязательно ошибочны. Объём 700–1200 слов.

1. Связность Леви-Чивиты не имеет кручения, поэтому при параллельном переносе по любому замкнутому контуру вектор вернётся к исходному направлению.
2. Ненулевые символы Кристоффеля в выбранных координатах доказывают, что поверхность искривлена.
3. Оператор формы самосопряжён, следовательно его матрица симметрична в любом координатном базисе.
4. При соглашении S=−dn и внешней нормали у сферы радиуса R>0 обе главные кривизны равны +1/R.
5. Каждая геодезическая соединяет любые две свои точки кратчайшим путём.
6. Если гауссова кривизна равна нулю всюду, параллельный перенос не зависит от пути, даже если область не односвязна. Например, на конусе без вершины.
7. Для любой связности и любых гладких векторных полей X,Y её кручение равно ∇_X Y−∇_Y X.
8. Для связности Леви-Чивиты, если два вектора параллельно переносятся вдоль одного и того же пути, их скалярное произведение постоянно.''', 42, 14000),
    '06_without_examples': ('''Создай начало учебного пособия по дифференциальной геометрии на русском языке. У тебя нет образцов книги и готового оглавления. Руководствуйся только рекомендациями по составлению учебных материалов из системного сообщения.

Напиши введение, включающее предварительный учебный план всей книги, и первые две полноценные главы. Содержание, порядок тем, названия глав, методический маршрут и примеры выбери самостоятельно. Во введении обозначь, что читатель должен знать до начала и чему научится. Первые главы должны действительно начать реализовывать твой план. Аудитория знакома с производными, векторами и матрицами, но ещё не изучала дифференциальную геометрию. Ориентир общего объёма — 2400–3200 русских слов. Нужен текст пособия, не заявка на него и не краткий конспект. Если нужны рисунки, дай точные описания и содержательные подписи рядом с соответствующим объяснением.''', 42, 26000),
}


def run(name, prompt, seed, limit, messages=None):
    dest = ROOT / 'runs' / name
    dest.mkdir(parents=True, exist_ok=True)
    if (dest / 'result.json').exists():
        print(name, 'already completed', flush=True)
        return
    # User explicitly requested thinking without an artificial generation cap.
    # Runtime /props reports max_tokens=-1 and n_ctx=131072. The legacy `limit`
    # argument documents earlier pilots; no max_tokens is sent in this run.
    payload = dict(model=MODEL, messages=messages or [dict(role='system', content=SYSTEM), dict(role='user', content=prompt)], temperature=0.6, top_p=0.9, seed=seed, stream=True, stream_options={'include_usage': True}, chat_template_kwargs={'enable_thinking': True})
    (dest / 'request.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    started = time.time()
    meta = dict(model=MODEL, base_url=BASE, started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), tls_verification=False)
    headers = {'Content-Type': 'application/json'}
    token = os.environ.get('GRIM_EVAL_API_KEY')
    if BASE.endswith(':8080') and not token:
        import yaml
        config = yaml.safe_load(Path('/home/mirmik/.config/llm-proxy/config.yaml').read_text())
        auth = config['routes'][MODEL]['backends'][0]['auth']
        token = config['hosts'][auth]['token']
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(BASE + '/v1/chat/completions', data=json.dumps(payload).encode(), headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
    print(name, 'started', flush=True)
    try:
        meta['sse_done'] = False
        with opener.open(request, timeout=900) as response, (dest / 'events.jsonl').open('w') as events, (dest / 'answer.md').open('w') as answer, (dest / 'reasoning.txt').open('w') as reasoning:
            meta['http_status'] = response.status
            for raw in response:
                line = raw.decode().strip()
                if not line.startswith('data: '):
                    continue
                data = line[6:]
                if data == '[DONE]':
                    meta['sse_done'] = True
                    break
                chunk = json.loads(data)
                events.write(json.dumps(chunk, ensure_ascii=False) + '\n'); events.flush()
                if chunk.get('usage'):
                    meta['usage'] = chunk['usage']
                for choice in chunk.get('choices', []):
                    delta = choice.get('delta', {})
                    if delta.get('content'):
                        if 'first_content_seconds' not in meta:
                            meta['first_content_seconds'] = time.time() - started
                        answer.write(delta['content']); answer.flush()
                    for key in ['reasoning_content', 'reasoning']:
                        if delta.get(key):
                            reasoning.write(delta[key]); reasoning.flush()
                    if choice.get('finish_reason'):
                        meta['finish_reason'] = choice['finish_reason']
                for key in ['model', 'timings', 'system_fingerprint']:
                    if key in chunk:
                        meta['response_' + key] = chunk[key]
        meta['elapsed_seconds'] = time.time() - started
        meta['complete'] = meta.get('finish_reason') == 'stop' and meta['sse_done']
        meta['answer_words_whitespace'] = len((dest / 'answer.md').read_text().split())
        (dest / 'result.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        print(name, json.dumps(meta, ensure_ascii=False), flush=True)
    except Exception as exc:
        meta.update(error=str(exc), elapsed_seconds=time.time() - started)
        (dest / 'error.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cases', nargs='*', default=list(CASES))
    args = parser.parse_args()
    for name in args.cases:
        run(name, *CASES[name])
