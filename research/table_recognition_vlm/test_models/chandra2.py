from transformers import AutoModelForImageTextToText, AutoProcessor
from chandra.model.hf import generate_hf
from chandra.model.schema import BatchInputItem
from chandra.prompts import OCR_PROMPT
from PIL import Image, ImageDraw
from pathlib import Path
from html.parser import HTMLParser
from collections import Counter
from math import sqrt
from bs4 import BeautifulSoup
import argparse
import numpy as np
import torch


MAX_IMAGE_PIXELS = 3072 * 2048
MAX_UPSCALE_FACTOR = 3.0
RULING_DARK_THRESHOLD = 160
RULING_MIN_ROW_DENSITY = 0.07
RULING_MIN_PROMINENCE = 5.0
RULING_MIN_SPAN_RATIO = 0.30

TABLE_PROMPT = f"""{OCR_PROMPT}

The image has already been cropped by layout detection and contains exactly one
physical table. Transcribe the entire crop as one HTML <table>. Keep titles,
notes, form fields, and full-width bands inside that table as rows and cells.
Do not split the crop into document sections or multiple tables. Do not output
anything outside the table. Ignore watermarks overlaid on or behind the table;
do not transcribe watermark text, logos, stamps, or graphics into table cells.
Do not confuse watermarks with legitimate cell content or filled form marks.
Treat dotted, dashed, faint, or broken ruling lines as real table borders. Use
them to separate rows and cells, but never transcribe the dots or dashes as text.
The table may be sparse or form-like, with irregular merged cells, multi-level
sections, and large blank regions. Preserve that geometry with accurate rowspan
and colspan instead of forcing every visual row to have the same cell divisions.
A partial ruling line divides only the columns it crosses. If a horizontal line
stops at a vertical border, preserve adjacent cells that continue through it as
row-spanning cells; do not extend the line through those cells. Keep blank merged
regions as explicit empty cells.
""".strip()


class TableColumnValidator(HTMLParser):
    """Count each HTML table row's effective columns, including cell spans."""

    def __init__(self):
        super().__init__()
        self.tables = []
        self._table_rows = None
        self._current_count = None
        self._current_column = 0
        self._active_rowspans = {}

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table_rows = []
            self._active_rowspans = {}
        elif tag == "tr" and self._table_rows is not None:
            self._current_count = 0
            self._current_column = 0
        elif tag in {"td", "th"} and self._current_count is not None:
            attributes = dict(attrs)
            try:
                colspan = int(attributes.get("colspan", "1"))
            except ValueError:
                colspan = 1
            try:
                rowspan = int(attributes.get("rowspan", "1"))
            except ValueError:
                rowspan = 1

            colspan = max(1, colspan)
            rowspan = max(1, rowspan)
            while self._active_rowspans.get(self._current_column, 0) > 0:
                self._current_column += 1

            cell_columns = range(
                self._current_column, self._current_column + colspan
            )
            if rowspan > 1:
                for column in cell_columns:
                    self._active_rowspans[column] = rowspan

            self._current_column += colspan
            self._current_count = max(self._current_count, self._current_column)

    def handle_endtag(self, tag):
        if tag == "tr" and self._current_count is not None:
            if self._active_rowspans:
                self._current_count = max(
                    self._current_count, max(self._active_rowspans) + 1
                )
            self._table_rows.append(self._current_count)
            self._current_count = None
            self._active_rowspans = {
                column: remaining_rows - 1
                for column, remaining_rows in self._active_rowspans.items()
                if remaining_rows > 1
            }
        elif tag == "table" and self._table_rows is not None:
            self.tables.append(self._table_rows)
            self._table_rows = None
            self._active_rowspans = {}


def detect_horizontal_rulings(image: Image.Image) -> list[tuple[int, int, int]]:
    """Find long, thin horizontal rules, including dotted/partial rules."""

    gray = np.asarray(image.convert("L"))
    dark = gray < RULING_DARK_THRESHOLD
    row_counts = dark.sum(axis=1)
    height, width = dark.shape
    max_gap = max(4, round(width * 0.006))
    min_span = round(width * RULING_MIN_SPAN_RATIO)
    min_dark_pixels = max(20, round(width * 0.03))
    segments = []

    for y in range(3, height - 3):
        count = int(row_counts[y])
        if count < width * RULING_MIN_ROW_DENSITY:
            continue
        if count < row_counts[y - 1] or count < row_counts[y + 1]:
            continue

        neighboring_counts = np.concatenate(
            (row_counts[y - 3 : y], row_counts[y + 1 : y + 4])
        )
        background_count = max(float(np.median(neighboring_counts)), 1.0)
        if count / background_count < RULING_MIN_PROMINENCE:
            continue

        dark_x = np.flatnonzero(dark[y])
        if dark_x.size == 0:
            continue
        split_points = np.flatnonzero(np.diff(dark_x) > max_gap) + 1
        groups = np.split(dark_x, split_points)
        for group in groups:
            if group.size < min_dark_pixels:
                continue
            x0, x1 = int(group[0]), int(group[-1])
            span = x1 - x0 + 1
            if span < min_span:
                continue
            if group.size / span < RULING_MIN_ROW_DENSITY:
                continue
            segments.append((x0, y, x1))

    return segments


