"""
Export AuxGraphTATR image-only inference path as a TorchScript .pth file.

The saved file is intended for model visualization tools such as Netron. It
traces only the deployable Table Transformer path; the auxiliary graph branch is
training-only and is not required for inference.
"""
import argparse
import json
import os
import sys
from types import SimpleNamespace

import torch
from torch import nn


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DETR_DIR = os.path.abspath(os.path.join(THIS_DIR, "../detr"))
if THIS_DIR in sys.path:
    sys.path.remove(THIS_DIR)
sys.path.insert(0, THIS_DIR)
if DETR_DIR not in sys.path:
    sys.path.insert(1, DETR_DIR)

from models import build_aux_graph_model


DEFAULT_CONFIG_PATH = os.path.join(THIS_DIR, "aux_graph_tatr_config.json")
DEFAULT_OUTPUT_PATH = os.path.abspath(
    os.path.join(THIS_DIR, "../artifacts/aux_graph_tatr_image_only_torchscript.pth")
)


class AuxGraphTATRInferenceWrapper(nn.Module):
    """Return tensors instead of a dict so traced exports are easy to inspect."""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, images):
        outputs = self.model(images)
        return outputs["pred_logits"], outputs["pred_boxes"]


def load_config(config_file, device):
    with open(config_file, "rb") as infile:
        config = json.load(infile)
    config["device"] = device
    config["masks"] = False
    return SimpleNamespace(**config)


def clean_state_dict_keys(state_dict):
    cleaned = {}
    for key, value in state_dict.items():
        if key.startswith("module."):
            key = key[len("module."):]
        cleaned[key] = value
    return cleaned


def extract_model_state(checkpoint):
    if isinstance(checkpoint, dict):
        if "model_state_dict" in checkpoint:
            return checkpoint["model_state_dict"]
        if "model" in checkpoint:
            return checkpoint["model"]
    return checkpoint


def load_checkpoint(model, checkpoint_path, device):
    checkpoint = torch.load(checkpoint_path, map_location=device)
    state_dict = clean_state_dict_keys(extract_model_state(checkpoint))
    model_state = model.state_dict()
    mapped_state = {}
    has_aux_graph_keys = any(
        key.startswith("base.")
        or key.startswith("graph_node_encoder.")
        or key.startswith("graph_layers.")
        or key.startswith("relation_head.")
        or key.startswith("visual_distill_proj.")
        or key.startswith("graph_distill_proj.")
        for key in state_dict.keys()
    )

    for key, value in state_dict.items():
        if not torch.is_tensor(value):
            continue
        if key in model_state and model_state[key].shape == value.shape:
            mapped_state[key] = value
            continue
        if not has_aux_graph_keys:
            base_key = f"base.{key}"
            if base_key in model_state and model_state[base_key].shape == value.shape:
                mapped_state[base_key] = value

    model_state.update(mapped_state)
    model.load_state_dict(model_state, strict=True)
    print(f"Loaded {len(mapped_state)} tensors from {checkpoint_path}")


def build_dummy_input(batch_size, height, width, device):
    return torch.randn(batch_size, 3, height, width, device=device)


def get_args():
    parser = argparse.ArgumentParser("Export AuxGraphTATR .pth for visualization")
    parser.add_argument("--config_file", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--checkpoint", default=None, help="Optional AuxGraphTATR or baseline TATR checkpoint")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--width", type=int, default=256)
    return parser.parse_args()


def main():
    args = get_args()
    device = torch.device(args.device)
    config = load_config(args.config_file, args.device)

    model, _, _ = build_aux_graph_model(config)
    model.to(device)
    model.eval()
    if args.checkpoint:
        load_checkpoint(model, args.checkpoint, device)

    wrapper = AuxGraphTATRInferenceWrapper(model).to(device).eval()
    dummy_input = build_dummy_input(args.batch_size, args.height, args.width, device)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with torch.no_grad():
        pred_logits, pred_boxes = wrapper(dummy_input)
    print("Dummy input:", tuple(dummy_input.shape))
    print("pred_logits:", tuple(pred_logits.shape))
    print("pred_boxes:", tuple(pred_boxes.shape))

    traced = torch.jit.trace(wrapper, dummy_input, strict=False)
    traced.save(args.output)
    print("Saved TorchScript .pth:", os.path.abspath(args.output))


if __name__ == "__main__":
    main()
