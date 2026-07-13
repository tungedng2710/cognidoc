import argparse
import json
import tempfile
from pathlib import Path

from datasets import Dataset, Features, Image, Sequence, Value
from huggingface_hub import HfApi, login
from tqdm import tqdm


def dataset_card(num_examples: int | None = None, data_pattern: str = "data/train-*") -> str:
    split_info = ""
    if num_examples is not None:
        split_info = f"""  splits:
  - name: train
    num_examples: {num_examples}
"""
    return f"""---
license: mit
configs:
- config_name: default
  data_files:
  - split: train
    path: {data_pattern}
dataset_info:
  features:
  - name: id
    dtype: string
  - name: images
    list: image
  - name: table_html
    dtype: string
  - name: has_reasoning
    dtype: bool
  - name: num_images
    dtype: int32
{split_info}---

# Table HTML Dataset

Rows contain a list of table-page images in `images` and the corresponding table HTML in `table_html`. If `has_reasoning` is true, `table_html` contains a visible `<think>...</think>` reasoning trace followed by the final structural `<table>...</table>` label.
"""


def upload_dataset_card(repo_id: str, num_examples: int | None = None, data_pattern: str = "data/train-*") -> None:
    api = HfApi()
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8") as card_file:
        card_file.write(dataset_card(num_examples, data_pattern=data_pattern))
        card_file.flush()
        api.upload_file(
            path_or_fileobj=card_file.name,
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="dataset",
        )


def build_dataset(dataset_dir: Path, limit: int | None = None) -> Dataset:
    metadata = json.loads((dataset_dir / "metadata.json").read_text(encoding="utf-8"))
    if limit is not None:
        metadata = metadata[:limit]
    rows = []
    reasoning_dir = dataset_dir / "table_html_reasoning"
    for item in tqdm(metadata, desc="Preparing HF rows"):
        html_path = dataset_dir / item["table_html"]
        reasoning_path = reasoning_dir / Path(item["table_html"]).name
        has_reasoning = reasoning_path.exists()
        rows.append({
            "id": item["id"],
            "images": [
                {"bytes": (dataset_dir / path).read_bytes(), "path": path}
                for path in item["images"]
            ],
            "table_html": (reasoning_path if has_reasoning else html_path).read_text(encoding="utf-8"),
            "has_reasoning": has_reasoning,
            "num_images": item["num_images"],
        })
    features = Features({
        "id": Value("string"),
        "images": Sequence(Image()),
        "table_html": Value("string"),
        "has_reasoning": Value("bool"),
        "num_images": Value("int32"),
    })
    return Dataset.from_list(rows, features=features)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload rendered table HTML dataset to HuggingFace.")
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--repo-id", default="tungedng2710/table_html")
    parser.add_argument("--token", default=None, help="HF token; optional if already logged in")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Upload only the first N rows")
    parser.add_argument("--fix-card-only", action="store_true", help="Only upload corrected dataset card")
    parser.add_argument("--data-pattern", default="data/train-*-of-*.parquet")
    parser.add_argument(
        "--max-shard-size",
        default="2048MB",
        help="Smaller shards avoid nested image embedding issues on large datasets.",
    )
    args = parser.parse_args()

    if args.token:
        login(token=args.token)
    if args.fix_card_only:
        metadata = json.loads((args.dataset_dir / "metadata.json").read_text(encoding="utf-8"))
        upload_dataset_card(args.repo_id, len(metadata) if args.limit is None else args.limit, args.data_pattern)
        return

    metadata = json.loads((args.dataset_dir / "metadata.json").read_text(encoding="utf-8"))
    upload_dataset_card(args.repo_id, len(metadata) if args.limit is None else args.limit, args.data_pattern)
    dataset = build_dataset(args.dataset_dir, limit=args.limit)
    try:
        dataset.push_to_hub(args.repo_id, private=args.private, max_shard_size=args.max_shard_size)
    finally:
        upload_dataset_card(args.repo_id, len(dataset), args.data_pattern)


if __name__ == "__main__":
    main()
