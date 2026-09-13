"""Create a listening page, normalized MP3s and independent ASR checks."""
import hashlib
import html
import json
import shutil
import subprocess
from pathlib import Path

import soundfile as sf
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"


def main():
    reports = [json.loads(p.read_text()) for p in sorted(OUT.glob("section-*.json"))]
    reports = [r for r in reports if "wav" in r]
    assert reports, "No completed audio yet"
    reports.sort(key=lambda r: (r["speaker"], r["variant"] != "neutral"))
    baseline = ROOT.parent / "surface-bending-manim/output-voxcpm-scenes/05-section-0.wav"
    baseline_meta = json.loads(baseline.with_suffix(".json").read_text())
    assert baseline_meta["spec"]["text"] == reports[0]["source_text"]
    shutil.copy2(baseline, OUT / "section-voxcpm2.wav")
    baseline_info = sf.info(baseline)
    reports.append({"id": "section-voxcpm2", "wav": "section-voxcpm2.wav", "variant": "voxcpm2",
                    "source_text": reports[0]["source_text"], "duration_seconds": baseline_info.duration,
                    "generation_seconds": baseline_meta["generation_seconds"], "speaker": "из образца"})
    whisper = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=6,
                           download_root="/tmp/grim-video-whisper", local_files_only=True)
    prior = json.loads((OUT / "speech-check.json").read_text()) if (OUT / "speech-check.json").exists() else []
    checks = []
    cards = {}
    titles = {"neutral": "Обычное чтение", "context": "С контекстом", "voxcpm2": "Текущая озвучка"}
    descriptions = {"neutral": "Просьба дословно прочитать текст.",
                    "context": "Контекст анимации, спокойное объяснение и смысловой акцент на противопоставлении направлений.",
                    "voxcpm2": "Готовая запись той же сцены из ролика. Озвучка целиком, голос из нашего образца."}
    for r in reports:
        wav = OUT / r["wav"]
        sha = hashlib.sha256(wav.read_bytes()).hexdigest()
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-f", "null", "-"], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-af", "loudnorm=I=-18:TP=-1.5:LRA=11",
                        "-c:a", "libmp3lame", "-q:a", "2", str(wav.with_suffix(".mp3"))], check=True)
        check = next((c for c in prior if c["sha256"] == sha), None)
        if check is None:
            segments, _ = whisper.transcribe(str(wav), language="ru", beam_size=5, word_timestamps=True)
            segments = list(segments)
            check = {"file": wav.name, "sha256": sha, "expected": r["source_text"],
                     "recognized": " ".join(s.text.strip() for s in segments),
                     "words": [{"word": w.word, "start": w.start, "end": w.end} for s in segments for w in (s.words or [])]}
        checks.append(check)
        (OUT / "speech-check.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2))
        print(wav.name, check["recognized"], flush=True)
        timing = f'{r["duration_seconds"]:.1f} с'
        if "generation_seconds" in r:
            timing += f' · синтез {r["generation_seconds"]:.0f} с · голос {html.escape(r["speaker"])}'
        mp3 = wav.with_suffix(".mp3").name
        detail = ""
        if "generated_text" in r:
            detail = '<details><summary>Текстовый ответ модели</summary><p>' + html.escape(r["generated_text"]) + '</p></details>'
        group = "VoxCPM2" if r["variant"] == "voxcpm2" else "Qwen3-Omni · " + r["speaker"]
        cards.setdefault(group, []).append(f'<article><h3>{titles[r["variant"]]}</h3><p>{descriptions[r["variant"]]}</p>'
                     f'<audio controls preload="metadata" src="{mp3}"></audio><small>{timing}</small>'
                     f'<p><a href="{mp3}" download>Скачать MP3</a> · <a href="{wav.name}" download>Исходный WAV</a></p>'
                     f'{detail}<details><summary>Проверка распознаванием</summary><p>{html.escape(check["recognized"])}</p></details></article>')
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Qwen3-Omni — проба озвучки</title><style>
*{box-sizing:border-box}body{font:17px/1.6 system-ui,sans-serif;color:#172638;background:#f3f5f7;max-width:1150px;margin:40px auto;padding:0 24px}
h1{font-size:32px;line-height:1.2}h2{font-size:25px;line-height:1.3;margin:32px 0 16px}h3{font-size:21px;line-height:1.3;margin:0}article{background:white;border:1px solid #d9e0e7;border-radius:12px;padding:22px;min-width:0}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;margin:16px 0 28px}audio{width:100%;display:block;margin:18px 0}a{color:#2058aa}small{color:#536273}details{margin:14px 0;font-size:15px}summary{cursor:pointer}.text{background:#e8edf2;padding:20px;border-radius:10px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
</style><h1>Qwen3-Omni: озвучка нормальной кривизны</h1>
<p>Одна сцена целиком. Для каждого голоса Qwen3-Omni сравниваем обычное чтение и чтение с контекстом. Тексты запросов, seed 42 и параметры синтеза одинаковы для всех голосов. Ниже — VoxCPM2 из нашего ролика.</p>
'''
    page += '<details class="text"><summary>Общий исходный текст</summary><p>' + html.escape(reports[0]["source_text"]) + '</p></details>'
    for group, group_cards in cards.items():
        page += '<section><h2>' + html.escape(group) + '</h2><div class="grid">' + ''.join(group_cards) + '</div></section>'
    page += '''<p>Громкость MP3 приведена к целевым −18 LUFS. Записи не обрезались и не склеивались. Голоса у Qwen и VoxCPM2 разные: сравниваем выразительность, паузы и произношение.</p>
<details><summary>Условия эксперимента</summary><p>Qwen/Qwen3-Omni-30B-A3B-Instruct, Transformers 5.2.0, RTX 5090 32 ГБ. Экспертные матрицы Thinker — NF4; Talker и Code2Wav — BF16. Это локальный запуск с частичным квантованием. Результат не характеризует полноточный запуск всей модели.</p>
<p>Ответ модели и независимое распознавание сохранены для проверки пропусков и добавлений. Whisper не оценивает интонацию и тоже может ошибаться. Все завершившиеся пробы этой сцены представлены без отбора.</p></details>
<script>document.querySelectorAll('audio').forEach(a=>a.addEventListener('play',()=>document.querySelectorAll('audio').forEach(b=>{if(a!==b)b.pause()})));</script></html>'''
    (OUT / "index.html").write_text(page)
    (OUT / "validation.json").write_text(json.dumps({"full_audio_decode": "passed", "samples": len(checks),
        "prosody_assessment": "Listening required; ASR checks content only"}, indent=2))


if __name__ == "__main__":
    main()
