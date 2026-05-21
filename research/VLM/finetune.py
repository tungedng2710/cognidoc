# ============================================================
# Fine-tune Qwen3.5-0.8B for OCR with Unsloth
# Dataset format:
#   train split: columns ["image", "text"]
#   test split:  columns ["image", "text"]
# ============================================================

# Install first, if needed:
# pip install --upgrade --force-reinstall --no-cache-dir unsloth unsloth_zoo
# pip install -U datasets trl accelerate pillow torchvision

import argparse
from pathlib import Path


# -----------------------------
# Config
# -----------------------------
DEFAULT_DATASET_ID = "5CD-AI/Viet-Handwriting-OCR-v2"
DEFAULT_MODEL_NAME = "unsloth/Qwen3.5-0.8B"  # or "Qwen/Qwen3.5-0.8B"
DEFAULT_OUTPUT_DIR = "qwen35_08b_ocr_lora"
DEFAULT_MAX_SEQ_LENGTH = 2048

OCR_PROMPT = (
    "Read the text in this image. "
    "Return exactly the visible text, preserving line breaks when possible. "
    "Do not add explanations."
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fine-tune Qwen3.5-0.8B for OCR with optional checkpoint resume.",
    )

    data_group = parser.add_argument_group("data and model")
    data_group.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    data_group.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    data_group.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    data_group.add_argument("--max-seq-length", type=int, default=DEFAULT_MAX_SEQ_LENGTH)

    train_group = parser.add_argument_group("training")
    train_group.add_argument("--num-train-epochs", type=float, default=3)
    train_group.add_argument("--per-device-train-batch-size", type=int, default=1)
    train_group.add_argument("--gradient-accumulation-steps", type=int, default=8)
    train_group.add_argument("--learning-rate", type=float, default=1e-4)
    train_group.add_argument("--warmup-ratio", type=float, default=0.03)
    train_group.add_argument("--lr-scheduler-type", default="linear")
    train_group.add_argument("--optim", default="adamw_8bit")
    train_group.add_argument("--weight-decay", type=float, default=0.01)
    train_group.add_argument("--max-grad-norm", type=float, default=0.3)
    train_group.add_argument("--logging-steps", type=int, default=10)
    train_group.add_argument("--eval-steps", type=int, default=100)
    train_group.add_argument("--save-steps", type=int, default=100)
    train_group.add_argument("--seed", type=int, default=3407)
    train_group.add_argument("--dataset-num-proc", type=int, default=1)

    lora_group = parser.add_argument_group("lora")
    lora_group.add_argument("--lora-r", type=int, default=16)
    lora_group.add_argument("--lora-alpha", type=int, default=16)
    lora_group.add_argument("--lora-dropout", type=float, default=0)

    resume_group = parser.add_argument_group("resume")
    parser.add_argument(
        "checkpoint_folder",
        nargs="?",
        default=None,
        help=(
            "Optional checkpoint folder to resume from, e.g. "
            "qwen35_08b_ocr_lora/checkpoint-1700."
        ),
    )
    resume_group.add_argument(
        "--resume-from-checkpoint",
        default=None,
        help="Checkpoint folder to resume from. Overrides the positional argument.",
    )
    return parser.parse_args()


def get_resume_checkpoint(args):
    checkpoint = args.resume_from_checkpoint or args.checkpoint_folder
    if checkpoint is None:
        return None

    checkpoint_path = Path(checkpoint).expanduser()
    if not checkpoint_path.is_dir():
        raise FileNotFoundError(
            f"Resume checkpoint folder does not exist: {checkpoint_path}"
        )

    return str(checkpoint_path)


args = parse_args()
RESUME_FROM_CHECKPOINT = get_resume_checkpoint(args)


import torch
from datasets import load_dataset, Image
from PIL import Image as PILImage

from unsloth import FastVisionModel, is_bfloat16_supported
from unsloth.trainer import UnslothVisionDataCollator
from trl import SFTTrainer, SFTConfig


# -----------------------------
# Load dataset
# -----------------------------
dataset = load_dataset(args.dataset_id)

