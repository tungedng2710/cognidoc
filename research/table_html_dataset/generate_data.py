import argparse
import json
import random
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from playwright.sync_api import sync_playwright
from tqdm import tqdm


PAGE_WIDTH = 1200
PAGE_HEIGHT = 1600
SPLIT_HEIGHT = 1500


def read_html(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TableStructureParser(HTMLParser):
    STRUCTURAL_TAGS = {"table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col"}
    KEEP_ATTRS = {"rowspan", "colspan"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.table_depth = 0
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self.table_depth += 1
        if not self.table_depth:
            return
        if tag in {"style", "script"}:
            self.skip_depth += 1
            return
        if self.skip_depth or tag not in self.STRUCTURAL_TAGS:
            return
        kept_attrs = []
        for name, value in attrs:
            name = name.lower()
            if name in self.KEEP_ATTRS and value and value != "1":
                kept_attrs.append(f'{name}="{value}"')
        attr_text = f" {' '.join(kept_attrs)}" if kept_attrs else ""
        self.parts.append(f"<{tag}{attr_text}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self.table_depth:
            return
        if tag in {"style", "script"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if not self.skip_depth and tag in self.STRUCTURAL_TAGS:
            self.parts.append(f"</{tag}>")
        if tag == "table":
            self.table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.table_depth and not self.skip_depth:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.parts.append(text)


def structural_table_html(html: str) -> str:
    parser = TableStructureParser()
    parser.feed(html)
    table_html = "".join(parser.parts).strip()
    if not table_html:
        raise ValueError("HTML label does not contain a <table> structure")
    return table_html


def wrap_html(table_html: str) -> str:
    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ margin: 32px; background: white; font-family: Arial, Helvetica, sans-serif; }}
    table {{ border-collapse: collapse; width: max-content; max-width: none; color: #111; }}
    th, td {{ border: 1px solid #333; padding: 6px 10px; font-size: 18px; line-height: 1.25; vertical-align: top; }}
    th {{ font-weight: 700; background: #f1f3f5; }}
    caption {{ caption-side: top; font-weight: 700; font-size: 22px; margin-bottom: 10px; }}
  </style>
</head>
<body>{table_html}</body>
</html>
"""


def degrade_image(image: Image.Image, noise_std: float, blur_radius: float) -> Image.Image:
    image = image.convert("RGB")
    if blur_radius > 0:
        image = image.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    if noise_std > 0:
        arr = np.asarray(image).astype(np.int16)
        noise = np.random.normal(0, noise_std, arr.shape).astype(np.int16)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        image = Image.fromarray(arr, "RGB")
    return image


def render_html(page, html: str, output_prefix: Path, noise_std: float, blur_radius: float) -> list[str]:
    page.set_viewport_size({"width": PAGE_WIDTH, "height": PAGE_HEIGHT})
    page.set_content(wrap_html(html), wait_until="networkidle")
    table = page.locator("table").first
    box = table.bounding_box()
    if box is None:
        raise ValueError("HTML does not contain a renderable <table> element")

    full_height = int(box["y"] + box["height"] + 40)
    page.set_viewport_size({"width": PAGE_WIDTH, "height": min(max(full_height, 300), 6000)})

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        page.screenshot(path=tmp.name, full_page=True)
        image = Image.open(tmp.name).convert("RGB")

    image_paths = []
    if image.height > SPLIT_HEIGHT:
        split_at = image.height // 2
        crops = [image.crop((0, 0, image.width, split_at)), image.crop((0, split_at, image.width, image.height))]
    else:
        crops = [image]

    for idx, crop in enumerate(crops):
        crop = degrade_image(crop, noise_std=noise_std, blur_radius=blur_radius)
        suffix = f"_part{idx + 1}" if len(crops) > 1 else ""
        out_path = output_prefix.with_name(f"{output_prefix.name}{suffix}.png")
        crop.save(out_path)
        image_paths.append(str(out_path))
    return image_paths


def generate_dataset(input_dir: Path, output_dir: Path, noise_std: float, blur_radius: float, seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    image_dir = output_dir / "images"
    html_dir = output_dir / "table_html"
    image_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)

    html_files = sorted(input_dir.glob("*.html")) + sorted(input_dir.glob("*.htm")) + sorted(input_dir.glob("*.txt"))
    metadata = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        for idx, html_path in enumerate(tqdm(html_files, desc="Generating dataset")):
            sample_id = f"sample_{idx:06d}"
            html = read_html(html_path)
            label_html = structural_table_html(html)
            saved_html = html_dir / f"{sample_id}.html"
            saved_html.write_text(label_html, encoding="utf-8")
            image_paths = render_html(page, html, image_dir / sample_id, noise_std, blur_radius)
            metadata.append({
                "id": sample_id,
                "source_html": str(html_path),
                "images": [str(Path(p).relative_to(output_dir)) for p in image_paths],
                "table_html": str(saved_html.relative_to(output_dir)),
                "num_images": len(image_paths),
            })
        browser.close()

    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render table HTML files into degraded table images.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Folder containing table HTML files")
    parser.add_argument("--output-dir", type=Path, required=True, help="Dataset output folder")
    parser.add_argument("--noise-std", type=float, default=6.0, help="Gaussian noise standard deviation")
    parser.add_argument("--blur-radius", type=float, default=0.45, help="Gaussian blur radius")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    generate_dataset(args.input_dir, args.output_dir, args.noise_std, args.blur_radius, args.seed)


if __name__ == "__main__":
    main()
