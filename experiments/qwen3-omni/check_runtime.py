"""Verify the unpacked expert layout against Transformers' reference forward."""
from types import SimpleNamespace
import torch
from transformers.models.qwen3_omni_moe.modeling_qwen3_omni_moe import Qwen3OmniMoeThinkerTextExperts
from runtime import UnpackedExperts

torch.manual_seed(42)
config = SimpleNamespace(num_experts=4, hidden_size=16, moe_intermediate_size=8, hidden_act="silu", _experts_implementation="eager")
packed = Qwen3OmniMoeThinkerTextExperts(config)
unpacked = UnpackedExperts(4, 16, 8, packed.act_fn)
with torch.no_grad():
    packed.gate_up_proj.normal_(0, 0.1)
    packed.down_proj.normal_(0, 0.1)
    for i, expert in enumerate(unpacked):
        expert.gate_proj.weight.copy_(packed.gate_up_proj[i, :8])
        expert.up_proj.weight.copy_(packed.gate_up_proj[i, 8:])
        expert.down_proj.weight.copy_(packed.down_proj[i])
    x = torch.randn(7, 16)
    weights, indices = torch.rand(7, 4).topk(2, dim=-1)
    weights /= weights.sum(-1, keepdim=True)
    reference = packed(x, indices, weights)
    actual = unpacked(x, indices, weights)
    torch.testing.assert_close(actual, reference, rtol=1e-5, atol=1e-7)
print("Expert layout agrees with the official eager implementation.")
