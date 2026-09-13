"""Local content checks and an A/B listening page; no automated prosody verdict."""
import hashlib
import html
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output'


def main():
    from faster_whisper import WhisperModel
    model = WhisperModel('small', device='cpu', compute_type='int8', cpu_threads=6,
                         download_root='/tmp/grim-video-whisper', local_files_only=True)
    report = json.loads((OUT / 'report.json').read_text())
    checks = []
    for r in report['samples']:
        source = OUT / r['file']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == r['sha256']
        subprocess.run(['ffmpeg','-v','error','-i',str(source),'-f','null','-'], check=True)
        segments, _ = model.transcribe(str(source), language='ru', beam_size=5, word_timestamps=True)
        segments = list(segments)
        recognized = ' '.join(s.text.strip() for s in segments)
        checks.append(dict(file=r['file'], expected=r['spec']['expected'], recognized=recognized,
                           words=[dict(word=w.word,start=w.start,end=w.end) for s in segments for w in (s.words or [])]))
        print(r['file'], recognized, flush=True)
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-af',
                        'loudnorm=I=-18:TP=-1.5:LRA=11','-c:a','libmp3lame','-q:a','2',
                        str(source.with_suffix('.mp3'))], check=True)
    (OUT / 'speech-check.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    blocks = []
    for sample_id, title in [('beam','Объяснение балки'),('terms','Синусоида и термины')]:
        subset = [r for r in report['samples'] if r['sample'] == sample_id]
        blocks.append(f'<section><h2>{title}</h2><details><summary>Исходный текст</summary>'
                      f'<p>{html.escape(subset[0]["spec"]["expected"])}</p></details><div class="grid">')
        for mode in report['modes']:
            r = next(r for r in subset if r['mode'] == mode['id'])
            check = next(c for c in checks if c['file'] == r['file'])
            mp3 = Path(r['file']).with_suffix('.mp3').name
            blocks.append(f'<article><h3>{html.escape(mode["title"])}</h3><p>{html.escape(mode["description"])}</p>'
                          f'<audio controls preload="metadata" src="{mp3}"></audio>'
                          f'<small>{r["duration"]:.1f} с · синтез {r["generation_seconds"]:.1f} с</small>'
                          f'<p><a href="{mp3}">MP3</a> · <a href="{r["file"]}">Исходный WAV</a></p>'
                          f'<details><summary>Распознавание Whisper</summary><p>{html.escape(check["recognized"])}</p></details></article>')
        blocks.append('</div><div class="baselines">')
        for engine in ['qwen','xtts']:
            relative = f'../../qwen-tts/output/{engine}/{sample_id}-42.mp3'
            assert (OUT / relative).exists()
            blocks.append(f'<article><h3>Для сравнения: {engine.upper()}</h3><audio controls preload="none" src="{relative}"></audio></article>')
        blocks.append('</div></section>')
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VoxCPM2 — сравнение русской речи</title><style>
body{font:17px/1.6 system-ui,sans-serif;max-width:1240px;margin:40px auto;padding:0 22px;background:#f4f5f7;color:#172130}
h1,h2,h3{line-height:1.25}h1{font-size:32px}h2{font-size:25px}h3{font-size:20px;margin:0}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:20px}.baselines{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}
section{margin:34px 0}article{background:white;border:1px solid #d9dfe8;border-radius:12px;padding:20px;min-width:0}audio{display:block;width:100%;margin:14px 0}small{color:#526176}a{color:#245bc0}details{font-size:15px;margin-top:8px}
@media(max-width:850px){.grid,.baselines{grid-template-columns:1fr}}</style>
<h1>VoxCPM2: три режима рассказчика</h1>
<p>Один образец голоса — прежняя запись «Бородино». Два текста целыми абзацами, seed 42, CFG 2.0, 10 шагов диффузии. Вариант «Спокойное объяснение» дополнительно получает инструкцию: спокойный тон, умеренный темп, чёткая дикция и естественные паузы.</p>
<p>Все шесть записей сохранены без отбора, обрезки и автоматических повторных попыток. MP3 в плеерах выровнен до целевых −18 LUFS, исходные WAV доступны отдельно. Время измерено без torch.compile. Качество интонации, ударения и сходство голоса оцениваем на слух; распознавание Whisper тоже может ошибаться.</p>'''
    page += ''.join(blocks)
    page += '''<script>document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(a!==b)b.pause()})));</script></html>'''
    (OUT / 'index.html').write_text(page)
    (OUT / 'validation.json').write_text(json.dumps(dict(full_decode='passed', source_checksums='passed',
                                                       samples=len(checks), speech_assessment='ASR only; stress and prosody require listening'), indent=2))


if __name__ == '__main__':
    main()
