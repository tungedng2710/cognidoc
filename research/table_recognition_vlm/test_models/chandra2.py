from transformers import AutoModelForImageTextToText, AutoProcessor
from chandra.model.hf import generate_hf
from chandra.model.schema import BatchInputItem
from PIL import Image
from pathlib import Path
from html.parser import HTMLParser
from collections import Counter
from math import sqrt
from bs4 import BeautifulSoup
import argparse
import torch


MAX_IMAGE_PIXELS = 3072 * 2048

DENSE_TABLE_PROMPT = """
OCR this cropped image as exactly one HTML table. The outermost rectangular
border is the boundary of one physical table. Any full-width titled or numbered
band inside that border is a merged table row, never a document section and
never a boundary between separate tables.

Your response must begin with <table> and end with </table>. Return exactly one
<table>...</table> element. Never emit text, headings, paragraphs, Markdown,
code fences, layout blocks, or additional tables outside that element.

Table requirements:
- Infer one finest-grained logical column grid for the whole outer table.
  Represent wider section rows using colspan on that same grid.
- Encode section titles as table rows and cells, not as headings outside the
  table. Encode narrative or note regions as cells with the proper colspan.
- Determine the logical row and column grid from borders, alignment, spacing,
  and repeated header patterns before producing the table HTML.
- Reconstruct the complete table; do not split, flatten, summarize, or omit it.
- Preserve every empty cell as an explicit <td></td>; never shift a value into
  an adjacent column.
- Use colspan and rowspan only when the visible structure indicates a merged
  cell. Preserve multi-level headers and nested row groups.
- Preserve all text, punctuation, decimal and thousands separators, dates,
  units, symbols, and numeric values exactly as printed.
- Do not infer, calculate, normalize, or correct values.
- Keep wrapped text inside the same cell.
- For each table, maintain a consistent effective column grid across header
  and body rows after accounting for rowspan and colspan.
- Before responding, internally verify the table against its own grid and check
  that no cell has shifted into a neighboring column.
- Only use these tags: table, thead, tbody, tr, th, td, br, b, i, strong, small,
  sup, sub, and input.
- Only use these attributes: border, colspan, rowspan, type, checked, and value.
- Do not use h1-h6, p, div, Markdown headings, or prose outside table cells.
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


def upscale_for_dense_table(image: Image.Image) -> Image.Image:
    """Increase detail when useful without exceeding Chandra's pixel cap."""

    image = image.convert("RGB")
    pixel_count = image.width * image.height
    scale = min(2.0, sqrt(MAX_IMAGE_PIXELS / pixel_count))
    if scale <= 1.0:
        return image

    return image.resize(
        (round(image.width * scale), round(image.height * scale)),
        resample=Image.Resampling.LANCZOS,
    )


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
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"input image does not exist or is not a file: {args.image}")
    return args


def main() -> None:
    args = parse_args()

    model = AutoModelForImageTextToText.from_pretrained(
        "datalab-to/chandra",
        dtype=torch.bfloat16,
        device_map="auto",
    )
    model.eval()
    model.processor = AutoProcessor.from_pretrained(
        "datalab-to/chandra"
    )
    model.processor.tokenizer.padding_side = "left"

    with Image.open(args.image) as source_image:
        table_image = upscale_for_dense_table(source_image)

    batch = [BatchInputItem(image=table_image, prompt=DENSE_TABLE_PROMPT)]
    result = generate_hf(batch, model, max_output_tokens=12384)[0]
    html = normalize_single_physical_table(result.raw)

    output_path = args.image.with_suffix(".html")
    output_path.write_text(html, encoding="utf-8")
    validate_table_columns(html)
    print(f"Result saved to {output_path}")


if __name__ == "__main__":
    main()
