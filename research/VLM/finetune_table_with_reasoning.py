import argparse
import inspect
import json
from io import BytesIO
from pathlib import Path


DEFAULT_DATASET_ID = "tungedng2710/table_html_with_reasoning"
DEFAULT_MODEL_NAME = "unsloth/Qwen3.5-4B"
DEFAULT_OUTPUT_DIR = "qwen35_4b_table_html_reasoning_lora"
# The longest current target is about 17.7k tokens before vision/chat tokens.
DEFAULT_MAX_SEQ_LENGTH = 20_480
 
TABLE_REASONING_PROMPT = (
    "Analyze the table shown in the provided image or images and reconstruct it as HTML. "
    "If there are multiple images, they are consecutive parts of the same table. "
    "First provide your table-structure reasoning inside <think>...</think>. "
    "Then provide the complete structural <table>...</table> HTML. "
    "Preserve all visible text, empty cells, row and column order, and rowspan or colspan "
    "attributes. Do not use markdown fences or add text outside the reasoning and table."
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Fine-tune Qwen3.5-4B with Unsloth on table images paired with "
            "reasoning traces and structural HTML."
        ),
    )

    data_group = parser.add_argument_group("data and model")
    data_group.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    data_group.add_argument("--dataset-config", default=None)
    data_group.add_argument("--dataset-revision", default=None)
    data_group.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    data_group.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    data_group.add_argument("--train-split", default="train")
    data_group.add_argument("--eval-split", default=None)
    data_group.add_argument("--eval-size", type=float, default=0.1)
    data_group.add_argument("--max-seq-length", type=int, default=DEFAULT_MAX_SEQ_LENGTH)
    data_group.add_argument("--max-train-samples", type=int, default=None)
    data_group.add_argument("--max-eval-samples", type=int, default=None)
    data_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize the dataset without loading the model.",
    )

    train_group = parser.add_argument_group("training")
    train_group.add_argument("--num-train-epochs", type=float, default=3)
    train_group.add_argument("--per-device-train-batch-size", type=int, default=1)
    train_group.add_argument("--per-device-eval-batch-size", type=int, default=1)
    train_group.add_argument("--gradient-accumulation-steps", type=int, default=8)
    train_group.add_argument("--learning-rate", type=float, default=1e-4)
    train_group.add_argument("--warmup-ratio", type=float, default=0.03)
    train_group.add_argument("--lr-scheduler-type", default="linear")
    train_group.add_argument("--optim", default="adamw_torch_fused")
    train_group.add_argument("--weight-decay", type=float, default=0.01)
    train_group.add_argument("--max-grad-norm", type=float, default=0.3)
    train_group.add_argument("--logging-steps", type=int, default=10)
    train_group.add_argument("--eval-steps", type=int, default=100)
    train_group.add_argument("--save-steps", type=int, default=100)
    train_group.add_argument("--save-total-limit", type=int, default=3)
    train_group.add_argument("--seed", type=int, default=3407)
    train_group.add_argument("--dataset-num-proc", type=int, default=1)

    lora_group = parser.add_argument_group("lora")
    lora_group.add_argument("--lora-r", type=int, default=16)
    lora_group.add_argument("--lora-alpha", type=int, default=16)
    lora_group.add_argument("--lora-dropout", type=float, default=0)
    lora_group.add_argument("--language-only", action="store_true")

    parser.add_argument(
        "--resume-from-checkpoint",
        default=None,
        help="Existing Trainer checkpoint directory from which to resume.",
    )
    return parser.parse_args(argv)


def validate_args(args):
    if not 0 < args.eval_size < 1 and args.eval_split is None:
        raise ValueError("--eval-size must be between 0 and 1 when --eval-split is not set.")
    if args.max_seq_length <= 0:
        raise ValueError("--max-seq-length must be positive.")
    for name in ("max_train_samples", "max_eval_samples"):
        value = getattr(args, name)
        if value is not None and value <= 0:
            raise ValueError(f"--{name.replace('_', '-')} must be positive when set.")


def get_resume_checkpoint(checkpoint):
    if checkpoint is None:
        return None
    checkpoint_path = Path(checkpoint).expanduser()
    if not checkpoint_path.is_dir():
        raise FileNotFoundError(f"Resume checkpoint directory does not exist: {checkpoint_path}")
    return str(checkpoint_path)


