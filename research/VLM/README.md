# VLM OCR Fine-Tuning

This folder contains `finetune.py`, a script for fine-tuning `unsloth/Qwen3.5-0.8B` on the Hugging Face dataset `5CD-AI/Viet-Handwriting-OCR-v2`.

## Install

From the repository root:

```bash
pip install --upgrade --force-reinstall --no-cache-dir unsloth unsloth_zoo
pip install -U datasets trl accelerate pillow torchvision
```

## Train From Scratch

```bash
cd research/VLM
python finetune.py
```

The script writes LoRA checkpoints and the final adapter to:

```text
qwen35_08b_ocr_lora/
```

Checkpoints are saved every 100 steps, for example:

```text
qwen35_08b_ocr_lora/checkpoint-1700/
```

## Resume From A Checkpoint

Pass the checkpoint folder as an argument:

```bash
cd research/VLM
python finetune.py qwen35_08b_ocr_lora/checkpoint-1700
```

Equivalent named argument:

```bash
python finetune.py --resume-from-checkpoint qwen35_08b_ocr_lora/checkpoint-1700
```

The checkpoint path must be an existing folder. Training resumes optimizer, scheduler, trainer state, and model adapter state from that checkpoint.

## Configure Training

Common settings can be changed from the command line:

```bash
python finetune.py \
  --output-dir qwen35_08b_ocr_lora \
  --per-device-train-batch-size 1 \
  --gradient-accumulation-steps 8 \
  --num-train-epochs 3 \
  --learning-rate 1e-4 \
  --save-steps 100 \
  --eval-steps 100
```

Resume while changing training settings:

```bash
python finetune.py \
  --resume-from-checkpoint qwen35_08b_ocr_lora/checkpoint-1700 \
  --per-device-train-batch-size 2 \
  --gradient-accumulation-steps 4
```

Useful arguments:

```text
--dataset-id
--model-name
--output-dir
--max-seq-length
--num-train-epochs
--per-device-train-batch-size
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
--seed
--dataset-num-proc
--lora-r
--lora-alpha
--lora-dropout
--resume-from-checkpoint
```

## Main Defaults

Default values in `finetune.py`:

```python
DEFAULT_DATASET_ID = "5CD-AI/Viet-Handwriting-OCR-v2"
DEFAULT_MODEL_NAME = "unsloth/Qwen3.5-0.8B"
DEFAULT_OUTPUT_DIR = "qwen35_08b_ocr_lora"
DEFAULT_MAX_SEQ_LENGTH = 2048
```

The dataset is expected to have `train` and `test` splits with these columns:

```text
image
text
```
