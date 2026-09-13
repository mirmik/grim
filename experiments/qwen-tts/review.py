"""Check transcription and create a portable listening page; does not judge prosody."""
import html
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"


def words(text):
    return re.findall(r"[а-яa-z0-9]+", text.lower().replace("ё", "е"))


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        nxt = [i]
        for j, y in enumerate(b, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j-1] + (x != y)))
        row = nxt
    return row[-1]


def main():
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=6,
                         download_root="/tmp/grim-video-whisper", local_files_only=True)
    results = []
    for engine in ["qwen", "xtts"]:
        report = json.loads((OUT / engine / "report.json").read_text())
        for record in report["samples"]:
            path = OUT / engine / record["file"]
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], check=True)
            segs, _ = model.transcribe(str(path), language="ru", beam_size=5, word_timestamps=True)
            segments = list(segs)
            recognized = " ".join(s.text.strip() for s in segments)
            expected_words, actual_words = words(record["text"]), words(recognized)
            result = {**record, "engine": engine, "recognized": recognized,
                      "asr_word_error_ratio": distance(expected_words, actual_words) / len(expected_words),
                      "words": [{"word": w.word, "start": w.start, "end": w.end} for s in segments for w in s.words]}
            results.append(result)
            print(engine, record["file"], recognized, flush=True)
    (OUT / "speech-check.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    body = []
    for item in json.loads((ROOT / "samples.json").read_text()):
        body.append(f'<section><h2>{html.escape(item["title"])}</h2><p>{html.escape(item["text"])}</p>')
        for seed in item["seeds"]:
            body.append(f'<h3>Повтор / seed {seed}</h3><div class="pair">')
            for engine in ["qwen", "xtts"]:
                r = next(x for x in results if x["engine"] == engine and x["id"] == item["id"] and x["seed"] == seed)
                # Listening copies have equal target loudness; untouched WAV files remain linked.
                source = OUT / engine / r["file"]
                target = source.with_suffix(".mp3")
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af",
                                "loudnorm=I=-18:TP=-1.5:LRA=11", "-c:a", "libmp3lame", "-q:a", "2", str(target)], check=True)
                body.append(f'<article><strong>{engine.upper()}</strong><audio controls preload="none" src="{engine}/{target.name}"></audio>'
                            f'<small>{r["duration"]:.1f} с аудио · синтез {r["generation_seconds"]:.1f} с</small>'
                            f'<p><a href="{engine}/{source.name}">Исходный WAV</a></p>'
                            f'<details><summary>Распознавание Whisper</summary><p>{html.escape(r["recognized"])}</p></details></article>')
            body.append('</div>')
        body.append('</section>')
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Qwen и XTTS — сравнение русской речи</title><style>
body{font:17px/1.6 system-ui,sans-serif;max-width:1060px;margin:40px auto;padding:0 22px;background:#f4f5f7;color:#172130}
h1,h2,h3{line-height:1.2}h1{font-size:32px}h2{font-size:23px}h3{font-size:17px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:18px}
section{margin:34px 0}article{background:white;border:1px solid #d9dfe8;border-radius:12px;padding:18px;min-width:0}audio{display:block;width:100%;margin:14px 0}small{color:#526176}a{color:#245bc0}details{font-size:14px}
@media(max-width:650px){.pair{grid-template-columns:1fr}}</style><h1>Qwen3-TTS и XTTS</h1>
<p>Один образец голоса, одинаковые тексты. Qwen3-TTS 1.7B Base и XTTS v2. Все запланированные повторы сохранены; монтаж и удаление лишних слов не применялись.</p>
<p>В плеерах — MP3 с выравниванием громкости до целевых −18 LUFS; исходные WAV доступны отдельно. Ударения, интонацию и сходство голоса оцениваем на слух. Распознавание Whisper — вспомогательная проверка текста, оно тоже может ошибаться.</p>'''
    (OUT / "index.html").write_text(page + "".join(body) + "</html>")


if __name__ == "__main__":
    main()
