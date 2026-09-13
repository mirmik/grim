"""Text-only Omni inference on a 32 GiB GPU, using Transformers 5.2.

Only Thinker's MoE expert matrices use NF4. Talker, Code2Wav, routers,
attention and embeddings remain BF16. Unused perception towers are omitted.
The original checkpoint stores experts as individual Linear weights; keeping
that layout allows bitsandbytes to quantize them without packing huge tensors.
"""
import gc
import json
import time
from collections import Counter
from pathlib import Path

import bitsandbytes as bnb
import torch
from accelerate import init_empty_weights
from accelerate.utils import set_module_tensor_to_device
from safetensors import safe_open
from torch import nn
from transformers import Qwen3OmniMoeConfig, Qwen3OmniMoeForConditionalGeneration
from transformers.activations import ACT2FN

ROOT = Path(__file__).resolve().parent
OMITTED = ("thinker.audio_tower.", "thinker.visual.")


class Expert(nn.Module):
    def __init__(self, hidden, intermediate, activation):
        super().__init__()
        self.gate_proj = nn.Linear(hidden, intermediate, bias=False)
        self.up_proj = nn.Linear(hidden, intermediate, bias=False)
        self.down_proj = nn.Linear(intermediate, hidden, bias=False)
        self.act_fn = activation

    def forward(self, hidden):
        return self.down_proj(self.act_fn(self.gate_proj(hidden)) * self.up_proj(hidden))


class UnpackedExperts(nn.ModuleList):
    """Same routing and accumulation as the official eager Experts.forward."""
    def __init__(self, count, hidden, intermediate, activation):
        super().__init__([Expert(hidden, intermediate, activation) for _ in range(count)])

    def forward(self, hidden_states, top_k_index, top_k_weights):
        final = torch.zeros_like(hidden_states)
        with torch.no_grad():
            mask = torch.nn.functional.one_hot(top_k_index, num_classes=len(self)).permute(2, 1, 0)
            hits = torch.greater(mask.sum(dim=(-1, -2)), 0).nonzero().flatten().tolist()
        for expert_idx in hits:
            top_k_pos, token_idx = torch.where(mask[expert_idx])
            current = self[expert_idx](hidden_states[token_idx])
            current = current * top_k_weights[token_idx, top_k_pos, None]
            final.index_add_(0, token_idx, current.to(final.dtype))
        return final


class UnusedPerception(nn.Module):
    def forward(self, *args, **kwargs):
        raise RuntimeError("This experiment loads text input only; perception weights were omitted")


def build_empty(config):
    # Actual CPU buffers (rotary frequencies, codec offsets) must survive.
    with init_empty_weights(include_buffers=False):
        model = Qwen3OmniMoeForConditionalGeneration._from_config(
            config, dtype=torch.bfloat16, attn_implementation="sdpa"
        )
        model.thinker.audio_tower = UnusedPerception()
        model.thinker.visual = UnusedPerception()
        for branch in (model.thinker.model, model.talker.model):
            for layer in branch.layers:
                old = layer.mlp.experts
                layer.mlp.experts = UnpackedExperts(
                    old.num_experts, old.hidden_dim, old.intermediate_dim, old.act_fn
                )
    return model


def load_model(snapshot, output_dir):
    start = time.perf_counter()
    config = Qwen3OmniMoeConfig.from_pretrained(snapshot, local_files_only=True)
    model = build_empty(config)
    index = json.loads((snapshot / "model.safetensors.index.json").read_text())["weight_map"]
    wanted = {key for key in index if not key.startswith(OMITTED)}
    actual = set(model.state_dict())
    assert actual == wanted, {"missing": sorted(wanted-actual)[:20], "extra": sorted(actual-wanted)[:20]}
    counts = Counter()
    for name, param in model.named_parameters():
        group = "thinker_experts_nf4" if name.startswith("thinker.model.") and ".experts." in name else name.split(".")[0] + "_bf16"
        counts[group] += param.numel()
    print("Parameter counts:", dict(counts), flush=True)

    quantized = set()
    for name, module in list(model.thinker.model.named_modules()):
        if isinstance(module, nn.Linear) and ".experts." in name:
            full_name = "thinker.model." + name
            with torch.device("meta"):
                replacement = bnb.nn.Linear4bit(
                    module.in_features, module.out_features, bias=False,
                    compute_dtype=torch.bfloat16, compress_statistics=True, quant_type="nf4"
                )
            model.set_submodule(full_name, replacement)
            quantized.add(full_name + ".weight")

    loaded = set()
    shards = sorted(set(index.values()))
    for shard_idx, shard in enumerate(shards):
        with safe_open(snapshot / shard, framework="pt", device="cpu") as handle:
            for name in handle.keys():
                if name not in wanted:
                    continue
                tensor = handle.get_tensor(name)
                if name in quantized:
                    module = model.get_submodule(name.rsplit(".", 1)[0])
                    module.weight = bnb.nn.Params4bit(
                        tensor, requires_grad=False, compress_statistics=True,
                        quant_type="nf4", module=module
                    ).to("cuda")
                else:
                    set_module_tensor_to_device(model, name, "cuda", value=tensor, dtype=torch.bfloat16)
                loaded.add(name)
                del tensor
        gc.collect()
        torch.cuda.empty_cache()
        print(f"Loaded {shard_idx+1}/{len(shards)} shards; GPU allocated {torch.cuda.memory_allocated()/2**30:.2f} GiB", flush=True)
    assert loaded == wanted
    for name, buffer in list(model.named_buffers()):
        assert not buffer.is_meta, name
        set_module_tensor_to_device(model, name, "cuda", value=buffer)
    assert all(not p.is_meta for p in model.parameters())
    model.eval().requires_grad_(False)
    report = {
        "load_seconds": time.perf_counter()-start,
        "parameter_counts": dict(counts), "quantized_matrices": len(quantized),
        "loaded_tensors": len(loaded), "omitted_prefixes": list(OMITTED),
        "gpu_allocated_gib": torch.cuda.memory_allocated()/2**30,
        "gpu_reserved_gib": torch.cuda.memory_reserved()/2**30,
        "quantization": "Thinker MoE experts NF4, double quant; all other loaded weights BF16",
    }
    (output_dir / "loading.json").write_text(json.dumps(report, indent=2))
    return model