def load_and_split_dataset(args):
    from datasets import load_dataset

    load_kwargs = {}
    if args.dataset_revision:
        load_kwargs["revision"] = args.dataset_revision
    dataset = load_dataset(args.dataset_id, args.dataset_config, **load_kwargs)

    if args.train_split not in dataset:
        raise ValueError(
            f"Train split {args.train_split!r} was not found. Available splits: {list(dataset)}"
        )

    train_dataset = dataset[args.train_split]
    if args.eval_split:
        if args.eval_split not in dataset:
            raise ValueError(
                f"Eval split {args.eval_split!r} was not found. Available splits: {list(dataset)}"
            )
        eval_dataset = dataset[args.eval_split]
    else:
        split = train_dataset.train_test_split(test_size=args.eval_size, seed=args.seed)
        train_dataset, eval_dataset = split["train"], split["test"]

    if args.max_train_samples is not None:
        train_dataset = train_dataset.select(
            range(min(args.max_train_samples, len(train_dataset)))
        )
    if args.max_eval_samples is not None:
        eval_dataset = eval_dataset.select(range(min(args.max_eval_samples, len(eval_dataset))))

    return train_dataset, eval_dataset


def validate_dataset(dataset, split_name):
    required_columns = {"id", "images", "table_html", "has_reasoning", "num_images"}
    missing_columns = required_columns.difference(dataset.column_names)
    if missing_columns:
        raise ValueError(
            f"{split_name} is missing required columns: {sorted(missing_columns)}"
        )

    errors = []
    for index, sample in enumerate(dataset):
        images = sample["images"]
        target = sample["table_html"]
        if not images:
            errors.append(f"row {index} ({sample['id']}): no images")
        elif sample["num_images"] != len(images):
            errors.append(
                f"row {index} ({sample['id']}): num_images={sample['num_images']} "
                f"but found {len(images)} images"
            )
        if not sample["has_reasoning"]:
            errors.append(f"row {index} ({sample['id']}): has_reasoning is false")
        if not isinstance(target, str) or not target.strip():
            errors.append(f"row {index} ({sample['id']}): empty table_html target")
        elif not (
            target.lstrip().startswith("<think>")
            and "</think>" in target
            and "<table" in target.lower()
            and "</table>" in target.lower()
        ):
            errors.append(f"row {index} ({sample['id']}): malformed reasoning/HTML target")
        if len(errors) >= 10:
            break

    if errors:
        raise ValueError(f"Invalid {split_name} dataset:\n" + "\n".join(errors))


def to_rgb(image):
    from PIL import Image

    if isinstance(image, Image.Image):
        return image if image.mode == "RGB" else image.convert("RGB")
    if isinstance(image, (str, Path)):
        with Image.open(image) as opened:
            return opened.convert("RGB")
    if isinstance(image, bytes):
        with Image.open(BytesIO(image)) as opened:
            return opened.convert("RGB")
    if isinstance(image, dict):
        if image.get("bytes") is not None:
            return to_rgb(image["bytes"])
        if image.get("path") is not None:
            return to_rgb(image["path"])
        if image.get("image") is not None:
            return to_rgb(image["image"])
    raise TypeError(f"Unsupported image value: {type(image).__name__}")


def convert_to_conversation(sample):
    user_content = [{"type": "text", "text": TABLE_REASONING_PROMPT}]
    user_content.extend(
        {"type": "image", "image": to_rgb(image)} for image in sample["images"]
    )
    return {
        "messages": [
            {"role": "user", "content": user_content},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": sample["table_html"].strip()}],
            },
        ]
    }


