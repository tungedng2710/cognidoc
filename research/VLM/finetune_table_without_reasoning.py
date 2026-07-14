import argparse
import inspect
import json

import finetune_table_with_reasoning as common


DEFAULT_DATASET_ID = common.DEFAULT_DATASET_ID
DEFAULT_MODEL_NAME = common.DEFAULT_MODEL_NAME
DEFAULT_OUTPUT_DIR = "qwen35_4b_table_html_no_reasoning_lora"
DEFAULT_MAX_SEQ_LENGTH = common.DEFAULT_MAX_SEQ_LENGTH

TABLE_HTML_PROMPT = (
    "Convert the table shown in the provided image or images into structural HTML. "
    "If there are multiple images, they are consecutive parts of the same table. "
    "Preserve all visible text, empty cells, row and column order, and rowspan or colspan "
    "attributes. Return only the complete <table>...</table> markup. "
    "Do not provide reasoning, explanations, markdown fences, or any other text."
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Fine-tune Qwen3.5-4B with Unsloth on table images and HTML only, "
            "without supervising reasoning traces."
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
        help="Validate and summarize the HTML-only dataset without loading the model.",
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


def extract_table_html(target):
    if not isinstance(target, str):
        raise TypeError(f"Expected a string target, received {type(target).__name__}")

    lowercase_target = target.lower()
    reasoning_end_tag = "</think>"
    reasoning_end = lowercase_target.rfind(reasoning_end_tag)
    if reasoning_end < 0:
        raise ValueError("Target does not contain a closing </think> tag")

    start = lowercase_target.find("<table", reasoning_end + len(reasoning_end_tag))
    closing_tag = "</table>"
    end = lowercase_target.rfind(closing_tag)
    if start < 0 or end < start:
        raise ValueError("Target does not contain a complete <table>...</table> element")
    return target[start : end + len(closing_tag)].strip()


def validate_source_dataset(dataset, split_name):
    common.validate_dataset(dataset, split_name)
    errors = []
    for index, target in enumerate(dataset["table_html"]):
        try:
            html = extract_table_html(target)
        except (TypeError, ValueError) as error:
            errors.append(f"row {index}: {error}")
        else:
            if "<think>" in html.lower() or "</think>" in html.lower():
                errors.append(f"row {index}: reasoning tags occur inside the table element")
        if len(errors) >= 10:
            break
    if errors:
        raise ValueError(f"Invalid {split_name} HTML-only targets:\n" + "\n".join(errors))


def convert_to_conversation(sample):
    user_content = [{"type": "text", "text": TABLE_HTML_PROMPT}]
    user_content.extend(
        {"type": "image", "image": common.to_rgb(image)} for image in sample["images"]
    )
    return {
        "messages": [
            {"role": "user", "content": user_content},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": extract_table_html(sample["table_html"])}],
            },
        ]
    }


def print_dataset_summary(train_dataset, eval_dataset, max_seq_length):
    source_targets = list(train_dataset["table_html"]) + list(eval_dataset["table_html"])
    html_lengths = sorted(len(extract_table_html(target)) for target in source_targets)
    image_counts = list(train_dataset["num_images"]) + list(eval_dataset["num_images"])
    summary = {
        "train_rows": len(train_dataset),
        "eval_rows": len(eval_dataset),
        "image_counts": sorted(set(image_counts)),
        "html_target_characters": {
            "min": html_lengths[0],
            "median": html_lengths[len(html_lengths) // 2],
            "max": html_lengths[-1],
        },
        "max_seq_length": max_seq_length,
        "reasoning_in_assistant_target": False,
    }
    print(json.dumps(summary, indent=2))


def prepare_datasets(args):
    train_dataset, eval_dataset = common.load_and_split_dataset(args)
    validate_source_dataset(train_dataset, "train")
    validate_source_dataset(eval_dataset, "eval")
    print_dataset_summary(train_dataset, eval_dataset, args.max_seq_length)
    return train_dataset, eval_dataset


def main(argv=None):
    args = parse_args(argv)
    common.validate_args(args)
    resume_from_checkpoint = common.get_resume_checkpoint(args.resume_from_checkpoint)

    if args.dry_run:
        train_raw, _ = prepare_datasets(args)
        conversation = convert_to_conversation(train_raw[0])
        assistant_target = conversation["messages"][1]["content"][0]["text"]
        if "<think>" in assistant_target.lower():
            raise RuntimeError("Dry run failed: assistant target still contains reasoning")
        print(
            f"Dry run passed; sample has {len(conversation['messages'][0]['content']) - 1} "
            "image(s) and an HTML-only assistant response."
        )
        return

    # Unsloth must be imported before Transformers, TRL, and Torch patch their models.
    import unsloth  # noqa: F401

    train_raw, eval_raw = prepare_datasets(args)

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
        "args": common.build_sft_config(args, is_bfloat16_supported, eos_token),
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