# Ensure the image column is decoded as PIL images
dataset = dataset.cast_column("image", Image())

train_raw = dataset["train"]
test_raw = dataset["test"]


# -----------------------------
# Convert image/text rows to VLM chat format
# -----------------------------
def to_rgb(image):
    if isinstance(image, str):
        return PILImage.open(image).convert("RGB")
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def convert_to_conversation(sample):
    image = to_rgb(sample["image"])
    answer = str(sample["text"]).strip()

    return {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": OCR_PROMPT},
                    {"type": "image", "image": image},
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": answer},
                ],
            },
        ]
    }


# For vision datasets, list conversion is often simpler than dataset.map()
train_dataset = [convert_to_conversation(x) for x in train_raw]
eval_dataset = [convert_to_conversation(x) for x in test_raw]


# -----------------------------
# Load Qwen3.5 vision model
# -----------------------------
dtype = torch.bfloat16 if is_bfloat16_supported() else torch.float16

model, tokenizer = FastVisionModel.from_pretrained(
    model_name=args.model_name,
    max_seq_length=args.max_seq_length,
    dtype=dtype,

    # Qwen3.5 Unsloth docs recommend bf16/16-bit LoRA over 4-bit QLoRA.
    load_in_4bit=False,
    load_in_16bit=True,

    use_gradient_checkpointing="unsloth",
)


# -----------------------------
# Add LoRA adapters
# -----------------------------
model = FastVisionModel.get_peft_model(
    model,

    # For OCR, usually keep both vision + language trainable.
    finetune_vision_layers=True,
    finetune_language_layers=True,
    finetune_attention_modules=True,
    finetune_mlp_modules=True,

    r=args.lora_r,
    lora_alpha=args.lora_alpha,
    lora_dropout=args.lora_dropout,
    bias="none",

    target_modules="all-linear",
    random_state=args.seed,
    use_rslora=False,
    loftq_config=None,

    # Useful when adapting vocabulary/output head behavior
    modules_to_save=[
        "lm_head",
        "embed_tokens",
    ],
)


# -----------------------------
# Train
# -----------------------------
FastVisionModel.for_training(model)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    data_collator=UnslothVisionDataCollator(
        model,
        tokenizer,

        # Optional but useful: only compute loss on assistant OCR answer.
        # If your chat template causes matching errors, set this to False.
        train_on_responses_only=True,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    ),
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    args=SFTConfig(
        output_dir=args.output_dir,

        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,

        # Use num_train_epochs for full training.
        num_train_epochs=args.num_train_epochs,

        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        lr_scheduler_type=args.lr_scheduler_type,

        optim=args.optim,
        weight_decay=args.weight_decay,
        max_grad_norm=args.max_grad_norm,

        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),

        logging_steps=args.logging_steps,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_strategy="steps",
        save_steps=args.save_steps,

        seed=args.seed,
        report_to="none",

        # Required for vision fine-tuning
        remove_unused_columns=False,
        dataset_text_field="",
        dataset_kwargs={"skip_prepare_dataset": True},
        dataset_num_proc=args.dataset_num_proc,

        max_seq_length=args.max_seq_length,
    ),
)

if RESUME_FROM_CHECKPOINT:
    print(f"Resuming training from checkpoint: {RESUME_FROM_CHECKPOINT}")
    trainer.train(resume_from_checkpoint=RESUME_FROM_CHECKPOINT)
else:
    trainer.train()


# -----------------------------
# Save LoRA adapter
# -----------------------------
model.save_pretrained(args.output_dir)
tokenizer.save_pretrained(args.output_dir)

# Optional: save merged 16-bit model
# model.save_pretrained_merged(
#     "qwen35_08b_ocr_merged",
#     tokenizer,
#     save_method="merged_16bit",
# )

# Optional: push LoRA to Hugging Face
# model.push_to_hub("your_username/qwen35-08b-ocr-lora", token="hf_xxx")
# tokenizer.push_to_hub("your_username/qwen35-08b-ocr-lora", token="hf_xxx")