def prepare_table_image(
    image: Image.Image,
) -> tuple[Image.Image, list[tuple[int, int, int]]]:
    """Upscale a table crop and reinforce detected ruling segments."""

    image = image.convert("RGB")
    ruling_segments = detect_horizontal_rulings(image)
    pixel_count = image.width * image.height
    scale = min(
        MAX_UPSCALE_FACTOR,
        sqrt(MAX_IMAGE_PIXELS / pixel_count),
    )
    if scale <= 1.0:
        prepared = image.copy()
        scale = 1.0
    else:
        prepared = image.resize(
            (int(image.width * scale), int(image.height * scale)),
            resample=Image.Resampling.LANCZOS,
        )

    draw = ImageDraw.Draw(prepared)
    line_width = max(1, round(scale))
    for x0, y, x1 in ruling_segments:
        draw.line(
            (
                round(x0 * scale),
                round(y * scale),
                round(x1 * scale),
                round(y * scale),
            ),
            fill="black",
            width=line_width,
        )

    return prepared, ruling_segments


def validate_table_columns(html: str) -> None:
    validator = TableColumnValidator()
    validator.feed(html)
    if not validator.tables:
        print("No HTML tables were found in the model output.")
        return

    for table_number, rows in enumerate(validator.tables, start=1):
        if not rows:
            print(f"Warning: table {table_number} contains no rows.")
            continue

        expected_columns = Counter(rows).most_common(1)[0][0]
        invalid_rows = [
            (row_number, count)
            for row_number, count in enumerate(rows, start=1)
            if count != expected_columns
        ]
        if invalid_rows:
            details = ", ".join(
                f"row {row_number}: {count}"
                for row_number, count in invalid_rows
            )
            print(
                f"Warning: table {table_number} has a dominant width of "
                f"{expected_columns} effective columns; mismatches: {details}"
            )
        else:
            print(
                f"Validated table {table_number}: {len(rows)} rows with "
                f"{expected_columns} effective columns each."
            )


def normalize_single_physical_table(raw_html: str) -> str:
    """Join Chandra layout blocks that belong to one cropped physical table."""

    parsed = BeautifulSoup(raw_html, "html.parser")
    source_tables = parsed.find_all("table")
    if not source_tables:
        return raw_html.strip()

    validator = TableColumnValidator()
    validator.feed(raw_html)
    row_widths = [width for table in validator.tables for width in table]
    grid_width = Counter(row_widths).most_common(1)[0][0]

    top_level_blocks = parsed.find_all("div", recursive=False)
    if not top_level_blocks:
        if len(source_tables) == 1:
            return str(source_tables[0])
        top_level_blocks = list(parsed.children)

    output = BeautifulSoup("", "html.parser")
    table = output.new_tag("table", border="1")
    tbody = output.new_tag("tbody")
    table.append(tbody)

    for block in top_level_blocks:
        if getattr(block, "name", None) == "table":
            nested_table = block
        else:
            nested_table = getattr(block, "find", lambda *_a, **_k: None)(
                "table"
            )
        if nested_table is not None:
            for row in list(nested_table.find_all("tr", recursive=False)):
                tbody.append(row.extract())
            for section in nested_table.find_all(["thead", "tbody", "tfoot"]):
                for row in list(section.find_all("tr", recursive=False)):
                    tbody.append(row.extract())
            continue

        get_text = getattr(block, "get_text", None)
        if get_text is None or not get_text(" ", strip=True):
            continue

        label = block.get("data-label", "")
        cell_name = "th" if label == "Section-Header" else "td"
        row = output.new_tag("tr")
        cell = output.new_tag(cell_name, colspan=str(grid_width))
        content = block.find(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p"], recursive=True
        )
        if content is None:
            cell.string = get_text(" ", strip=True)
        else:
            for child in list(content.contents):
                cell.append(child.extract())
        row.append(cell)
        tbody.append(row)

    output.append(table)
    return str(table)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse a document image with Chandra OCR 2."
    )
    parser.add_argument(
        "image",
        type=Path,
        help="Path to the input document image.",
    )
    parser.add_argument(
        "--save-preprocessed",
        action="store_true",
        help="Save the resized, line-reinforced image beside the input image.",
    )
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"input image does not exist or is not a file: {args.image}")
    return args


def main() -> None:
    args = parse_args()

    model = AutoModelForImageTextToText.from_pretrained(
        "datalab-to/chandra-ocr-2",
        dtype=torch.bfloat16,
        device_map="auto",
    )
    model.eval()
    model.processor = AutoProcessor.from_pretrained(
        "datalab-to/chandra-ocr-2"
    )
    model.processor.tokenizer.padding_side = "left"

    with Image.open(args.image) as source_image:
        source_size = source_image.size
        table_image, ruling_segments = prepare_table_image(source_image)
    print(
        f"Input image resized from {source_size} to {table_image.size}; "
        f"reinforced {len(ruling_segments)} horizontal ruling segments"
    )
    if args.save_preprocessed:
        preprocessed_path = args.image.with_name(
            f"{args.image.stem}_preprocessed.png"
        )
        table_image.save(preprocessed_path)
        print(f"Preprocessed image saved to {preprocessed_path}")

    batch = [BatchInputItem(image=table_image, prompt=TABLE_PROMPT)]
    result = generate_hf(batch, model, max_output_tokens=12384)[0]
    html = normalize_single_physical_table(result.raw)

    output_path = args.image.with_suffix(".html")
    output_path.write_text(html, encoding="utf-8")
    validate_table_columns(html)
    print(f"Result saved to {output_path}")


if __name__ == "__main__":
    main()
