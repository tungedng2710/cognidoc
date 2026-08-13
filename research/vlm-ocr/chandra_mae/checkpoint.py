from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch
import transformers
from accelerate import init_empty_weights
from huggingface_hub import hf_hub_download
from safetensors import safe_open
from safetensors.torch import load_file, save_file
from transformers import AutoConfig, AutoModel

VISION_PREFIXES = ("model.visual.", "visual.", "model.vision_tower.", "vision_tower.")


def _vision_from_config(config: Any) -> torch.nn.Module:
    """Construct the tower while silencing unrelated lazy-import doc errors."""
    previous_verbosity = transformers.logging.get_verbosity()
    transformers.logging.set_verbosity(60)  # Higher than logging.CRITICAL.
    try:
        return AutoModel.from_config(config)
    finally:
        transformers.logging.set_verbosity(previous_verbosity)


def _resolve_safetensors(
    model: str, revision: str | None, local_files_only: bool
) -> Path:
    local = Path(model).expanduser()
    if local.is_dir():
        candidates = sorted(local.glob("*.safetensors"))
        if len(candidates) == 1:
            return candidates[0]
        conventional = local / "model.safetensors"
        if conventional.is_file():
            return conventional
        raise FileNotFoundError(f"Expected one model.safetensors file in {local}")
    return Path(
        hf_hub_download(
            repo_id=model,
            filename="model.safetensors",
            revision=revision,
            local_files_only=local_files_only,
        )
    )


def load_chandra_vision(
    model: str,
    revision: str | None = None,
    local_files_only: bool = False,
    random_init: bool = False,
) -> tuple[torch.nn.Module, str | None]:
    full_config = AutoConfig.from_pretrained(
        model, revision=revision, local_files_only=local_files_only
    )
    config = getattr(full_config, "vision_config", full_config)
    if random_init:
        return _vision_from_config(config), None

    checkpoint = _resolve_safetensors(model, revision, local_files_only)
    with safe_open(checkpoint, framework="pt", device="cpu") as handle:
        names = list(handle.keys())
        prefix = next(
            (
                candidate
                for candidate in VISION_PREFIXES
                if any(name.startswith(candidate) for name in names)
            ),
            None,
        )
        if prefix is None:
            # Also accept a standalone save_pretrained vision checkpoint.
            prefix = "" if "patch_embed.proj.weight" in names else None
        if prefix is None:
            raise RuntimeError(
                f"Could not identify Chandra vision weights in {checkpoint}"
            )
        with init_empty_weights():
            vision = _vision_from_config(config)
        expected = set(vision.state_dict().keys())
        state = {
            name.removeprefix(prefix): handle.get_tensor(name)
            for name in names
            if name.startswith(prefix) and name.removeprefix(prefix) in expected
        }
    missing = expected - state.keys()
    if missing:
        raise RuntimeError(
            f"Vision checkpoint is missing {len(missing)} tensors; first: {sorted(missing)[:3]}"
        )
    incompatible = vision.load_state_dict(state, strict=True, assign=True)
    if incompatible.missing_keys or incompatible.unexpected_keys:
        raise RuntimeError(f"Vision checkpoint is incompatible: {incompatible}")
    return vision, prefix


def save_vision_delta(
    vision: torch.nn.Module,
    output_dir: str | Path,
    base_model: str,
    base_prefix: str = "model.visual.",
    metadata: dict[str, Any] | None = None,
) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    vision.save_pretrained(output / "vision_encoder", safe_serialization=True)
    delta_path = output / "chandra_vision_delta.safetensors"
    tensors = {
        base_prefix + name: value.detach().cpu().contiguous()
        for name, value in vision.state_dict().items()
    }
    save_file(
        tensors,
        delta_path,
        metadata={"base_model": base_model, "vision_prefix": base_prefix},
    )
    manifest = {
        "format": "chandra-vision-delta-v1",
        "base_model": base_model,
        "vision_prefix": base_prefix,
        "tensor_count": len(tensors),
        **(metadata or {}),
    }
    (output / "vision_delta_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    return delta_path


def apply_vision_delta(model: torch.nn.Module, delta_path: str | Path) -> None:
    """Strictly apply a prefixed vision delta to an already loaded full model."""
    state = load_file(str(delta_path), device="cpu")
    incompatible = model.load_state_dict(state, strict=False)
    if incompatible.unexpected_keys:
        raise RuntimeError(
            f"Unexpected vision delta keys: {incompatible.unexpected_keys[:5]}"
        )
    loaded = set(state)
    if not loaded:
        raise RuntimeError("Vision delta is empty")
