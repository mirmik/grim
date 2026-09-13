"""Qwen narration for the existing beam video; keeps XTTS artifacts separate."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parent
QWEN = ROOT.parent / "qwen-tts"
OUT = ROOT / "output-qwen"
os.environ.setdefault("HF_HOME", str(QWEN / "models"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--chunking', choices=['scene', 'sentence'], default='scene')
    args = parser.parse_args()
    OUT = ROOT / ('output-qwen-scenes' if args.chunking == 'scene' else 'output-qwen')
    os.environ.setdefault("NUMBA_CACHE_DIR", str(OUT / "numba-cache"))
    import numpy as np
    import soundfile as sf
    import torch
    from transformers import set_seed
    from huggingface_hub import snapshot_download
    from qwen_tts import Qwen3TTSModel
    OUT.mkdir(exist_ok=True)
    torch.set_num_threads(8)
    assert torch.cuda.is_available()
    model_id = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    revision = "fd4b254389122332181a7c3db7f27e918eec64e3"
    path = snapshot_download(model_id, revision=revision)
    model = Qwen3TTSModel.from_pretrained(path, device_map="cuda:0", dtype=torch.bfloat16, attn_implementation="sdpa")
    reference = Path.home() / "project/for-tts-xtts/reference.wav"
    ref_text = (QWEN / "reference.txt").read_text().strip()
    prompt = model.create_voice_clone_prompt(ref_audio=str(reference), ref_text=ref_text)
    voice_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
    settings = dict(model.generate_defaults, non_streaming_mode=True, max_new_tokens=600)
    rate = 24000
    clips, timeline, records = [], [], []
    samples = 0

    def silence(seconds):
        nonlocal samples
        data = np.zeros(round(seconds * rate), dtype=np.float32)
        clips.append(data)
        samples += len(data)

    script = json.loads((ROOT / "script.json").read_text())
    for i, scene in enumerate(script):
        entry = {**scene, "start": samples / rate, "cues": []}
        silence(.35)
        utterances = ([" ".join(scene["speech"])] if args.chunking == 'scene' else
                      [s for p in scene["speech"] for s in re.split(r"(?<=[.!?])\s+", p)])
        for j, text in enumerate(utterances):
            seed = 180 + i * 10 + j
            spec = dict(text=text, seed=seed, model=model_id, revision=revision,
                        reference_sha256=voice_hash, ref_text=ref_text, settings=settings)
            wav = OUT / f"{i:02d}-{scene['id']}-{j}.wav"
            meta = wav.with_suffix(".json")
            cached = json.loads(meta.read_text()) if meta.exists() else {}
            if wav.exists() and cached.get("spec") == spec:
                audio, sr = sf.read(wav, dtype="float32")
                record = cached
            else:
                set_seed(seed)
                started = time.monotonic()
                torch.cuda.reset_peak_memory_stats()
                with torch.inference_mode():
                    waves, sr = model.generate_voice_clone(text=text, language="Russian", voice_clone_prompt=prompt, **settings)
                torch.cuda.synchronize()
                audio = np.asarray(waves[0], dtype=np.float32).squeeze()
                assert audio.ndim == 1 and len(audio) > sr / 2 and np.isfinite(audio).all()
                sf.write(wav, audio, sr, subtype="FLOAT")
                record = dict(spec=spec, file=wav.name, duration=len(audio)/sr,
                              generation_seconds=time.monotonic()-started,
                              peak_vram_gib=torch.cuda.max_memory_allocated()/2**30)
                meta.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            assert sr == rate
            records.append(record)
            print(f"{wav.name}: {len(audio)/rate:.2f}s", flush=True)
            start = samples / rate
            clips.append(audio)
            samples += len(audio)
            entry["cues"].append(dict(start=start, end=samples/rate, text=text, file=wav.name))
            silence(.20 if j < len(utterances)-1 else .8)
        entry["end"] = samples / rate
        timeline.append(entry)
    silence(1)
    timeline[-1]["end"] = samples / rate
    sf.write(OUT / "narration.wav", np.concatenate(clips), rate, subtype="FLOAT")
    (OUT / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2))
    (OUT / "synthesis-report.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(f"Narration: {samples/rate:.2f}s", flush=True)


if __name__ == "__main__":
    main()
