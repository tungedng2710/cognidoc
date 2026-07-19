"""Evaluate the trained image-to-table-HTML adapter on the dataset test split."""

import argparse
import html
import json
import os
import re
import time
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


DEFAULT_DATASET_ID = "tungedng2710/table_html_with_reasoning"
DEFAULT_MODEL = "qwen35_2b_table_html_lora"
PROMPT = (
    "Convert the table in the provided image into structural HTML. Preserve all visible "
    "text, empty cells, row and column order, and rowspan and colspan attributes. If there "
    "are multiple images, they are consecutive parts of the same table. Return only the "
    "complete <table>...</table> markup, with no reasoning, explanation, or markdown."
)


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument("--dataset-config", default=None)
    parser.add_argument("--split", default="test")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", default="test_predictions.jsonl")
    parser.add_argument("--summary", default="test_metrics.json")
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--max-new-tokens", type=int, default=8192)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--load-in-16bit", action="store_true")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--log-every", type=int, default=10)
    return parser.parse_args()


def extract_table(value):
    """Extract only the final complete table, tolerating reasoning and code fences."""
    if not isinstance(value, str):
        return ""
    lower = value.lower()
    start = lower.find("<table")
    end = lower.rfind("</table>")
    return value[start : end + 8].strip() if start >= 0 and end >= start else ""


def normalized_html(value):
    value = re.sub(r">\s+<", "><", value.strip())
    return re.sub(r"\s+", " ", value)


def edit_similarity(left, right):
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0
    # Two-row Levenshtein keeps memory bounded for long table strings.
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (a != b)))
        previous = current
    return 1.0 - previous[-1] / max(len(left), len(right))


class CellTokenizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.tokens = []

    def handle_starttag(self, tag, attrs):
        self.tokens.append(f"<{tag}>")
        for key, value in sorted(attrs):
            self.tokens.extend([key, value or ""])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.tokens.append(f"</{tag}>")

    def handle_endtag(self, tag):
        self.tokens.append(f"</{tag}>")

    def handle_data(self, data):
        self.tokens.extend(data)

    def handle_entityref(self, name):
        self.tokens.extend(html.unescape(f"&{name};"))

    def handle_charref(self, name):
        self.tokens.extend(html.unescape(f"&#{name};"))


class TableNode:
    def __init__(self, tag, colspan=None, rowspan=None, content=None, children=None):
        self.tag = tag
        self.colspan = colspan
        self.rowspan = rowspan
        self.content = content or []
        self.children = children or []


def _node_count(node):
    return 1 + sum(_node_count(child) for child in node.children)


def _table_tree(markup, structure_only=False):
    from lxml import html as lxml_html

    table = lxml_html.fromstring(markup)
    if table.tag.lower() != "table":
        found = table.xpath(".//table")
        if not found:
            raise ValueError("no table element")
        table = found[0]

    allowed = {"table", "thead", "tbody", "tfoot", "tr", "td", "th"}

    def convert(element):
        tag = element.tag.lower() if isinstance(element.tag, str) else ""
        children = [convert(child) for child in element if
                    isinstance(child.tag, str) and child.tag.lower() in allowed]
        if tag not in allowed:
            raise ValueError(f"unexpected structural element {tag}")
        content = []
        if tag in {"td", "th"} and not structure_only:
            raw = (element.text or "") + "".join(
                lxml_html.tostring(child, encoding="unicode") for child in element
            )
            tokenizer = CellTokenizer()
            tokenizer.feed(raw)
            content = tokenizer.tokens
        return TableNode(tag, element.get("colspan", "1"), element.get("rowspan", "1"),
                         content, children)

    return convert(table)


def teds(reference, prediction, structure_only=False):
    """PubTabNet-style Tree Edit Distance Similarity in [0, 1]."""
    from apted import APTED, Config

    class TableConfig(Config):
        def rename(self, left, right):
            if left.tag != right.tag:
                return 1.0
            if left.tag in {"td", "th"}:
                if left.colspan != right.colspan or left.rowspan != right.rowspan:
                    return 1.0
                return 0.0 if structure_only else 1.0 - edit_similarity(
                    left.content, right.content
                )
            return 0.0

        def children(self, node):
            return node.children

    if not prediction:
        return 0.0
    try:
        ref_tree = _table_tree(reference, structure_only)
        pred_tree = _table_tree(prediction, structure_only)
        distance = APTED(ref_tree, pred_tree, TableConfig()).compute_edit_distance()
        return max(0.0, 1.0 - distance / max(_node_count(ref_tree), _node_count(pred_tree)))
    except Exception:
        return 0.0


def load_completed(path):
    completed = {}
    if not path.exists():
        return completed
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                row = json.loads(line)
                completed[row["index"]] = row
            except (json.JSONDecodeError, KeyError):
                print(f"Ignoring incomplete output line {line_number}")
    return completed


