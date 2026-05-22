"""Run OCR inference with the fine-tuned Qwen/Unsloth VLM.

Example:
    python predict.py path/to/image.png
    python predict.py path/to/image.png --model-dir qwen35_08b_ocr_lora
"""

import argparse
from pathlib import Path


DEFAULT_MODEL_DIR = Path(__file__).resolve().parent / "qwen35_08b_ocr_lora"
DEFAULT_MAX_SEQ_LENGTH = 2048

OCR_PROMPT = (
    "Read the text in this image. "
    "Return exactly the visible text, preserving line breaks when possible. "
    "Do not add explanations."
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run OCR on an image with a fine-tuned Qwen/Unsloth VLM.",
    )
    parser.add_argument(
        "image",
        help="Path to the image to OCR.",
    )
    parser.add_argument(
        "--model-dir",
        default=str(DEFAULT_MODEL_DIR),
        help=(
            "Path or Hugging Face id for the model/adapters to load. "
            f"Defaults to {DEFAULT_MODEL_DIR}."
        ),
    )
    parser.add_argument(
        "--prompt",
        default=OCR_PROMPT,
        help="Instruction prompt sent with the image.",
    )
    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=DEFAULT_MAX_SEQ_LENGTH,
        help="Maximum model sequence length.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=512,
        help="Maximum number of generated OCR tokens.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature. Use 0 for deterministic greedy decoding.",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=0.9,
        help="Nucleus sampling value used when temperature is greater than 0.",
    )
    parser.add_argument(
        "--load-in-4bit",
        action="store_true",
        help="Load model in 4-bit quantized mode instead of 16-bit.",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Optional path to write the OCR text.",
    )
    return parser.parse_args()


def load_image(image_path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: pillow. Install it with `pip install pillow`."
        ) from exc

    path = Path(image_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Image file does not exist: {path}")

    return Image.open(path).convert("RGB")


def move_inputs_to_device(inputs, device):
    if hasattr(inputs, "to"):
        return inputs.to(device)

    return {
        key: value.to(device) if hasattr(value, "to") else value
        for key, value in inputs.items()
    }


def build_inputs(tokenizer, image, prompt, device):
    template_messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image"},
            ],
        }
    ]
    input_text = tokenizer.apply_chat_template(
        template_messages,
        add_generation_prompt=True,
        tokenize=False,
    )

    try:
        inputs = tokenizer(
            image,
            input_text,
            add_special_tokens=False,
            return_tensors="pt",
        )
        return move_inputs_to_device(inputs, device)
    except (TypeError, ValueError):
        pass

    try:
        inputs = tokenizer(
            images=image,
            text=input_text,
            add_special_tokens=False,
            return_tensors="pt",
        )
        return move_inputs_to_device(inputs, device)
    except (TypeError, ValueError):
        pass

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image", "image": image},
            ],
        }
    ]

    try:
        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        )
    except TypeError as exc:
        raise RuntimeError("Could not build vision inputs for this processor.") from exc

    return move_inputs_to_device(inputs, device)


def decode_new_tokens(tokenizer, outputs, prompt_token_count):
    generated_tokens = outputs[0][prompt_token_count:]
    return tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()


def main():
    args = parse_args()

    try:
        import torch
        from unsloth import FastVisionModel, is_bfloat16_supported
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: unsloth/torch. Install the VLM dependencies first:\n"
            "  pip install --upgrade --force-reinstall --no-cache-dir unsloth "
            "unsloth_zoo\n"
            "  pip install -U torch pillow torchvision"
        ) from exc

    image = load_image(args.image)
    dtype = torch.bfloat16 if is_bfloat16_supported() else torch.float16

    model, tokenizer = FastVisionModel.from_pretrained(
        model_name=args.model_dir,
        max_seq_length=args.max_seq_length,
        dtype=dtype,
        load_in_4bit=args.load_in_4bit,
        load_in_16bit=not args.load_in_4bit,
    )

    FastVisionModel.for_inference(model)

    device = next(model.parameters()).device
    inputs = build_inputs(tokenizer, image, args.prompt, device)
    prompt_token_count = inputs["input_ids"].shape[-1]

    generation_kwargs = {
        "max_new_tokens": args.max_new_tokens,
        "use_cache": True,
        "do_sample": args.temperature > 0,
    }
    if args.temperature > 0:
        generation_kwargs.update(
            {
                "temperature": args.temperature,
                "top_p": args.top_p,
            }
        )

    with torch.inference_mode():
        outputs = model.generate(**inputs, **generation_kwargs)

    text = decode_new_tokens(tokenizer, outputs, prompt_token_count)
    print(text)

    if args.output_file:
        output_path = Path(args.output_file).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()