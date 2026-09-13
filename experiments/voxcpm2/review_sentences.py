"""Compare split vs whole speech and verify lossless assembly of sentence WAVs."""
import hashlib
import html
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/sentences'


def main():
    import numpy as np
    import soundfile as sf
    from faster_whisper import WhisperModel
    model = WhisperModel('small', device='cpu', compute_type='int8', cpu_threads=6,
                         download_root='/tmp/grim-video-whisper', local_files_only=True)
    report = json.loads((OUT / 'report.json').read_text())
    baseline = json.loads((OUT.parent / 'report.json').read_text())
    checks = []
    chunk_count = 0
    for r in report['samples']:
        path = OUT / r['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == r['sha256']
        mixed, sr = sf.read(path, dtype='float32')
        last = 0
        for cue in r['cues']:
            chunk_path = OUT / cue['file']
            assert hashlib.sha256(chunk_path.read_bytes()).hexdigest() == cue['sha256']
            audio, chunk_sr = sf.read(chunk_path, dtype='float32')
            start, end = round(cue['start']*sr), round(cue['end']*sr)
            assert chunk_sr == sr and end-start == len(audio)
            assert np.array_equal(mixed[start:end], audio)
            assert np.all(mixed[last:start] == 0)
            assert start-last == (0 if last == 0 else round(.2*sr))
            last = end
            chunk_count += 1
        assert last == len(mixed)
        assert ' '.join(c['text'] for c in r['cues']) == r['spec']['expected']
        subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'], check=True)
        segments, _ = model.transcribe(str(path), language='ru', beam_size=5, word_timestamps=True)
        segments = list(segments)
        recognized = ' '.join(s.text.strip() for s in segments)
        checks.append(dict(file=r['file'], expected=r['spec']['expected'], recognized=recognized,
                           words=[dict(word=w.word,start=w.start,end=w.end) for s in segments for w in (s.words or [])]))
        print(r['file'], recognized, flush=True)
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(path),'-af',
                        'loudnorm=I=-18:TP=-1.5:LRA=11','-c:a','libmp3lame','-q:a','2',
                        str(path.with_suffix('.mp3'))], check=True)
    (OUT / 'speech-check.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    blocks = []
    for sample_id,title in [('beam','Объяснение балки'),('terms','Синусоида и термины')]:
        blocks.append(f'<section><h2>{title}</h2>')
        for mode in report['modes']:
            r = next(r for r in report['samples'] if r['mode']==mode['id'] and r['sample']==sample_id)
            b = next(r for r in baseline['samples'] if r['mode']==mode['id'] and r['sample']==sample_id)
            check = next(c for c in checks if c['file']==r['file'])
            name = Path(r['file']).with_suffix('.mp3').name
            blocks.append(f'<h3>{html.escape(mode["title"])}</h3><div class="pair">'
                          f'<article><strong>Цельный абзац · {b["duration"]:.1f} с</strong>'
                          f'<audio controls preload="none" src="../{name}"></audio>')
            if mode['id']=='calm' and sample_id=='beam':
                blocks.append('<p>В этой прежней записи отсутствуют два заключительных предложения.</p>')
            blocks.append(f'</article><article><strong>По предложениям · {r["duration"]:.1f} с</strong>'
                          f'<audio controls preload="metadata" src="{name}"></audio>'
                          f'<p>{len(r["cues"])} отдельных генераций, добавленная пауза 0,2 с.</p>'
                          f'<p><a href="{name}">MP3</a> · <a href="{r["file"]}">WAV</a></p>'
                          f'<details><summary>Распознавание</summary><p>{html.escape(check["recognized"])}</p></details></article></div>')
        blocks.append('</section>')
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VoxCPM2: абзац или предложения</title><style>
body{font:17px/1.6 system-ui,sans-serif;max-width:1080px;margin:40px auto;padding:0 22px;background:#f4f5f7;color:#172130}
h1,h2,h3{line-height:1.25}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}section{margin:34px 0}article{background:white;border:1px solid #d9dfe8;border-radius:12px;padding:20px;min-width:0}audio{display:block;width:100%;margin:14px 0}a{color:#245bc0}details{font-size:15px}
@media(max-width:650px){.pair{grid-template-columns:1fr}}</style><h1>VoxCPM2: абзац или предложения</h1>
<p>Справа каждое предложение синтезировано отдельным вызовом. Использованы те же модель, голосовой образец, CFG 2.0, 10 шагов диффузии и seed 42 перед каждым вызовом. Между исходными WAV добавлено по 0,2 с тишины; внутренние паузы и речевые хвосты не обрезались.</p>
<p>В плеерах — MP3 с выравниванием громкости до целевых −18 LUFS. Все запланированные фразы сохранены без отбора. Распознавание помогает проверить содержание, но не оценивает интонацию и ударения.</p>'''
    page += ''.join(blocks)
    page += '''<script>document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(a!==b)b.pause()})));</script></html>'''
    (OUT / 'index.html').write_text(page)
    (OUT / 'validation.json').write_text(json.dumps(dict(full_decode='passed', chunks=chunk_count,
        assembly='Source WAVs match sample-for-sample; all inserted gaps are 0.2s of silence',
        expected_sentence_texts='passed', source_checksums='passed', samples=len(checks)), indent=2))


if __name__ == '__main__':
    main()