def aggregate(rows, elapsed_seconds):
    keys = ["teds", "teds_structure", "html_edit_similarity", "exact_match",
            "valid_table"]
    result = {key: sum(float(row[key]) for row in rows) / len(rows) for key in keys}
    result.update({
        "samples": len(rows),
        "elapsed_seconds": elapsed_seconds,
        "samples_per_second": len(rows) / elapsed_seconds if elapsed_seconds else None,
        "by_merged_cells": {},
    })
    for merged in (False, True):
        subset = [row for row in rows if bool(row["has_merged_cells"]) == merged]
        if subset:
            result["by_merged_cells"][str(merged).lower()] = {
                "samples": len(subset),
                "teds": sum(row["teds"] for row in subset) / len(subset),
                "teds_structure": sum(row["teds_structure"] for row in subset) / len(subset),
            }
    return result


def main():
    args = arguments()
    if args.max_samples is not None and args.max_samples <= 0:
        raise ValueError("--max-samples must be positive")
    if args.temperature < 0:
        raise ValueError("--temperature cannot be negative")

    # Required for the currently installed Unsloth/Qwen3.5 combination.
    os.environ.setdefault("UNSLOTH_COMPILE_DISABLE", "1")
    import torch
    import unsloth  # noqa: F401 - must precede transformers imports
    from datasets import load_dataset
    from transformers import StoppingCriteriaList, StopStringCriteria
    from unsloth import FastVisionModel

    dataset = load_dataset(args.dataset_id, args.dataset_config, split=args.split)
    if args.max_samples is not None:
        dataset = dataset.select(range(min(args.max_samples, len(dataset))))
    if len(dataset) == 0:
        raise ValueError("Selected test set is empty")

    model, processor = FastVisionModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_new_tokens + 2048,
        load_in_4bit=not args.load_in_16bit,
        load_in_16bit=args.load_in_16bit,
    )
    FastVisionModel.for_inference(model)
    model.eval()

    output_path = Path(args.output)
    summary_path = Path(args.summary)
    previous = load_completed(output_path) if args.resume else {}
    mode = "a" if args.resume else "w"
    started = time.monotonic()

    with output_path.open(mode, encoding="utf-8", buffering=1) as output:
        for index, sample in enumerate(dataset):
            if index in previous:
                continue
            images = [image.convert("RGB") for image in sample["images"]]
            content = [{"type": "text", "text": PROMPT}]
            content.extend({"type": "image", "image": image} for image in images)
            messages = [{"role": "user", "content": content}]
            prompt = processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = processor(text=prompt, images=images, return_tensors="pt")
            inputs = {key: value.to(model.device) for key, value in inputs.items()}
            generate_kwargs = {
                "max_new_tokens": args.max_new_tokens,
                "do_sample": args.temperature > 0,
                "use_cache": True,
                "stopping_criteria": StoppingCriteriaList([
                    StopStringCriteria(
                        getattr(processor, "tokenizer", processor), "</table>"
                    )
                ]),
            }
            if args.temperature > 0:
                generate_kwargs["temperature"] = args.temperature
            with torch.inference_mode():
                generated = model.generate(**inputs, **generate_kwargs)
            new_tokens = generated[0, inputs["input_ids"].shape[1]:]
            raw_prediction = processor.decode(new_tokens, skip_special_tokens=True)
            prediction = extract_table(raw_prediction)
            reference = extract_table(sample["table_html"])
            row = {
                "index": index,
                "id": sample["id"],
                "prediction": prediction,
                "raw_prediction": raw_prediction,
                "reference": reference,
                "teds": teds(reference, prediction),
                "teds_structure": teds(reference, prediction, structure_only=True),
                "html_edit_similarity": edit_similarity(normalized_html(reference),
                                                          normalized_html(prediction)),
                "exact_match": normalized_html(reference) == normalized_html(prediction),
                "valid_table": bool(prediction),
                "has_merged_cells": sample["has_merged_cells"],
                "num_rows": sample["num_rows"],
                "num_cols": sample["num_cols"],
                "num_cells": sample["num_cells"],
                "num_images": sample["num_images"],
                "generated_tokens": int(new_tokens.numel()),
            }
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            previous[index] = row
            done = len(previous)
            if done % args.log_every == 0 or done == len(dataset):
                partial = aggregate(list(previous.values()), time.monotonic() - started)
                print(json.dumps({"progress": f"{done}/{len(dataset)}", **partial}, indent=2))

    rows = [previous[index] for index in range(len(dataset))]
    summary = aggregate(rows, time.monotonic() - started)
    summary.update({"dataset": args.dataset_id, "split": args.split, "model": args.model})
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
