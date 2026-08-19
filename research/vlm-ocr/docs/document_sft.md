# Benchmarking and Document SFT

After MAE and merger alignment, first compare complete-model generation on a
held-out set. Only start document SFT after the aligned model improves over the
MAE-only model and remains competitive with original Chandra.

## 1. Benchmark alignment

Copy the example and set `dataset` to the paired dataset root:

```bash
cp docs/benchmark_alignment_example.yaml configs/benchmark_alignment_local.yaml
```

The benchmark loads one Chandra model and evaluates these states sequentially:

1. Original Chandra.
2. Original Chandra plus the MAE vision delta.
3. MAE vision delta plus the alignment merger delta.

Run it on one GPU:

```bash
conda activate tungn197
CUDA_VISIBLE_DEVICES=0 python benchmark_alignment.py \
  --config configs/benchmark_alignment_local.yaml
```

For a quick smoke test, add `--max-samples 4 --max-new-tokens 2048`.

Outputs are written beneath `outputs/chandra2-alignment-benchmark`:

- `base.jsonl`, `mae.jsonl`, and `aligned.jsonl`: per-example predictions.
- `summary.json`: JSON validity, exact match, normalized edit similarity, and
  micro field precision/recall/F1.

Use a held-out dataset that was not used to tune alignment hyperparameters.
Inspect predictions manually in addition to aggregate metrics.

## 2. Train document SFT

SFT uses the same paired layout:

```text
sft_dataset/
├── images/
│   └── example.png
└── labels/
    └── example.json
```

Copy and edit the configuration:

```bash
cp docs/sft_example.yaml configs/sft_local.yaml
```

The default policy loads base Chandra, then the MAE vision delta, then the
alignment merger delta. It freezes the vision encoder, trains the merger, and
adds LoRA to the Qwen 3.5 language projections. Loss is applied only to the
assistant JSON response.

Run two steps before a full job:

```bash
CUDA_VISIBLE_DEVICES=0 accelerate launch \
  --num_processes 1 \
  --num_machines 1 \
  --mixed_precision bf16 \
  --dynamo_backend no \
  train_sft.py \
  --config configs/sft_local.yaml \
  --max-steps 2 \
  --gradient-accumulation-steps 1 \
  --eval-every 2 \
  --save-every 2
```

Then run the configured schedule:

```bash
CUDA_VISIBLE_DEVICES=0 accelerate launch \
  --num_processes 1 \
  --num_machines 1 \
  --mixed_precision bf16 \
  --dynamo_backend no \
  train_sft.py --config configs/sft_local.yaml
```

Resume from a full training checkpoint:

```bash
accelerate launch train_sft.py \
  --config configs/sft_local.yaml \
  --resume-from outputs/chandra2-sft/checkpoints/step-250
```

Final outputs include:

- `lora_adapter/`: language-model LoRA adapter.
- `sft_merger_delta.safetensors`: final merger weights.
- `sft_manifest.json`: exact parent checkpoints and loading metadata.
- `processor/`: processor and tokenizer files.

## 3. Load the final SFT model

```python
import torch
from peft import PeftModel
from transformers import AutoModelForImageTextToText

from chandra_mae.checkpoint import apply_vision_delta

model = AutoModelForImageTextToText.from_pretrained(
    "datalab-to/chandra-ocr-2",
    dtype=torch.bfloat16,
)
apply_vision_delta(
    model, "outputs/chandra2-mae-full/chandra_vision_delta.safetensors"
)
apply_vision_delta(
    model, "outputs/chandra2-alignment/alignment_merger_delta.safetensors"
)
apply_vision_delta(model, "outputs/chandra2-sft/sft_merger_delta.safetensors")
model = PeftModel.from_pretrained(model, "outputs/chandra2-sft/lora_adapter")
```

## 4. Train the fair baseline

Use the identical SFT dataset and settings but initialize from original Chandra:

```bash
accelerate launch train_sft.py \
  --config configs/sft_local.yaml \
  --no-load-adapted-vision \
  --output-dir outputs/chandra2-direct-sft
```

The important comparison is aligned-MAE SFT versus direct SFT, not their raw
training losses. Evaluate both using the same generation benchmark and held-out
documents.
