"""
Export GraphTATR with a dummy image input for Netron visualization.

TorchScript is the default because the implemented graph builder contains
dynamic edge construction that is not always portable to ONNX.
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
if DETR_DIR not in sys.path:
    sys.path.insert(0, DETR_DIR)

from models import build_graph_model


DEFAULT_CONFIG_PATH = os.path.join(THIS_DIR, "graph_tatr_config.json")
DEFAULT_OUTPUT_PATH = os.path.abspath(
    os.path.join(THIS_DIR, "../artifacts/graph_tatr_dummy_torchscript.pt")
)


class NetronGraphTATRWrapper(nn.Module):
    """Return tensors instead of a dict so trace/export stays simple."""

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
    has_graph_keys = any(
        key.startswith("base.") or key.startswith("gnn_layers.") or key.startswith("refined_")
        for key in state_dict.keys()
    )

    for key, value in state_dict.items():
        if not torch.is_tensor(value):
            continue
        if key in model_state and model_state[key].shape == value.shape:
            mapped_state[key] = value
            continue

        if not has_graph_keys:
            base_key = f"base.{key}"
            if base_key in model_state and model_state[base_key].shape == value.shape:
                mapped_state[base_key] = value
            if key.startswith("class_embed."):
                refined_key = "refined_class_embed." + key[len("class_embed."):]
                if refined_key in model_state and model_state[refined_key].shape == value.shape:
                    mapped_state[refined_key] = value
            elif key.startswith("bbox_embed."):
                refined_key = "refined_bbox_embed." + key[len("bbox_embed."):]
                if refined_key in model_state and model_state[refined_key].shape == value.shape:
                    mapped_state[refined_key] = value

    model_state.update(mapped_state)
    model.load_state_dict(model_state, strict=True)
    print(f"Loaded {len(mapped_state)} tensors from {checkpoint_path}")


def build_dummy_input(batch_size, height, width, device):
    return torch.randn(batch_size, 3, height, width, device=device)


def export_torchscript(wrapper, dummy_input, output_path):
    traced = torch.jit.trace(wrapper, dummy_input, strict=False)
    traced.save(output_path)


def export_onnx(wrapper, dummy_input, output_path, opset):
    torch.onnx.export(
        wrapper,
        dummy_input,
        output_path,
        input_names=["images"],
        output_names=["pred_logits", "pred_boxes"],
        opset_version=opset,
        do_constant_folding=True,
    )


def get_args():
    parser = argparse.ArgumentParser("Export GraphTATR for Netron")
    parser.add_argument("--config_file", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--checkpoint", default=None, help="Optional GraphTATR or baseline TATR checkpoint")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--format", choices=["torchscript", "onnx"], default="torchscript")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--opset", type=int, default=17)
    return parser.parse_args()


def main():
    args = get_args()
    device = torch.device(args.device)
    config = load_config(args.config_file, args.device)

    model, _, _ = build_graph_model(config)
    model.to(device)
    model.eval()
    if args.checkpoint:
        load_checkpoint(model, args.checkpoint, device)

    wrapper = NetronGraphTATRWrapper(model).to(device).eval()
    dummy_input = build_dummy_input(args.batch_size, args.height, args.width, device)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with torch.no_grad():
        pred_logits, pred_boxes = wrapper(dummy_input)
    print("Dummy input:", tuple(dummy_input.shape))
    print("pred_logits:", tuple(pred_logits.shape))
    print("pred_boxes:", tuple(pred_boxes.shape))

    if args.format == "torchscript":
        export_torchscript(wrapper, dummy_input, args.output)
    else:
        export_onnx(wrapper, dummy_input, args.output, args.opset)
    print("Saved Netron model:", os.path.abspath(args.output))


if __name__ == "__main__":
    main()
