"""Optional independent speech recognition check; no audio leaves this machine."""
import argparse
import json
from pathlib import Path
import time
from faster_whisper import WhisperModel

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--model", default="base")
args = parser.parse_args()
model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=6, download_root="/tmp/grim-video-whisper")
script = json.loads((root/"script.json").read_text())
results = []
for i, scene in enumerate(script):
    started = time.monotonic()
    segments, _ = model.transcribe(str(root/"output"/f"{i:02d}-{scene['id']}.wav"), language="ru", beam_size=5)
    transcript = " ".join(segment.text.strip() for segment in segments)
    results.append({"id": scene["id"], "expected": scene["text"], "recognized": transcript})
    print(f"{scene['id']} ({time.monotonic()-started:.1f}s): {transcript}", flush=True)
(root/"output"/"speech-check.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
