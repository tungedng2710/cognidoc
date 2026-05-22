"""Demo OCR inference with the CogniOCR adapter from Hugging Face.

Examples:
    python demo_hf.py
    python demo_hf.py path/to/image.png
    python demo_hf.py path/to/image.png --output-file ocr.txt
"""

import argparse
from pathlib import Path

from predict import (
    OCR_PROMPT,
    build_inputs,
    decode_new_tokens,
    load_image,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_ID = "tungedng2710/cogniocr"
DEFAULT_IMAGE = SCRIPT_DIR / "test1.png"
DEFAULT_MAX_SEQ_LENGTH = 2048


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run OCR with the CogniOCR LoRA adapter from Hugging Face.",
    )
    parser.add_argument(
        "image",
        nargs="?",
        default=str(DEFAULT_IMAGE),
        help=f"Path to the image to OCR. Defaults to {DEFAULT_IMAGE}.",
    )
    parser.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help=f"Hugging Face model id or local adapter path. Defaults to {DEFAULT_MODEL_ID}.",
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
        help="Load the model in 4-bit quantized mode instead of 16-bit.",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help="Optional path to write the OCR text.",
    )
    return parser.parse_args()


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

    print(f"Loading model: {args.model_id}")
    model, tokenizer = FastVisionModel.from_pretrained(
        model_name=args.model_id,
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
    print("\nOCR result:")
    print(text)

    if args.output_file:
        output_path = Path(args.output_file).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
        print(f"\nWrote OCR text to: {output_path}")


if __name__ == "__main__":
    main()
