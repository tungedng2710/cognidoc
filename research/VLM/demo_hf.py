from pathlib import Path

from predict import (
    OCR_PROMPT,
    build_inputs,
    decode_new_tokens,
    load_image,
)


SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_ID = "tungedng2710/cogniocr"
IMAGE_PATH = SCRIPT_DIR / "test1.png"
MAX_SEQ_LENGTH = 2048
MAX_NEW_TOKENS = 512


def main():
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

    image = load_image(IMAGE_PATH)
    dtype = torch.bfloat16 if is_bfloat16_supported() else torch.float16

    print(f"Loading model: {MODEL_ID}")
    model, tokenizer = FastVisionModel.from_pretrained(
        model_name=MODEL_ID,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=dtype,
        load_in_4bit=False,
        load_in_16bit=True,
    )

    FastVisionModel.for_inference(model)

    device = next(model.parameters()).device
    inputs = build_inputs(tokenizer, image, OCR_PROMPT, device)
    prompt_token_count = inputs["input_ids"].shape[-1]

    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            use_cache=True,
            do_sample=False,
        )

    text = decode_new_tokens(tokenizer, outputs, prompt_token_count)
    print("\nOCR result:")
    print(text)


if __name__ == "__main__":
    main()
