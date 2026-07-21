from transformers import AutoModelForImageTextToText, AutoProcessor
from chandra.model.hf import generate_hf
from chandra.model.schema import BatchInputItem
from chandra.output import parse_markdown
from chandra.prompts import OCR_LAYOUT_PROMPT
from PIL import Image
from pathlib import Path
from html.parser import HTMLParser
from collections import Counter
from math import sqrt
import torch


IMAGE_PATH = Path(
    "/root/tungn197/cognidoc/asssets/test_samples/page-62_cropped.png"
)
MAX_IMAGE_PIXELS = 3072 * 2048

DENSE_TABLE_PROMPT = OCR_LAYOUT_PROMPT + """

Pay special attention to complex and dense tables anywhere in the document.
Preserve non-table content normally, but prioritize accurate table structure
and cell transcription over visual simplification.

Additional table requirements:
- Determine the logical row and column grid from borders, alignment, spacing,
  and repeated header patterns before producing the table HTML.
- Reconstruct complete tables; do not flatten, summarize, or omit cells.
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
- Before responding, internally verify each table against its own header grid
  and check that no cell has shifted into a neighboring column.
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


model = AutoModelForImageTextToText.from_pretrained(
    "datalab-to/chandra-ocr-2",
    dtype=torch.bfloat16,
    device_map="auto",
)
model.eval()
model.processor = AutoProcessor.from_pretrained("datalab-to/chandra-ocr-2")
model.processor.tokenizer.padding_side = "left"

with Image.open(IMAGE_PATH) as source_image:
    table_image = upscale_for_dense_table(source_image)

batch = [BatchInputItem(image=table_image, prompt=DENSE_TABLE_PROMPT)]

result = generate_hf(batch, model, max_output_tokens=12384)[0]
markdown = parse_markdown(result.raw)
output_path = Path(__file__).with_name("chandra2_result.md")
output_path.write_text(markdown, encoding="utf-8")
validate_table_columns(markdown)
print(f"Result saved to {output_path}")
