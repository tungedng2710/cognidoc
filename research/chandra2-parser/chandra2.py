import argparse
import sys
from pathlib import Path

MODEL_NAME = "datalab-to/chandra-ocr-2"
SUPPORTED_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Chandra OCR on an image, PDF, or folder."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to an image, PDF, or folder containing supported files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help=(
            "Output Markdown file for a single input, or output directory for a "
            "folder. Folder inputs default to <input>_output."
        ),
    )
    parser.add_argument(
        "-b",
        "--batch-size",
        type=positive_int,
        default=1,
        help="Number of images/PDF pages to process at once (default: 1).",
    )
    return parser.parse_args()


def get_input_files(input_path: Path) -> list[Path]:
    input_path = input_path.expanduser()

    if not input_path.exists():
        raise ValueError(f"Input path does not exist: {input_path}")

    if input_path.is_file():
        if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {input_path.suffix or '(none)'}")
        return [input_path]

    if input_path.is_dir():
        files = sorted(
            path
            for path in input_path.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if not files:
            raise ValueError(f"No supported image or PDF files found in: {input_path}")
        return files

    raise ValueError(f"Input is not a regular file or directory: {input_path}")


def load_model():
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_NAME,
        dtype=torch.bfloat16,
        device_map="auto",
    )
    model.eval()
    model.processor = AutoProcessor.from_pretrained(MODEL_NAME)
    model.processor.tokenizer.padding_side = "left"
    return model


def process_file(file_path: Path, model, batch_size: int) -> list[str]:
    from chandra.input import load_file
    from chandra.model.hf import generate_hf
    from chandra.model.schema import BatchInputItem
    from chandra.output import parse_markdown

    images = load_file(str(file_path), {})
    markdown_pages = []

    try:
        for start in range(0, len(images), batch_size):
            batch_images = images[start : start + batch_size]
            batch = [
                BatchInputItem(image=image, prompt_type="ocr_layout")
                for image in batch_images
            ]
            end = start + len(batch_images)
            print(
                f"  Processing page/image {start + 1}-{end} of {len(images)}",
                file=sys.stderr,
            )
            results = generate_hf(batch, model)
            markdown_pages.extend(parse_markdown(result.raw) for result in results)
    finally:
        for image in images:
            image.close()

    return markdown_pages


def get_folder_output_file(
    file_path: Path, input_files: list[Path], output_dir: Path
) -> Path:
    same_stem_count = sum(
        other.stem.casefold() == file_path.stem.casefold() for other in input_files
    )
    if same_stem_count == 1:
        return output_dir / f"{file_path.stem}.md"
    return output_dir / f"{file_path.name}.md"


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()

    try:
        input_files = get_input_files(input_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    output_dir = None
    output_file = None
    if input_path.is_dir():
        output_dir = (
            args.output.expanduser()
            if args.output
            else input_path.parent / f"{input_path.name or 'input'}_output"
        )
        if output_dir.exists() and not output_dir.is_dir():
            print(
                f"Error: Folder input requires an output directory: {output_dir}",
                file=sys.stderr,
            )
            return 2
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output directory: {output_dir}", file=sys.stderr)
    elif args.output:
        output_file = args.output.expanduser()
        if output_file.exists() and output_file.is_dir():
            output_file = output_file / f"{input_path.stem}.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading model: {MODEL_NAME}", file=sys.stderr)
    model = load_model()

    for index, file_path in enumerate(input_files, start=1):
        print(
            f"[{index}/{len(input_files)}] Processing {file_path}",
            file=sys.stderr,
        )
        markdown = "\n\n".join(process_file(file_path, model, args.batch_size))

        if output_dir is not None:
            destination = get_folder_output_file(
                file_path, input_files, output_dir
            )
            destination.write_text(markdown + "\n", encoding="utf-8")
            print(f"  Saved {destination}", file=sys.stderr)
        elif output_file is not None:
            output_file.write_text(markdown + "\n", encoding="utf-8")
            print(f"Saved {output_file}", file=sys.stderr)
        else:
            print(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
