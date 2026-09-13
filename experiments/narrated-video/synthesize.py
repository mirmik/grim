"""Generate narration using the user's existing XTTS installation and reference."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("NUMBA_CACHE_DIR", str(ROOT / "output" / "numba-cache"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xtts-root", type=Path, default=Path.home() / "project/for-tts-xtts")
    parser.add_argument("--model-dir", type=Path, default=Path.home() / ".local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2")
    args = parser.parse_args()
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio
    # Compatibility adapters already used by for-tts-xtts/tts_service.py.
    original_load = torch.load
    torch.load = lambda *a, **kw: original_load(*a, **{**kw, "weights_only": False})
    def soundfile_load(path, **kwargs):
        audio, rate = sf.read(path, dtype="float32", always_2d=True)
        return torch.from_numpy(audio.T), rate
    torchaudio.load = soundfile_load
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    config = XttsConfig()
    config.load_json(str(args.model_dir / "config.json"))
    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=str(args.model_dir), use_deepspeed=False)
    model.to("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:", next(model.parameters()).device, flush=True)
    reference = args.xtts_root / "reference.wav"
    conditioning, speaker = model.get_conditioning_latents(audio_path=[str(reference)])
    script = json.loads((ROOT / "script.json").read_text())
    seed, rate = 42, 24000
    torch.manual_seed(seed)
    fingerprint = hashlib.sha256(reference.read_bytes()).hexdigest()
    timeline, pieces, cursor = [], [], 0
    for index, scene in enumerate(script):
        wav_path = output / f"{index:02d}-{scene['id']}.wav"
        cache_path = wav_path.with_suffix(".json")
        spec = {"text": scene["text"], "reference_sha256": fingerprint, "model_dir": str(args.model_dir), "temperature": 0.65, "speed": 1.0, "seed": seed + index}
        if wav_path.exists() and cache_path.exists() and json.loads(cache_path.read_text()) == spec:
            audio, sr = sf.read(wav_path, dtype="float32")
            assert sr == rate
        else:
            started = time.monotonic()
            torch.manual_seed(seed + index)
            with torch.inference_mode():
                result = model.inference(text=scene["text"], language="ru", gpt_cond_latent=conditioning, speaker_embedding=speaker, temperature=0.65, speed=1.0, enable_text_splitting=True)
            audio = np.asarray(result["wav"], dtype=np.float32).squeeze()
            assert audio.ndim == 1 and np.isfinite(audio).all() and len(audio) > rate
            # Keep a small natural margin, removing long model-generated edge silence.
            audible = np.flatnonzero(np.abs(audio) > 0.006)
            if len(audible):
                audio = audio[max(0, audible[0] - 2400):min(len(audio), audible[-1] + 3600)]
            fade = min(240, len(audio)//2)
            audio[:fade] *= np.linspace(0, 1, fade)
            audio[-fade:] *= np.linspace(1, 0, fade)
            sf.write(wav_path, audio, rate, subtype="PCM_16")
            cache_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2))
            print(f"{scene['id']}: {len(audio)/rate:.1f}s audio, {time.monotonic()-started:.1f}s generation", flush=True)
        lead, tail = 0.35, 0.8 if index < len(script)-1 else 1.5
        duration = lead + len(audio)/rate + tail
        timeline.append({**scene, "start": cursor, "speech_start": cursor+lead, "speech_end": cursor+lead+len(audio)/rate, "end": cursor+duration})
        pieces.extend([np.zeros(round(lead*rate), dtype=np.float32), audio, np.zeros(round(tail*rate), dtype=np.float32)])
        cursor += duration
    sf.write(output / "narration.wav", np.concatenate(pieces), rate, subtype="PCM_16")
    (output / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2))
    print(f"Total duration: {cursor:.2f}s", flush=True)

if __name__ == "__main__":
    main()
