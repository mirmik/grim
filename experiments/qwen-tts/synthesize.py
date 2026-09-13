"""Unedited, seeded local voice-cloning samples for Qwen / XTTS comparison."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(ROOT / "models"))
os.environ.setdefault("NUMBA_CACHE_DIR", str(ROOT / "output/numba-cache"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["qwen", "xtts"], default="qwen")
    parser.add_argument("--reference", type=Path, default=Path.home() / "project/for-tts-xtts/reference.wav")
    parser.add_argument("--sample", nargs="*")
    args = parser.parse_args()
    import numpy as np
    import soundfile as sf
    import torch
    from transformers import set_seed

    torch.set_num_threads(8)
    assert torch.cuda.is_available(), "This experiment expects a CUDA GPU"
    out = ROOT / "output" / args.engine
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    if args.engine == "qwen":
        from qwen_tts import Qwen3TTSModel
        from huggingface_hub import snapshot_download
        model_id = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
        revision = "fd4b254389122332181a7c3db7f27e918eec64e3"
        model_path = snapshot_download(model_id, revision=revision)
        model = Qwen3TTSModel.from_pretrained(model_path, device_map="cuda:0", dtype=torch.bfloat16, attn_implementation="sdpa")
        prompt = model.create_voice_clone_prompt(ref_audio=str(args.reference), ref_text=(ROOT / "reference.txt").read_text().strip())
        settings = dict(model.generate_defaults, non_streaming_mode=True, max_new_tokens=1600)

        def generate(text):
            waves, sr = model.generate_voice_clone(text=text, language="Russian", voice_clone_prompt=prompt, **settings)
            return waves[0], sr
    else:
        import torchaudio
        original_load = torch.load
        torch.load = lambda *a, **kw: original_load(*a, **{**kw, "weights_only": False})

        def load_audio(path, **kwargs):
            data, sr = sf.read(path, dtype="float32", always_2d=True)
            return torch.from_numpy(data.T), sr
        torchaudio.load = load_audio
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts
        model_dir = Path.home() / ".local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2"
        model_id = str(model_dir)
        config = XttsConfig()
        config.load_json(str(model_dir / "config.json"))
        model = Xtts.init_from_config(config)
        model.load_checkpoint(config, checkpoint_dir=str(model_dir), use_deepspeed=False)
        model.to("cuda")
        cond, speaker = model.get_conditioning_latents(audio_path=[str(args.reference)])
        settings = dict(temperature=.60, speed=1.0, enable_text_splitting=True)

        def generate(text):
            result = model.inference(text=text, language="ru", gpt_cond_latent=cond, speaker_embedding=speaker, **settings)
            return result["wav"], 24000
        revision = None
    torch.cuda.synchronize()
    load_seconds = time.monotonic() - started
    print(f"Model and reference ready in {load_seconds:.1f}s", flush=True)
    package_names = ["torch", "transformers", "qwen-tts" if args.engine == "qwen" else "TTS"]
    report = dict(engine=args.engine, model=model_id, revision=revision,
                  gpu=torch.cuda.get_device_name(), load_seconds=load_seconds,
                  versions={p: importlib.metadata.version(p) for p in package_names},
                  reference_sha256=hashlib.sha256(args.reference.read_bytes()).hexdigest(),
                  settings=settings, samples=[])
    report_path = out / "report.json"
    if report_path.exists():
        report["samples"] = json.loads(report_path.read_text())["samples"]
    for item in json.loads((ROOT / "samples.json").read_text()):
        if args.sample and item["id"] not in args.sample:
            continue
        for seed in item["seeds"]:
            name = f"{item['id']}-{seed}.wav"
            if (out / name).exists():
                print(f"Exists: {name}", flush=True)
                continue
            set_seed(seed)
            torch.cuda.reset_peak_memory_stats()
            t0 = time.monotonic()
            with torch.inference_mode():
                wave, sr = generate(item["text"])
            torch.cuda.synchronize()
            elapsed = time.monotonic() - t0
            wave = np.asarray(wave, dtype=np.float32).squeeze()
            assert wave.ndim == 1 and len(wave) > sr and np.isfinite(wave).all()
            sf.write(out / name, wave, sr, subtype="FLOAT")
            record = dict(id=item["id"], file=name, text=item["text"], seed=seed,
                          duration=len(wave)/sr, generation_seconds=elapsed,
                          real_time_factor=elapsed/(len(wave)/sr), sample_rate=sr,
                          peak_vram_gib=torch.cuda.max_memory_allocated()/2**30)
            report["samples"].append(record)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(json.dumps(record, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
