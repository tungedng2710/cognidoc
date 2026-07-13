# Table Recognition With Reasoning

This guide describes how `finetune_table_with_reasoning.py` fine-tunes
`unsloth/Qwen3.5-4B` for table-image recognition with a visible reasoning
trace and structural HTML output.

## Dataset

The default Hugging Face dataset is:

```text
tungedng2710/table_html_with_reasoning
```

It contains 1,000 rows in a single `train` split with these columns:

| Column | Description |
| --- | --- |
| `id` | Unique sample identifier |
| `images` | One or more table images |
| `table_html` | Reasoning trace followed by structural table HTML |
| `has_reasoning` | Whether the target contains a reasoning trace |
| `num_images` | Number of images in the sample |

Every current target uses this response format:

```text
<think>
Reasoning about the table layout, headers, spans, rows, and cells.
</think>
<table>
...
</table>
```

The script validates that every selected row:

- Contains at least one image.
- Has a matching `num_images` value.
- Has `has_reasoning=true`.
- Contains `<think>...</think>` and complete `<table>...</table>` tags.

Because the dataset only provides a `train` split, the script creates a
deterministic 90/10 train/evaluation split using seed `3407`. This produces 900
training examples and 100 evaluation examples by default.

## Training Method

Each row is converted to a multimodal Qwen conversation. The user message
contains the table-recognition instruction and all images. The assistant
message contains the complete target from `table_html`, including both the
reasoning trace and final HTML.

The instruction asks the model to:

- Analyze the table structure before generating HTML.
- Put its structural reasoning inside `<think>...</think>`.
- Preserve visible text, empty cells, row and column order.
- Preserve `rowspan` and `colspan` attributes.
- Return the final table inside `<table>...</table>` without Markdown fences.

Training uses supervised fine-tuning with `SFTTrainer` and
`UnslothVisionDataCollator`. Loss is calculated only on the assistant response,
not on the user instruction or image placeholders.

The model is loaded in 16-bit precision. LoRA adapters are attached to all
linear attention and MLP modules, with both vision and language layers enabled
by default. The base embedding and language-model output layers remain frozen.

Default LoRA settings:

| Setting | Value |
| --- | ---: |
| Rank | 16 |
| Alpha | 16 |
| Dropout | 0 |
| Target modules | All linear modules |
| Vision layers | Enabled |
| Language layers | Enabled |

The default sequence length is `20480`. Dataset inspection found a median
target length of approximately 7,485 tokens and a maximum of approximately
17,706 tokens before image and chat tokens. A 4,096-token context would
truncate 996 of the 1,000 current targets.

Default training settings:

| Setting | Value |
| --- | ---: |
| Epochs | 3 |
| Train batch size per device | 1 |
| Evaluation batch size per device | 1 |
| Gradient accumulation | 8 |
| Effective batch size on one GPU | 8 |
| Learning rate | `1e-4` |
| Warmup ratio | `0.03` |
| Scheduler | Linear |
| Optimizer | `adamw_torch_fused` |
| Weight decay | `0.01` |
| Maximum gradient norm | `0.3` |
| Evaluation interval | 100 steps |
| Checkpoint interval | 100 steps |
| Saved checkpoint limit | 3 |

Gradient checkpointing is enabled through Unsloth to reduce activation memory.
Dataset packing is disabled because the inputs are multimodal.

## Environment

Activate the project Conda environment before running any command:

```bash
conda activate tungn197
cd /root/tungn197/cognidoc/research/VLM
```

The current environment stores the CUDA 13 `nvJitLink` library outside the
default dynamic linker path. Export it before importing Unsloth:

```bash
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib/python3.13/site-packages/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}"
```

Optionally choose a GPU:

```bash
export CUDA_VISIBLE_DEVICES=0
```

## Validate The Dataset

Run the complete dataset and conversation-format validation without loading the
model:

```bash
python finetune_table_with_reasoning.py --dry-run
```

Expected summary:

```json
{
  "train_rows": 900,
  "eval_rows": 100,
  "image_counts": [1],
  "target_characters": {
    "min": 7071,
    "median": 14748,
    "max": 32670
  },
  "max_seq_length": 20480
}
```

## Run Training

Start training with the default configuration:

```bash
python finetune_table_with_reasoning.py
```

The final LoRA adapter and processor are written to:

```text
qwen35_4b_table_html_reasoning_lora/
```

Trainer checkpoints are created in the same directory, for example:

```text
qwen35_4b_table_html_reasoning_lora/checkpoint-100/
```

## Smoke Test

Use a small subset to verify model loading, collation, training, evaluation,
and checkpoint saving before starting the full run:

```bash
python finetune_table_with_reasoning.py \
  --max-train-samples 8 \
  --max-eval-samples 2 \
  --num-train-epochs 1 \
  --gradient-accumulation-steps 1 \
  --logging-steps 1 \
  --eval-steps 4 \
  --save-steps 4 \
  --output-dir /tmp/table-reasoning-smoke
```

The full `20480` context can require substantial VRAM even with batch size 1.
For a pipeline-only smoke test on a smaller GPU, temporarily reduce the context:

```bash
python finetune_table_with_reasoning.py \
  --max-train-samples 2 \
  --max-eval-samples 1 \
  --num-train-epochs 1 \
  --gradient-accumulation-steps 1 \
  --max-seq-length 4096 \
  --logging-steps 1 \
  --eval-steps 1 \
  --save-steps 1 \
  --output-dir /tmp/table-reasoning-smoke
```

The reduced context intentionally truncates long targets and should not be used
for the final training run.

## Configure Training

Example configuration with a different effective batch size and output path:

```bash
python finetune_table_with_reasoning.py \
  --output-dir qwen35_table_reasoning_experiment \
  --num-train-epochs 3 \
  --per-device-train-batch-size 1 \
  --gradient-accumulation-steps 16 \
  --learning-rate 5e-5 \
  --eval-steps 50 \
  --save-steps 50
```

To train only language layers while keeping the vision encoder frozen:

```bash
python finetune_table_with_reasoning.py --language-only
```

To use a different dataset revision:

```bash
python finetune_table_with_reasoning.py \
  --dataset-revision REVISION_OR_COMMIT_SHA
```

## Resume Training

Resume model, optimizer, scheduler, and Trainer state from an existing
checkpoint:

```bash
python finetune_table_with_reasoning.py \
  --resume-from-checkpoint qwen35_4b_table_html_reasoning_lora/checkpoint-100
```

Keep training arguments consistent with the original run unless intentionally
starting a new training schedule.

## Important Arguments

```text
--dataset-id
--dataset-config
--dataset-revision
--model-name
--output-dir
--train-split
--eval-split
--eval-size
--max-seq-length
--max-train-samples
--max-eval-samples
--dry-run
--num-train-epochs
--per-device-train-batch-size
--per-device-eval-batch-size
--gradient-accumulation-steps
--learning-rate
--warmup-ratio
--lr-scheduler-type
--optim
--weight-decay
--max-grad-norm
--logging-steps
--eval-steps
--save-steps
--save-total-limit
--lora-r
--lora-alpha
--lora-dropout
--language-only
--resume-from-checkpoint
```

Run the built-in help for the complete CLI:

```bash
python finetune_table_with_reasoning.py --help
```
