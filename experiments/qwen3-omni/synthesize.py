"""Compare verbatim reading with context-guided reading of the same scene."""
import argparse
import gc
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(ROOT / "models"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

import numpy as np
import soundfile as sf
import torch
import transformers
from transformers import AutoTokenizer, set_seed
from runtime import load_model

SYSTEM = "You are Qwen, a virtual human developed by the Qwen Team, Alibaba Group, capable of perceiving auditory and visual inputs, as well as generating text and speech."
CONTEXT = (
    "Ты озвучиваешь на русском языке учебную анимацию к главе «Как поверхность изгибается». "
    "Слушатель — студент, который впервые знакомится с дифференциальной геометрией. "
    "На экране плоскость пересекает поверхность-чашу; при вращении плоскости сечение меняется. "
    "Объясняй спокойно, заинтересованно и естественно, как преподаватель, который понимает рисунок. "
    "Не торопись. Связывай предложения общей мыслью, делай короткие смысловые паузы. "
    "Выдели голосом противопоставление «в одном направлении» и «в другом». "
)


def normalized(text):
    return re.findall(r"[\w]+", text.lower().replace("ё", "е"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", nargs="+", default=["neutral", "context"])
    parser.add_argument("--speaker", default="Ethan")
    parser.add_argument("--scene", default="section")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    spec = json.loads((ROOT / "model.json").read_text())
    snapshot = ROOT / "models/hub/models--Qwen--Qwen3-Omni-30B-A3B-Instruct/snapshots" / spec["revision"]
    scenes = json.loads((ROOT.parent / "surface-bending-manim/script.json").read_text())
    scene = next(item for item in scenes if item["id"] == args.scene)
    speech = " ".join(scene["speech"])
    if args.smoke:
        speech = "На плоскости стрелка сохраняет направление. На цилиндре она поворачивается."
    # The test has no image/audio/video input; the official tokenizer is enough.
    # Loading a multimodal processor would need an unused torchvision runtime.
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
    tokenizer.chat_template = json.loads((snapshot / "chat_template.json").read_text())["chat_template"]
    tokenizer.apply_chat_template([
        {"role": "user", "content": [{"type": "text", "text": "Проверка."}]}
    ], add_generation_prompt=True, tokenize=False)
    torch.set_num_threads(6)
    model = load_model(snapshot, out)

    # Preserve the Thinker's answer even if a later audio stage fails.
    original_generate = model.thinker.generate
    active = {}

    def logged_thinker(*pos, **kwargs):
        started = time.perf_counter()
        result = original_generate(*pos, **kwargs)
        active["thinker_seconds"] = time.perf_counter() - started
        active["generated_text"] = tokenizer.decode(
            result.sequences[0, active["prompt_tokens"]:], skip_special_tokens=True
        )
        print("Thinker answer:", active["generated_text"], flush=True)
        (out / (active["id"] + ".json")).write_text(json.dumps(active, ensure_ascii=False, indent=2))
        return result

    model.thinker.generate = logged_thinker
    for variant in args.variants:
        if variant not in ("neutral", "context"):
            raise ValueError(variant)
        name = f"{'smoke' if args.smoke else args.scene}-{args.speaker.lower()}-{variant}"
        if (out / (name + ".wav")).exists():
            print("Already generated:", name, flush=True)
            continue
        instruction = "Прочитай вслух следующий текст дословно, без вступления, комментариев, добавлений и изменений. В ответе должен быть только этот текст."
        prompt = (CONTEXT if variant == "context" else "") + instruction + "\n\nТекст для озвучки:\n" + speech
        conversation = [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM}]},
            {"role": "user", "content": [{"type": "text", "text": prompt}]},
        ]
        chat = tokenizer.apply_chat_template(conversation, add_generation_prompt=True, tokenize=False)
        inputs = tokenizer(chat, return_tensors="pt", padding=True).to("cuda")
        active.clear()
        active.update({
            "id": name, "model": spec, "scene": args.scene, "variant": variant,
            "speaker": args.speaker, "seed": 42, "source_text": speech,
            "conversation": conversation, "prompt_tokens": inputs.input_ids.shape[-1],
            "torch": torch.__version__, "transformers": transformers.__version__,
            "talker_temperature": 0.9, "talker_top_k": 50, "talker_top_p": 1.0,
            "talker_repetition_penalty": 1.05,
        })
        print("Generating", name, flush=True)
        set_seed(42)
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        with torch.inference_mode():
            text_ids, audio = model.generate(
                **inputs, speaker=args.speaker, return_audio=True,
                thinker_do_sample=False, thinker_max_new_tokens=512,
                talker_max_new_tokens=400 if args.smoke else 1600,
            )
        torch.cuda.synchronize()
        active["generation_seconds"] = time.perf_counter() - started
        samples = audio.reshape(-1).float().cpu().numpy()
        assert len(samples) and np.isfinite(samples).all()
        sf.write(out / (name + ".wav"), samples, 24000, subtype="PCM_16")
        active.update({
            "wav": name + ".wav", "sample_rate": 24000,
            "duration_seconds": len(samples)/24000,
            "text_matches_source": normalized(active["generated_text"]) == normalized(speech),
            "peak_amplitude": float(np.abs(samples).max()),
            "gpu_peak_allocated_gib": torch.cuda.max_memory_allocated()/2**30,
            "gpu_peak_reserved_gib": torch.cuda.max_memory_reserved()/2**30,
        })
        (out / (name + ".json")).write_text(json.dumps(active, ensure_ascii=False, indent=2))
        print(json.dumps({k: active[k] for k in ["id", "duration_seconds", "generation_seconds", "text_matches_source", "gpu_peak_allocated_gib"]}, ensure_ascii=False), flush=True)
        del audio, text_ids, inputs, samples
        gc.collect()
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
