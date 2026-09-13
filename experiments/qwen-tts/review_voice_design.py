"""Decode, transcribe and prepare listening copies of every VoiceDesign sample."""
import hashlib
import html
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/voice-design'


def main():
    from faster_whisper import WhisperModel
    model = WhisperModel('small', device='cpu', compute_type='int8', cpu_threads=6,
                         download_root='/tmp/grim-video-whisper', local_files_only=True)
    report = json.loads((OUT / 'report.json').read_text())
    checks = []
    for r in report['samples']:
        source = OUT / r['file']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == r['sha256']
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-f', 'null', '-'], check=True)
        segments, _ = model.transcribe(str(source), language='ru', beam_size=5, word_timestamps=True)
        segments = list(segments)
        recognized = ' '.join(s.text.strip() for s in segments)
        checks.append(dict(file=r['file'], expected=r['spec']['text'], recognized=recognized,
                           words=[dict(word=w.word, start=w.start, end=w.end) for s in segments for w in (s.words or [])]))
        print(r['file'], recognized, flush=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-af',
                        'loudnorm=I=-18:TP=-1.5:LRA=11', '-c:a', 'libmp3lame', '-q:a', '2',
                        str(source.with_suffix('.mp3'))], check=True)
    (OUT / 'speech-check.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    styles = {s['id']: s for s in json.loads((ROOT / 'voice-design-styles.json').read_text())}
    samples = {s['id']: s for s in json.loads((ROOT / 'samples.json').read_text())}
    blocks = []
    for sample_id in ['beam', 'terms']:
        blocks.append(f'<section><h2>{html.escape(samples[sample_id]["title"])}</h2>'
                      f'<details><summary>Текст</summary><p>{html.escape(samples[sample_id]["text"])}</p></details><div class="grid">')
        for style_id in ['lecturer', 'mad-scientist', 'engaged', 'patient']:
            style = styles[style_id]
            r = next(r for r in report['samples'] if r['style'] == style_id and r['sample'] == sample_id)
            check = next(c for c in checks if c['file'] == r['file'])
            mp3 = Path(r['file']).with_suffix('.mp3').name
            blocks.append(f'<article><h3>{html.escape(style["title"])}</h3><p>{html.escape(style["description"])}</p>'
                          f'<audio controls preload="metadata" src="{mp3}"></audio>'
                          f'<small>{r["duration"]:.1f} с · синтез {r["generation_seconds"]:.1f} с</small>'
                          f'<p><a href="{mp3}">MP3</a> · <a href="{r["file"]}">Исходный WAV</a></p>'
                          f'<details><summary>Инструкция модели</summary><p>{html.escape(style["instruct"])}</p></details>'
                          f'<details><summary>Распознавание Whisper</summary><p>{html.escape(check["recognized"])}</p></details></article>')
        blocks.append('</div></section>')
    baseline = ROOT / 'output/qwen/beam-42.mp3'
    if baseline.exists():
        blocks.append('<section><h2>Прежний голос по образцу «Бородино»</h2><p>Qwen Base, тот же текст про балку.</p>'
                      '<audio controls preload="none" src="../qwen/beam-42.mp3"></audio></section>')
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VoiceDesign: четыре рассказчика</title><style>
body{font:17px/1.6 system-ui,sans-serif;max-width:1080px;margin:40px auto;padding:0 22px;background:#f4f5f7;color:#172130}
h1,h2,h3{line-height:1.25}h1{font-size:32px}h2{font-size:25px}h3{font-size:21px;margin:0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:20px}
section{margin:34px 0}article{background:white;border:1px solid #d9dfe8;border-radius:12px;padding:20px;min-width:0}audio{display:block;width:100%;margin:14px 0}small{color:#526176}a{color:#245bc0}details{font-size:15px;margin-top:8px}
@media(max-width:650px){.grid{grid-template-columns:1fr}}</style>
<h1>VoiceDesign: четыре рассказчика</h1>
<p>Qwen3-TTS 1.7B VoiceDesign. Одинаковые тексты, seed 42 и параметры генерации; меняется описание голоса и манеры речи. Исходный голосовой образец не используется — тембр тоже может различаться.</p>
<p>Все восемь запланированных записей сохранены без отбора и монтажа. В плеерах MP3 с выравниванием громкости до целевых −18 LUFS, исходные WAV доступны отдельно. Интонацию и ударения оцениваем на слух; Whisper проверяет текст и сам может ошибаться.</p>'''
    page += ''.join(blocks)
    page += '''<script>document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(a!==b)b.pause()})));</script></html>'''
    (OUT / 'index.html').write_text(page)
    (OUT / 'validation.json').write_text(json.dumps(dict(full_decode='passed', source_checksums='passed',
                                                       samples=len(checks), speech_assessment='ASR only; prosody and stress require listening'), indent=2))


if __name__ == '__main__':
    main()
