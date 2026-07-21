"""Evaluate Chandra OCR 2 on the table_html_with_reasoning test split.

Token accuracy is defined here as one minus the token-level Levenshtein
distance divided by the longer token sequence. HTML tags (including their
attributes) and non-whitespace text pieces are tokens. This makes insertions
and deletions count, unlike position-only token accuracy.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import torch
from apted import APTED, Config
from bs4 import BeautifulSoup
from chandra.model.hf import generate_hf
from chandra.model.schema import BatchInputItem
from datasets import load_dataset
from lxml import etree, html as lxml_html
from PIL import Image
from rapidfuzz.distance import Levenshtein
from tqdm.auto import tqdm
from transformers import AutoModelForImageTextToText, AutoProcessor

from chandra2 import (
    TABLE_PROMPT,
    normalize_single_physical_table,
    prepare_table_image,
)


DATASET_NAME = "tungedng2710/table_html_with_reasoning"
MODEL_NAME = "datalab-to/chandra-ocr-2"
HTML_TOKEN_RE = re.compile(r"<[^>]+>|[^<\s]+")
CELL_TAGS = {"td", "th"}


def normalize_html(html: str) -> str:
    """Make superficial HTML differences less important to token accuracy."""

    soup = BeautifulSoup(html or "", "html.parser")
    table = soup.find("table")
    if table is None:
        return " ".join((html or "").split())

    for tag in table.find_all(True):
        tag.attrs = dict(sorted(tag.attrs.items()))
    return str(table)


def html_tokens(html: str) -> list[str]:
    return HTML_TOKEN_RE.findall(normalize_html(html))


def token_accuracy(prediction: str, reference: str) -> float:
    """Normalized token edit similarity in [0, 1]."""

    pred_tokens = html_tokens(prediction)
    ref_tokens = html_tokens(reference)
    denominator = max(len(pred_tokens), len(ref_tokens))
    if denominator == 0:
        return 1.0
    distance = Levenshtein.distance(pred_tokens, ref_tokens)
    return max(0.0, 1.0 - distance / denominator)


@dataclass
class TableNode:
    tag: str
    rowspan: int = 1
    colspan: int = 1
    content: tuple[str, ...] = ()
    children: tuple["TableNode", ...] = ()


class TableTreeConfig(Config):
    """APTED costs used by the PubTabNet-style TEDS metric."""

    def rename(self, node1: TableNode, node2: TableNode) -> float:
        if node1.tag != node2.tag:
            return 1.0
        if node1.tag in CELL_TAGS:
            if (node1.rowspan, node1.colspan) != (node2.rowspan, node2.colspan):
                return 1.0
            denominator = max(len(node1.content), len(node2.content))
            if denominator == 0:
                return 0.0
            return Levenshtein.distance(node1.content, node2.content) / denominator
        return 0.0


def _positive_int(value: Any) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _cell_content_tokens(element: etree._Element) -> tuple[str, ...]:
    # TEDS compares the serialized content inside a cell, not its outer td/th.
    parts: list[str] = []
    if element.text:
        parts.append(element.text)
    for child in element:
        parts.append(etree.tostring(child, encoding="unicode", method="html"))
    return tuple(HTML_TOKEN_RE.findall("".join(parts)))


def _to_table_node(element: etree._Element) -> TableNode:
    tag = str(element.tag).lower()
    children = tuple(
        _to_table_node(child)
        for child in element
        if isinstance(child.tag, str)
    )
    if tag in CELL_TAGS:
        return TableNode(
            tag=tag,
            rowspan=_positive_int(element.get("rowspan", 1)),
            colspan=_positive_int(element.get("colspan", 1)),
            content=_cell_content_tokens(element),
            children=children,
        )
    return TableNode(tag=tag, children=children)


def _parse_table(html: str) -> TableNode | None:
    try:
        document = lxml_html.fromstring(html or "")
    except (etree.ParserError, ValueError):
        return None
    tables = document.xpath("self::table | .//table")
    return _to_table_node(tables[0]) if tables else None


def _tree_size(node: TableNode) -> int:
    return 1 + sum(_tree_size(child) for child in node.children)


def teds_score(prediction: str, reference: str) -> float:
    """Compute tree-edit-distance similarity for the first HTML table."""

    pred_tree = _parse_table(prediction)
    ref_tree = _parse_table(reference)
    if ref_tree is None:
        return 1.0 if pred_tree is None else 0.0
    if pred_tree is None:
        return 0.0
    distance = APTED(pred_tree, ref_tree, TableTreeConfig()).compute_edit_distance()
    tree_size = max(_tree_size(pred_tree), _tree_size(ref_tree))
    return max(0.0, 1.0 - distance / tree_size)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=DATASET_NAME)
    parser.add_argument("--split", default="test")
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--max-output-tokens", type=int, default=12384)
    parser.add_argument("--limit", type=int, help="evaluate only the first N rows")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("chandra2_test_predictions.jsonl"),
        help="append-only per-sample output; existing completed indices are resumed",
    )
    parser.add_argument(
        "--no-preprocess",
        action="store_true",
        help="skip the resizing and ruling-line reinforcement from chandra2.py",
    )
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def _load_completed(path: Path) -> dict[int, dict[str, Any]]:
    completed: dict[int, dict[str, Any]] = {}
    if not path.exists():
        return completed
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                completed[int(record["index"])] = record
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {error}") from error
    return completed


def _batched(items: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _first_image(example: dict[str, Any], index: int) -> Image.Image:
    images = example.get("images")
    if not images:
        raise ValueError(f"dataset row {index} has no image")
    image = images[0]
    if not isinstance(image, Image.Image):
        raise TypeError(f"dataset row {index} image decoded as {type(image).__name__}")
    return image.convert("RGB")


def _print_summary(records: Iterable[dict[str, Any]]) -> None:
    scored = [record for record in records if "teds" in record]
    if not scored:
        print("No successfully scored samples.")
        return
    mean_teds = sum(float(record["teds"]) for record in scored) / len(scored)
    mean_token = sum(float(record["token_accuracy"]) for record in scored) / len(scored)
    print(f"Scored samples: {len(scored)}")
    print(f"TEDS:           {mean_teds:.6f}")
    print(f"Token accuracy: {mean_token:.6f}")


def main() -> None:
    args = parse_args()
    dataset = load_dataset(args.dataset, split=args.split)
    if args.limit is not None:
        dataset = dataset.select(range(min(args.limit, len(dataset))))
    print(
        f"Loaded {len(dataset)} samples from {args.dataset!r} "
        f"split {args.split!r}"
    )

    completed = _load_completed(args.output)
    # Keep indices rather than examples here: indexing a datasets.Image column
    # decodes the image, and retaining every row would consume substantial RAM.
    pending = [index for index in range(len(dataset)) if index not in completed]
    print(f"Resuming {len(completed)} completed samples; {len(pending)} remain")

    if pending:
        model = AutoModelForImageTextToText.from_pretrained(
            args.model,
            dtype=torch.bfloat16,
            device_map="auto",
        )
        model.eval()
        model.processor = AutoProcessor.from_pretrained(args.model)
        model.processor.tokenizer.padding_side = "left"

        args.output.parent.mkdir(parents=True, exist_ok=True)
        progress = tqdm(total=len(pending), desc="Evaluating", unit="table")
        with args.output.open("a", encoding="utf-8") as output_stream:
            for indices in _batched(pending, args.batch_size):
                rows = [(index, dataset[index]) for index in indices]
                inputs: list[BatchInputItem] = []
                for index, example in rows:
                    image = _first_image(example, index)
                    if not args.no_preprocess:
                        image, _ = prepare_table_image(image)
                    inputs.append(BatchInputItem(image=image, prompt=TABLE_PROMPT))

                results = generate_hf(
                    inputs,
                    model,
                    max_output_tokens=args.max_output_tokens,
                )
                if len(results) != len(rows):
                    raise RuntimeError(
                        f"model returned {len(results)} results "
                        f"for {len(rows)} inputs"
                    )

                for (index, example), result in zip(rows, results):
                    prediction = normalize_single_physical_table(result.raw)
                    reference = example["table_html"]
                    record = {
                        "index": index,
                        "id": example.get("id", str(index)),
                        "prediction": prediction,
                        "reference": reference,
                        "teds": teds_score(prediction, reference),
                        "token_accuracy": token_accuracy(prediction, reference),
                    }
                    output_stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                    output_stream.flush()
                    completed[index] = record
                    progress.update(1)
        progress.close()

    selected_records = (
        completed[index]
        for index in range(len(dataset))
        if index in completed
    )
    _print_summary(selected_records)
    print(f"Per-sample results: {args.output.resolve()}")


if __name__ == "__main__":
    main()
