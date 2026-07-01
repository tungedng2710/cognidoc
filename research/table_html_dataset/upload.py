import argparse
import json
from pathlib import Path

from datasets import Dataset, Features, Image, Sequence, Value
from huggingface_hub import login
from tqdm import tqdm


def build_dataset(dataset_dir: Path) -> Dataset:
    metadata = json.loads((dataset_dir / "metadata.json").read_text(encoding="utf-8"))
    rows = []
    for item in tqdm(metadata, desc="Preparing HF rows"):
        rows.append({
            "id": item["id"],
            "images": [str(dataset_dir / path) for path in item["images"]],
            "table_html": (dataset_dir / item["table_html"]).read_text(encoding="utf-8"),
            "num_images": item["num_images"],
        })
    features = Features({
        "id": Value("string"),
        "images": Sequence(Image()),
        "table_html": Value("string"),
        "num_images": Value("int32"),
    })
    return Dataset.from_list(rows, features=features)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload rendered table HTML dataset to HuggingFace.")
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--repo-id", default="tungedng2710/table_html")
    parser.add_argument("--token", default=None, help="HF token; optional if already logged in")
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args()

    if args.token:
        login(token=args.token)
    dataset = build_dataset(args.dataset_dir)
    dataset.push_to_hub(args.repo_id, private=args.private)


if __name__ == "__main__":
    main()
