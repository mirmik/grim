"""Local VoxCPM2 comparison on the same reference and texts as Qwen / XTTS."""
import hashlib
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output'
QWEN = ROOT.parent / 'qwen-tts'
os.environ.setdefault('HF_HOME', str(ROOT / 'models'))
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('NUMBA_CACHE_DIR', str(OUT / 'numba-cache'))
os.environ.setdefault('MPLCONFIGDIR', str(OUT / 'mpl-cache'))
os.environ.setdefault('MODELSCOPE_CACHE', str(ROOT / 'models/modelscope'))

MODES = [
    dict(id='clone', title='Перенос голоса',
         description='Только образец голоса, без инструкции о манере речи.'),
    dict(id='calm', title='Спокойное объяснение',
         description='Тот же образец и инструкция о спокойной связной речи.',
         instruction='Calm explanatory tone, moderate pace, clear articulation and natural pauses.'),
    dict(id='continuation', title='Продолжение образца',
         description='Образец и его текст: перенос голоса вместе с манерой исходной записи.'),
]


def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--split-sentences', action='store_true')
    args = parser.parse_args()
    if args.split_sentences:
        OUT = OUT / 'sentences'
    import numpy as np
    import soundfile as sf
    import torch
    from transformers import set_seed
    from huggingface_hub import snapshot_download
    from voxcpm import VoxCPM
    OUT.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(8)
    assert torch.cuda.is_available()
    model_id = 'openbmb/VoxCPM2'
    revision = '32279effe8c19989596f05d353d1447f51d9e915'
    path = snapshot_download(model_id, revision=revision)
    started = time.monotonic()
    model = VoxCPM.from_pretrained(path, load_denoiser=False, optimize=False, device='cuda:0')
    torch.cuda.synchronize()
    report = dict(model=model_id, revision=revision, gpu=torch.cuda.get_device_name(),
                  load_seconds=time.monotonic()-started, optimize=False, modes=MODES,
                  chunking='sentence' if args.split_sentences else 'paragraph',
                  versions={p:importlib.metadata.version(p) for p in ['torch','torchaudio','torchcodec','transformers','voxcpm']}, samples=[])
    reference = Path.home() / 'project/for-tts-xtts/reference.wav'
    ref_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
    ref_text = (QWEN / 'reference.txt').read_text().strip()
    samples = {s['id']: s for s in json.loads((QWEN / 'samples.json').read_text())}
    settings = dict(cfg_value=2.0, inference_timesteps=10, max_len=700,
                    normalize=False, denoise=False, retry_badcase=False)
    for mode in MODES:
        for sample_id in ['beam', 'terms']:
            expected = samples[sample_id]['text']
            text = f'({mode["instruction"]}){expected}' if 'instruction' in mode else expected
            kwargs = dict(reference_wav_path=str(reference), **settings)
            if mode['id'] == 'continuation':
                kwargs.update(prompt_wav_path=str(reference), prompt_text=ref_text)
            spec = dict(model=model_id, revision=revision, mode=mode['id'], text=text,
                        expected=expected, seed=42, reference_sha256=ref_hash, parameters=kwargs)
            if args.split_sentences:
                spec.update(chunking='sentence', gap_seconds=.2)
            wav = OUT / f'{mode["id"]}-{sample_id}.wav'
            meta = wav.with_suffix('.json')
            previous = json.loads(meta.read_text()) if meta.exists() else {}
            if wav.exists() and previous.get('spec') == spec:
                record = previous
            else:
                torch.cuda.reset_peak_memory_stats()
                started = time.monotonic()
                sr = model.tts_model.sample_rate
                parts = re.split(r'(?<=[.!?])\s+', expected) if args.split_sentences else [expected]
                pieces, cues = [], []
                offset = 0
                for index, part in enumerate(parts):
                    set_seed(42)
                    part_text = f'({mode["instruction"]}){part}' if 'instruction' in mode else part
                    with torch.inference_mode():
                        result = model.generate(text=part_text, **kwargs)
                    torch.cuda.synchronize()
                    piece = np.asarray(result, dtype=np.float32).squeeze()
                    assert piece.ndim == 1 and len(piece) > sr/4 and np.isfinite(piece).all()
                    if args.split_sentences:
                        folder = OUT / 'chunks'
                        folder.mkdir(exist_ok=True)
                        chunk = folder / f'{mode["id"]}-{sample_id}-{index:02d}.wav'
                        sf.write(chunk, piece, sr, subtype='FLOAT')
                        cues.append(dict(text=part, file=str(chunk.relative_to(OUT)),
                                         start=offset/sr, end=(offset+len(piece))/sr,
                                         sha256=hashlib.sha256(chunk.read_bytes()).hexdigest()))
                        print(f'{chunk.name}: {len(piece)/sr:.2f}s', flush=True)
                    pieces.append(piece)
                    offset += len(piece)
                    if index < len(parts)-1:
                        gap = np.zeros(round(.2*sr), dtype=np.float32)
                        pieces.append(gap)
                        offset += len(gap)
                elapsed = time.monotonic() - started
                audio = np.concatenate(pieces)
                sf.write(wav, audio, sr, subtype='FLOAT')
                record = dict(spec=spec, file=wav.name, mode=mode['id'], sample=sample_id,
                              duration=len(audio)/sr, generation_seconds=elapsed, sample_rate=sr,
                              peak_vram_gib=torch.cuda.max_memory_allocated()/2**30,
                              sha256=hashlib.sha256(wav.read_bytes()).hexdigest())
                if args.split_sentences:
                    record['cues'] = cues
                meta.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            report['samples'].append(record)
            (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(f'{wav.name}: {record["duration"]:.2f}s audio, {record["generation_seconds"]:.2f}s generation', flush=True)


if __name__ == '__main__':
    main()
