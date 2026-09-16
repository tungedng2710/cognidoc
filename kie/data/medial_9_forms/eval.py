#!/usr/bin/env python3
"""Evaluate structured JSON predictions against medical-form ground truth."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
PathPart = str | int
LeafPath = tuple[PathPart, ...]
MISSING = object()


@dataclass
class DocumentMetrics:
    document: str
    score: float
    exact_accuracy: float
    key_precision: float
    key_recall: float
    key_f1: float
    matched_leaves: int
    expected_leaves: int
    predicted_leaves: int
    missing_leaves: int
    extra_leaves: int


def normalize_string(value: str) -> str:
    """Match NuExtract's whitespace normalization for verbatim strings."""
    return re.sub(r"\s+", " ", value).strip()


def indel_similarity(left: str, right: str) -> float:
    """Normalized indel similarity: 2 * LCS / total character count."""
    left = normalize_string(left)
    right = normalize_string(right)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0

    if len(left) > len(right):
        left, right = right, left
    previous = [0] * (len(left) + 1)
    for right_character in right:
        current = [0]
        for index, left_character in enumerate(left, start=1):
            if left_character == right_character:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current
    return (2.0 * previous[-1]) / (len(left) + len(right))


def flatten_leaves(value: Any, path: LeafPath = ()) -> dict[LeafPath, Any]:
    """Flatten a JSON tree while retaining array indexes in each leaf path."""
    if isinstance(value, dict):
        if not value:
            return {path: {}}
        leaves: dict[LeafPath, Any] = {}
        for key, child in value.items():
            leaves.update(flatten_leaves(child, path + (key,)))
        return leaves
    if isinstance(value, list):
        if not value:
            return {path: []}
        leaves = {}
        for index, child in enumerate(value):
            leaves.update(flatten_leaves(child, path + (index,)))
        return leaves
    return {path: value}


def leaf_score(expected: Any, predicted: Any) -> float:
    if expected is MISSING or predicted is MISSING:
        return 0.0
    if isinstance(expected, str) and isinstance(predicted, str):
        return indel_similarity(expected, predicted)
    if isinstance(expected, bool) or isinstance(predicted, bool):
        return float(type(expected) is type(predicted) and expected == predicted)
    if isinstance(expected, (int, float)) and isinstance(predicted, (int, float)):
        return float(expected == predicted)
    return float(type(expected) is type(predicted) and expected == predicted)


def leaf_exact(expected: Any, predicted: Any) -> bool:
    if expected is MISSING or predicted is MISSING:
        return False
    if isinstance(expected, str) and isinstance(predicted, str):
        return normalize_string(expected) == normalize_string(predicted)
    return type(expected) is type(predicted) and expected == predicted


def evaluate_document(
    document: str, expected: Any, predicted: Any
) -> tuple[DocumentMetrics, float, int, int]:
    expected_leaves = flatten_leaves(expected)
    predicted_leaves = flatten_leaves(predicted)
    expected_paths = set(expected_leaves)
    predicted_paths = set(predicted_leaves)
    shared_paths = expected_paths & predicted_paths
    all_paths = expected_paths | predicted_paths

    score_sum = 0.0
    exact_count = 0
    for path in all_paths:
        expected_value = expected_leaves.get(path, MISSING)
        predicted_value = predicted_leaves.get(path, MISSING)
        score_sum += leaf_score(expected_value, predicted_value)
        exact_count += leaf_exact(expected_value, predicted_value)

    denominator = len(all_paths)
    score = score_sum / denominator if denominator else 1.0
    exact_accuracy = exact_count / denominator if denominator else 1.0
    precision = len(shared_paths) / len(predicted_paths) if predicted_paths else 0.0
    recall = len(shared_paths) / len(expected_paths) if expected_paths else 0.0
    key_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    metrics = DocumentMetrics(
        document=document,
        score=score,
        exact_accuracy=exact_accuracy,
        key_precision=precision,
        key_recall=recall,
        key_f1=key_f1,
        matched_leaves=len(shared_paths),
        expected_leaves=len(expected_paths),
        predicted_leaves=len(predicted_paths),
        missing_leaves=len(expected_paths - predicted_paths),
        extra_leaves=len(predicted_paths - expected_paths),
    )
    return metrics, score_sum, exact_count, denominator


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def path_text(path: LeafPath) -> str:
    result = ""
    for part in path:
        result += f"[{part}]" if isinstance(part, int) else ("." if result else "") + part
    return result or "$"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate JSON trees using indel similarity for strings and exact "
            "match for non-string leaves. Missing and extra leaves score zero."
        )
    )
    parser.add_argument("--ground-truth", type=Path, default=ROOT / "ground_truth")
    parser.add_argument("--predictions", type=Path, default=ROOT / "predictions")
    parser.add_argument(
        "--report",
        type=Path,
        help="Optionally save the full machine-readable evaluation report",
    )
    parser.add_argument(
        "--show-errors",
        type=int,
        default=0,
        metavar="N",
        help="Show the N lowest-scoring shared leaves per document",
    )
    return parser.parse_args()


