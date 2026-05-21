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

import torch
from datasets import load_dataset, Image
from PIL import Image as PILImage

from unsloth import FastVisionModel, is_bfloat16_supported
from unsloth.trainer import UnslothVisionDataCollator
from trl import SFTTrainer, SFTConfig


# -----------------------------
# Config
# -----------------------------
DATASET_ID = "5CD-AI/Viet-Handwriting-OCR-v2"   # <-- change this
MODEL_NAME = "unsloth/Qwen3.5-0.8B"             # or "Qwen/Qwen3.5-0.8B"

OUTPUT_DIR = "qwen35_08b_ocr_lora"
MAX_SEQ_LENGTH = 2048

OCR_PROMPT = (
    "Read the text in this image. "
    "Return exactly the visible text, preserving line breaks when possible. "
    "Do not add explanations."
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fine-tune Qwen3.5-0.8B for OCR with optional checkpoint resume.",
    )
    parser.add_argument(
        "checkpoint_folder",
        nargs="?",
        default=None,
        help=(
            "Optional checkpoint folder to resume from, e.g. "
            "qwen35_08b_ocr_lora/checkpoint-1700."
        ),
    )
    parser.add_argument(
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


# -----------------------------
# Load dataset
# -----------------------------
dataset = load_dataset(DATASET_ID)

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
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LENGTH,
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

    r=16,
    lora_alpha=16,
    lora_dropout=0,
    bias="none",

    target_modules="all-linear",
    random_state=3407,
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
        output_dir=OUTPUT_DIR,

        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,

        # Use num_train_epochs for full training.
        num_train_epochs=3,

        learning_rate=1e-4,
        warmup_ratio=0.03,
        lr_scheduler_type="linear",

        optim="adamw_8bit",
        weight_decay=0.01,
        max_grad_norm=0.3,

        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),

        logging_steps=10,
        eval_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=100,

        seed=3407,
        report_to="none",

        # Required for vision fine-tuning
        remove_unused_columns=False,
        dataset_text_field="",
        dataset_kwargs={"skip_prepare_dataset": True},
        dataset_num_proc=1,

        max_seq_length=MAX_SEQ_LENGTH,
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
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

# Optional: save merged 16-bit model
# model.save_pretrained_merged(
#     "qwen35_08b_ocr_merged",
#     tokenizer,
#     save_method="merged_16bit",
# )

# Optional: push LoRA to Hugging Face
# model.push_to_hub("your_username/qwen35-08b-ocr-lora", token="hf_xxx")
# tokenizer.push_to_hub("your_username/qwen35-08b-ocr-lora", token="hf_xxx")