def print_dataset_summary(train_dataset, eval_dataset, max_seq_length):
    targets = list(train_dataset["table_html"]) + list(eval_dataset["table_html"])
    image_counts = list(train_dataset["num_images"]) + list(eval_dataset["num_images"])
    lengths = sorted(len(target) for target in targets)
    summary = {
        "train_rows": len(train_dataset),
        "eval_rows": len(eval_dataset),
        "image_counts": sorted(set(image_counts)),
        "target_characters": {
            "min": lengths[0],
            "median": lengths[len(lengths) // 2],
            "max": lengths[-1],
        },
        "max_seq_length": max_seq_length,
    }
    print(json.dumps(summary, indent=2))


def build_sft_config(args, is_bfloat16_supported, eos_token):
    from trl import SFTConfig

    config_kwargs = {
        "output_dir": args.output_dir,
        "per_device_train_batch_size": args.per_device_train_batch_size,
        "per_device_eval_batch_size": args.per_device_eval_batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "num_train_epochs": args.num_train_epochs,
        "learning_rate": args.learning_rate,
        "warmup_ratio": args.warmup_ratio,
        "lr_scheduler_type": args.lr_scheduler_type,
        "optim": args.optim,
        "weight_decay": args.weight_decay,
        "max_grad_norm": args.max_grad_norm,
        "fp16": not is_bfloat16_supported(),
        "bf16": is_bfloat16_supported(),
        "logging_steps": args.logging_steps,
        "eval_strategy": "steps",
        "eval_steps": args.eval_steps,
        "save_strategy": "steps",
        "save_steps": args.save_steps,
        "save_total_limit": args.save_total_limit,
        "seed": args.seed,
        "report_to": "none",
        "remove_unused_columns": False,
        "dataset_text_field": "",
        "dataset_kwargs": {"skip_prepare_dataset": True},
        "dataset_num_proc": args.dataset_num_proc,
        "packing": False,
    }
    if eos_token is not None:
        config_kwargs["eos_token"] = eos_token

    config_parameters = inspect.signature(SFTConfig).parameters
    length_parameter = "max_length" if "max_length" in config_parameters else "max_seq_length"
    config_kwargs[length_parameter] = args.max_seq_length
    return SFTConfig(**config_kwargs)


def main(argv=None):
    args = parse_args(argv)
    validate_args(args)
    resume_from_checkpoint = get_resume_checkpoint(args.resume_from_checkpoint)

    if args.dry_run:
        train_raw, eval_raw = load_and_split_dataset(args)
        validate_dataset(train_raw, "train")
        validate_dataset(eval_raw, "eval")
        print_dataset_summary(train_raw, eval_raw, args.max_seq_length)
        conversation = convert_to_conversation(train_raw[0])
        print(
            f"Dry run passed; sample has {len(conversation['messages'][0]['content']) - 1} "
            "image(s) and a valid assistant response."
        )
        return

    # Unsloth must be imported before Transformers, TRL, and Torch patch their models.
    import unsloth  # noqa: F401

    train_raw, eval_raw = load_and_split_dataset(args)
    validate_dataset(train_raw, "train")
    validate_dataset(eval_raw, "eval")
    print_dataset_summary(train_raw, eval_raw, args.max_seq_length)

    import torch
    from trl import SFTTrainer
    from unsloth import FastVisionModel, is_bfloat16_supported
    from unsloth.trainer import UnslothVisionDataCollator

    train_dataset = [convert_to_conversation(sample) for sample in train_raw]
    eval_dataset = [convert_to_conversation(sample) for sample in eval_raw]

    dtype = torch.bfloat16 if is_bfloat16_supported() else torch.float16
    model, processor = FastVisionModel.from_pretrained(
        model_name=args.model_name,
        max_seq_length=args.max_seq_length,
        dtype=dtype,
        load_in_4bit=False,
        load_in_16bit=True,
        use_gradient_checkpointing="unsloth",
    )
    model = FastVisionModel.get_peft_model(
        model,
        finetune_vision_layers=not args.language_only,
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
    )
    FastVisionModel.for_training(model)

    eos_token = getattr(processor, "eos_token", None)
    if eos_token is None and hasattr(processor, "tokenizer"):
        eos_token = getattr(processor.tokenizer, "eos_token", None)

    trainer_kwargs = {
        "model": model,
        "data_collator": UnslothVisionDataCollator(
            model,
            processor,
            train_on_responses_only=True,
            instruction_part="<|im_start|>user\n",
            response_part="<|im_start|>assistant\n",
        ),
        "train_dataset": train_dataset,
        "eval_dataset": eval_dataset,
        "args": build_sft_config(args, is_bfloat16_supported, eos_token),
    }
    if "processing_class" in inspect.signature(SFTTrainer).parameters:
        trainer_kwargs["processing_class"] = processor
    else:
        trainer_kwargs["tokenizer"] = processor

    trainer = SFTTrainer(**trainer_kwargs)
    trainer.train(resume_from_checkpoint=resume_from_checkpoint)
    model.save_pretrained(args.output_dir)
    processor.save_pretrained(args.output_dir)


if __name__ == "__main__":
    main()
