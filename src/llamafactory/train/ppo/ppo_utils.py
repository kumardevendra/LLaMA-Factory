import json
from typing import TYPE_CHECKING, Dict, List, Literal, Optional

import torch

from ...extras.packages import is_requests_available


if is_requests_available():
    import requests


if TYPE_CHECKING:
    from transformers import PreTrainedModel
    from trl import AutoModelForCausalLMWithValueHead


def get_rewards_from_server(server_url: str, messages: List[str]) -> List[torch.Tensor]:
    r"""
    Gets reward scores from the API server.
    """
    headers = {"Content-Type": "application/json"}
    payload = {"model": "model", "messages": messages}
    response = requests.post(server_url, json=payload, headers=headers)
    rewards = json.loads(response.text)["scores"]
    return torch.Tensor(rewards)


def replace_model(model: "AutoModelForCausalLMWithValueHead", target: Literal["default", "reward"]) -> None:
    r"""
    Replaces the default/reward modules in the model. The model is already unwrapped (and gathered).
    """
    if target == "reward":  # save default head temporarily
        setattr(model, "default_head_weight", model.v_head.summary.weight.data.detach().clone())
        setattr(model, "default_head_bias", model.v_head.summary.bias.data.detach().clone())

    model.pretrained_model.set_adapter(target)  # set the LoRA adapter to be active
    device = model.v_head.summary.weight.device
    model.v_head.summary.weight.data = model.get_buffer("{}_head_weight".format(target)).detach().clone().to(device)
    model.v_head.summary.bias.data = model.get_buffer("{}_head_bias".format(target)).detach().clone().to(device)


def dump_layernorm(model: "PreTrainedModel") -> Dict[str, torch.Tensor]:
    r"""
    Dumps the layernorm parameters in the model. The model is already unwrapped (and gathered).
    """
    layer_norm_params = {}
    for name, param in model.named_parameters():
        if param.data.dtype == torch.float32:
            layer_norm_params[name] = param.data.detach().clone()
            param.data = param.data.to(model.config.torch_dtype)

    return layer_norm_params


def restore_layernorm(model: "PreTrainedModel", layernorm_params: Optional[Dict[str, torch.Tensor]] = None) -> None:
    r"""
    Restores the layernorm parameters in the model. The model is already unwrapped (and gathered).
    """
    for name, param in model.named_parameters():
        if name in layernorm_params:
            param.data = layernorm_params[name]
