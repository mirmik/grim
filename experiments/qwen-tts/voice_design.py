"""Controlled local VoiceDesign comparison: identical Russian texts and seed."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/voice-design'
os.environ.setdefault('HF_HOME', str(ROOT / 'models'))
os.environ.setdefault('NUMBA_CACHE_DIR', str(OUT / 'numba-cache'))
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')


def main():
    import numpy as np
    import soundfile as sf
    import torch
    from transformers import set_seed
    from huggingface_hub import snapshot_download
    from qwen_tts import Qwen3TTSModel
    OUT.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(8)
    assert torch.cuda.is_available()
    model_id = 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign'
    revision = '5ecdb67327fd37bb2e042aab12ff7391903235d3'
    started = time.monotonic()
    path = snapshot_download(model_id, revision=revision)
    model = Qwen3TTSModel.from_pretrained(path, device_map='cuda:0', dtype=torch.bfloat16, attn_implementation='sdpa')
    settings = dict(model.generate_defaults, non_streaming_mode=True, max_new_tokens=1600)
    report = dict(model=model_id, revision=revision, gpu=torch.cuda.get_device_name(),
                  load_seconds=time.monotonic()-started,
                  versions={p:importlib.metadata.version(p) for p in ['torch','transformers','qwen-tts']}, samples=[])
    samples = {s['id']: s for s in json.loads((ROOT / 'samples.json').read_text())}
    styles = json.loads((ROOT / 'voice-design-styles.json').read_text())
    for style in styles:
        for sample_id in ['beam', 'terms']:
            sample = samples[sample_id]
            spec = dict(model=model_id, revision=revision, instruct=style['instruct'],
                        text=sample['text'], language='Russian', seed=42, settings=settings)
            file = f'{style["id"]}-{sample_id}.wav'
            wav = OUT / file
            meta = wav.with_suffix('.json')
            previous = json.loads(meta.read_text()) if meta.exists() else {}
            if wav.exists() and previous.get('spec') == spec:
                record = previous
            else:
                set_seed(42)
                torch.cuda.reset_peak_memory_stats()
                started = time.monotonic()
                with torch.inference_mode():
                    waves, sr = model.generate_voice_design(text=sample['text'], language='Russian', instruct=style['instruct'], **settings)
                torch.cuda.synchronize()
                elapsed = time.monotonic() - started
                audio = np.asarray(waves[0], dtype=np.float32).squeeze()
                assert audio.ndim == 1 and len(audio) > sr and np.isfinite(audio).all()
                sf.write(wav, audio, sr, subtype='FLOAT')
                record = dict(spec=spec, file=file, style=style['id'], sample=sample_id,
                              duration=len(audio)/sr, generation_seconds=elapsed, sample_rate=sr,
                              peak_vram_gib=torch.cuda.max_memory_allocated()/2**30,
                              sha256=hashlib.sha256(wav.read_bytes()).hexdigest())
                meta.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            report['samples'].append(record)
            (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(f'{file}: {record["duration"]:.2f}s audio, {record["generation_seconds"]:.2f}s generation', flush=True)


if __name__ == '__main__':
    main()
