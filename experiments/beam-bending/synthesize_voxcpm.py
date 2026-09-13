"""Two beam narrations with identical VoxCPM2 clone settings and different chunks."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parent
VOX = ROOT.parent / 'voxcpm2'
os.environ.setdefault('HF_HOME', str(VOX / 'models'))
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('NUMBA_CACHE_DIR', str(VOX / 'output/numba-cache'))
os.environ.setdefault('MPLCONFIGDIR', str(VOX / 'output/mpl-cache'))
os.environ.setdefault('TQDM_DISABLE', '1')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chunking', choices=['scene','sentence','both'], default='both')
    args = parser.parse_args()
    import numpy as np
    import soundfile as sf
    import torch
    from transformers import set_seed
    from huggingface_hub import snapshot_download
    from voxcpm import VoxCPM
    torch.set_num_threads(8)
    assert torch.cuda.is_available()
    model_id = 'openbmb/VoxCPM2'
    revision = '32279effe8c19989596f05d353d1447f51d9e915'
    model_path = snapshot_download(model_id, revision=revision)
    model = VoxCPM.from_pretrained(model_path, load_denoiser=False, optimize=False, device='cuda:0')
    reference = Path.home() / 'project/for-tts-xtts/reference.wav'
    voice_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
    settings = dict(cfg_value=2.0, inference_timesteps=10, max_len=700,
                    normalize=False, denoise=False, retry_badcase=False)
    script = json.loads((ROOT / 'script.json').read_text())
    variants = ['scene','sentence'] if args.chunking == 'both' else [args.chunking]
    rate = model.tts_model.sample_rate
    for variant in variants:
        out = ROOT / ('output-voxcpm-scenes' if variant == 'scene' else 'output-voxcpm-sentences')
        out.mkdir(exist_ok=True)
        clips, timeline, records = [], [], []
        total = 0

        def silence(seconds):
            nonlocal total
            data = np.zeros(round(seconds*rate), dtype=np.float32)
            clips.append(data)
            total += len(data)

        for i, scene in enumerate(script):
            entry = {**scene, 'start':total/rate, 'cues':[]}
            silence(.35)
            texts = ([' '.join(scene['speech'])] if variant == 'scene' else
                     [s for p in scene['speech'] for s in re.split(r'(?<=[.!?])\s+', p)])
            for j, text in enumerate(texts):
                wav = out / f'{i:02d}-{scene["id"]}-{j}.wav'
                meta = wav.with_suffix('.json')
                spec = dict(model=model_id, revision=revision, mode='clone', text=text, seed=42,
                            reference_sha256=voice_hash, settings=settings)
                cached = json.loads(meta.read_text()) if meta.exists() else {}
                if wav.exists() and cached.get('spec') == spec:
                    assert hashlib.sha256(wav.read_bytes()).hexdigest() == cached['sha256']
                    audio, sr = sf.read(wav, dtype='float32')
                    record = cached
                else:
                    set_seed(42)
                    torch.cuda.reset_peak_memory_stats()
                    started = time.monotonic()
                    with torch.inference_mode():
                        result = model.generate(text=text, reference_wav_path=str(reference), **settings)
                    torch.cuda.synchronize()
                    elapsed = time.monotonic()-started
                    audio = np.asarray(result, dtype=np.float32).squeeze()
                    sr = rate
                    assert audio.ndim == 1 and len(audio) > sr/4 and np.isfinite(audio).all()
                    sf.write(wav, audio, sr, subtype='FLOAT')
                    record = dict(spec=spec, file=wav.name, duration=len(audio)/sr,
                                  generation_seconds=elapsed,
                                  peak_vram_gib=torch.cuda.max_memory_allocated()/2**30,
                                  sha256=hashlib.sha256(wav.read_bytes()).hexdigest())
                    meta.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                assert sr == rate
                records.append(record)
                start = total/rate
                clips.append(audio)
                total += len(audio)
                entry['cues'].append(dict(start=start,end=total/rate,text=text,file=wav.name))
                silence(.2 if j < len(texts)-1 else .8)
                print(f'{variant}: {wav.name} {len(audio)/rate:.2f}s', flush=True)
            entry['end'] = total/rate
            timeline.append(entry)
        silence(1)
        timeline[-1]['end'] = total/rate
        sf.write(out / 'narration.wav', np.concatenate(clips), rate, subtype='FLOAT')
        (out / 'timeline.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=2))
        report = dict(model=model_id,revision=revision,chunking=variant,gpu=torch.cuda.get_device_name(),
                      versions={p:importlib.metadata.version(p) for p in ['voxcpm','torch','transformers']},
                      duration=total/rate,samples=records)
        (out / 'synthesis-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f'{variant}: total {total/rate:.2f}s', flush=True)


if __name__ == '__main__':
    main()