def lowest_scoring_leaves(expected: Any, predicted: Any, limit: int) -> list[str]:
    expected_leaves = flatten_leaves(expected)
    predicted_leaves = flatten_leaves(predicted)
    rows = []
    for path in set(expected_leaves) | set(predicted_leaves):
        expected_value = expected_leaves.get(path, MISSING)
        predicted_value = predicted_leaves.get(path, MISSING)
        score = leaf_score(expected_value, predicted_value)
        if score < 1.0:
            expected_display = "<MISSING>" if expected_value is MISSING else repr(expected_value)
            predicted_display = "<MISSING>" if predicted_value is MISSING else repr(predicted_value)
            rows.append(
                (
                    score,
                    f"    {path_text(path)}: {score:.3f} | "
                    f"GT={expected_display[:90]} | PRED={predicted_display[:90]}",
                )
            )
    rows.sort(key=lambda row: (row[0], row[1]))
    return [row[1] for row in rows[:limit]]


def run(args: argparse.Namespace) -> int:
    ground_truth_paths = sorted(args.ground_truth.glob("*.json"))
    if not ground_truth_paths:
        raise SystemExit(f"No ground-truth JSON files found in {args.ground_truth}")

    document_metrics: list[DocumentMetrics] = []
    document_values: dict[str, tuple[Any, Any]] = {}
    missing_predictions: list[str] = []
    micro_score_sum = 0.0
    micro_exact_count = 0
    micro_denominator = 0

    for ground_truth_path in ground_truth_paths:
        prediction_path = args.predictions / ground_truth_path.name
        expected = load_json(ground_truth_path)
        if prediction_path.is_file():
            predicted = load_json(prediction_path)
        else:
            predicted = {}
            missing_predictions.append(ground_truth_path.name)

        metrics, score_sum, exact_count, denominator = evaluate_document(
            ground_truth_path.stem, expected, predicted
        )
        document_metrics.append(metrics)
        document_values[ground_truth_path.stem] = (expected, predicted)
        micro_score_sum += score_sum
        micro_exact_count += exact_count
        micro_denominator += denominator

    macro_score = mean(metric.score for metric in document_metrics)
    macro_exact = mean(metric.exact_accuracy for metric in document_metrics)
    macro_key_f1 = mean(metric.key_f1 for metric in document_metrics)
    micro_score = micro_score_sum / micro_denominator if micro_denominator else 0.0
    micro_exact = micro_exact_count / micro_denominator if micro_denominator else 0.0

    print(
        f"{'Document':<22} {'Score':>8} {'Exact':>8} {'Key F1':>8} "
        f"{'GT':>6} {'Pred':>6} {'Miss':>6} {'Extra':>6}"
    )
    print("-" * 79)
    for metric in document_metrics:
        print(
            f"{metric.document:<22} {metric.score:>8.3f} "
            f"{metric.exact_accuracy:>8.3f} {metric.key_f1:>8.3f} "
            f"{metric.expected_leaves:>6} {metric.predicted_leaves:>6} "
            f"{metric.missing_leaves:>6} {metric.extra_leaves:>6}"
        )
        if args.show_errors:
            expected, predicted = document_values[metric.document]
            for row in lowest_scoring_leaves(expected, predicted, args.show_errors):
                print(row)

    print("-" * 79)
    print(f"Macro score:          {macro_score:.4f}")
    print(f"Micro score:          {micro_score:.4f}")
    print(f"Macro exact accuracy: {macro_exact:.4f}")
    print(f"Micro exact accuracy: {micro_exact:.4f}")
    print(f"Macro key F1:         {macro_key_f1:.4f}")

    report = {
        "summary": {
            "documents": len(document_metrics),
            "missing_prediction_files": missing_predictions,
            "macro_score": macro_score,
            "micro_score": micro_score,
            "macro_exact_accuracy": macro_exact,
            "micro_exact_accuracy": micro_exact,
            "macro_key_f1": macro_key_f1,
        },
        "documents": [asdict(metric) for metric in document_metrics],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Report: {args.report}")

    if missing_predictions:
        print(f"Missing prediction files: {', '.join(missing_predictions)}")
        return 2
    return 0


def main() -> None:
    raise SystemExit(run(parse_args()))


if __name__ == "__main__":
    main()
