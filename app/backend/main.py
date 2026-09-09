from __future__ import annotations

import ast
import asyncio
import base64
import json
import os
import re
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from time import perf_counter

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
SAMPLE_IMAGE = ROOT / "test_samples" / "page-62.png"

API_BASE_URL = os.getenv(
    "MONKEYOCR_BASE_URL",
    "https://8890--main--frontier--idp-lab.coder.vts-ai.space/v1",
).rstrip("/")
MODEL = os.getenv("MONKEYOCR_MODEL", "MonkeyOCRv2")
PROMPT = os.getenv(
    "MONKEYOCR_PROMPT",
    "List the document elements in reading order, including their categories, "
    "coordinates, and the content of each element.",
)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "30")) * 1024 * 1024
MAX_PAGES = int(os.getenv("MAX_PDF_PAGES", "20"))
MAX_IMAGE_SIDE = int(os.getenv("MAX_IMAGE_SIDE", "3200"))
MAX_PREVIEW_SIDE = int(os.getenv("MAX_PREVIEW_SIDE", "1200"))
OCR_CONCURRENCY = int(os.getenv("OCR_CONCURRENCY", "3"))
REQUEST_TIMEOUT = float(os.getenv("OCR_TIMEOUT_SECONDS", "300"))

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/bmp", "image/tiff"}
PDF_TYPE = "application/pdf"
ALLOWED_TYPES = IMAGE_TYPES | {PDF_TYPE}


class LayoutElement(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)
    label: str
    content: str


class PageResult(BaseModel):
    page_number: int
    markdown: str
    raw: str
    elements: list[LayoutElement]
    image_url: str


class ParseResponse(BaseModel):
    filename: str
    page_count: int
    source_page_count: int
    selected_pages: list[int]
    elapsed_seconds: float
    content: str
    pages: list[str]
    page_results: list[PageResult]


class PagePreview(BaseModel):
    page_number: int
    image_url: str


class PreviewResponse(BaseModel):
    filename: str
    page_count: int
    pages: list[PagePreview]


class HealthResponse(BaseModel):
    status: str
    model: str
    upstream: str


def _normalize_image(image: Image.Image, max_side: int = MAX_IMAGE_SIDE) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return image


def _image_page_count(data: bytes) -> int:
    try:
        with Image.open(BytesIO(data)) as source:
            # JPEG/MPO and animated WebP can expose auxiliary frames that are not
            # document pages. Only TIFF frames use the multi-page image workflow.
            page_count = int(getattr(source, "n_frames", 1)) if source.format == "TIFF" else 1
            if page_count > MAX_PAGES:
                raise HTTPException(
                    status_code=422,
                    detail=f"The image has {page_count} frames; the limit is {MAX_PAGES}.",
                )
            return page_count
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="The uploaded image is invalid or corrupted.") from exc


def _render_image_pages(
    data: bytes, page_numbers: list[int], max_side: int
) -> list[tuple[int, Image.Image]]:
    try:
        with Image.open(BytesIO(data)) as source:
            rendered = []
            for page_number in page_numbers:
                source.seek(page_number - 1)
                rendered.append((page_number, _normalize_image(source.copy(), max_side)))
            return rendered
    except (UnidentifiedImageError, OSError, EOFError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="The uploaded image is invalid or corrupted.") from exc


def _open_pdf(data: bytes):
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(data)
        page_count = len(document)
        if page_count == 0:
            document.close()
            raise HTTPException(status_code=422, detail="The PDF contains no pages.")
        if page_count > MAX_PAGES:
            document.close()
            raise HTTPException(
                status_code=422,
                detail=f"The PDF has {page_count} pages; the limit is {MAX_PAGES}.",
            )
        return document
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="The uploaded PDF is invalid, encrypted, or unsupported.",
        ) from exc


def _render_pdf_pages(data: bytes, page_numbers: list[int], max_side: int) -> list[tuple[int, Image.Image]]:
    document = _open_pdf(data)
    try:
        rendered: list[tuple[int, Image.Image]] = []
        for page_number in page_numbers:
            page = document[page_number - 1]
            try:
                width, height = page.get_size()
                scale = min(2.0, max_side / max(width, height))
                image = page.render(scale=scale).to_pil()
                rendered.append((page_number, _normalize_image(image, max_side)))
            finally:
                page.close()
        return rendered
    finally:
        document.close()


def _pdf_page_count(data: bytes) -> int:
    document = _open_pdf(data)
    try:
        return len(document)
    finally:
        document.close()


def _image_data_uri(image: Image.Image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=3)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _preview_data_uri(image: Image.Image) -> str:
    preview = image.copy()
    if max(preview.size) > MAX_PREVIEW_SIDE:
        preview.thumbnail((MAX_PREVIEW_SIDE, MAX_PREVIEW_SIDE), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    preview.save(buffer, format="JPEG", quality=82, optimize=True)
    preview.close()
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _parse_page_selection(selection: str | None, page_count: int) -> list[int]:
    if not selection or not selection.strip():
        return list(range(1, page_count + 1))

    selected: set[int] = set()
    try:
        for token in selection.split(","):
            token = token.strip()
            if not token:
                continue
            if "-" in token:
                start_text, end_text = token.split("-", 1)
                start, end = int(start_text), int(end_text)
                if start > end:
                    raise ValueError
                selected.update(range(start, end + 1))
            else:
                selected.add(int(token))
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid page selection. Use page numbers such as 1,3-5.",
        ) from exc

    if not selected:
        raise HTTPException(status_code=422, detail="Select at least one page to OCR.")
    invalid = sorted(page for page in selected if page < 1 or page > page_count)
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Selected page {invalid[0]} is outside this {page_count}-page document.",
        )
    return sorted(selected)


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    match = re.fullmatch(r"```(?:json|python)?\s*(.*?)\s*```", stripped, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else stripped


def _parse_layout(content: str) -> list[LayoutElement]:
    """Parse MonkeyOCR's JSON/Python-list response without evaluating code."""
    candidate = _strip_code_fence(content)
    start, end = candidate.find("["), candidate.rfind("]")
    if start == -1 or end <= start:
        return []
    candidate = candidate[start : end + 1]

    parsed = None
    for loader in (json.loads, ast.literal_eval):
        try:
            parsed = loader(candidate)
            break
        except (json.JSONDecodeError, ValueError, SyntaxError):
            continue
    if not isinstance(parsed, list):
        return []

    elements: list[LayoutElement] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox") or item.get("box") or item.get("coordinates")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        try:
            coords = [max(0.0, min(1000.0, float(value))) for value in bbox]
        except (TypeError, ValueError):
            continue
        if coords[2] <= coords[0] or coords[3] <= coords[1]:
            continue
        label = str(item.get("label") or item.get("category") or item.get("type") or "Text")
        text = str(item.get("content") or item.get("text") or "").strip()
        elements.append(LayoutElement(bbox=coords, label=label.strip() or "Text", content=text))
    return elements


def _elements_to_markdown(elements: list[LayoutElement], fallback: str) -> str:
    if not elements:
        return fallback.strip()

    blocks: list[str] = []
    for element in elements:
        content = element.content.strip()
        if not content:
            continue
        label = re.sub(r"[\s_-]+", " ", element.label.strip().lower())
        if label in {"title", "document title"}:
            block = content if content.startswith("#") else f"# {content}"
        elif label in {"section header", "heading", "header"}:
            block = content if content.startswith("#") else f"## {content}"
        elif label in {"formula", "equation", "display formula"}:
            block = content if content.startswith(("$", "\\[")) else f"$$\n{content}\n$$"
        elif label in {"figure", "image", "picture", "chart"}:
            block = f"> **{element.label}:** {content}"
        else:
            block = content
        blocks.append(block)
    return "\n\n".join(blocks).strip()


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_TYPES:
        await file.close()
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a PNG, JPEG, WebP, BMP, TIFF, or PDF.",
        )
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"The upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )
    return data, content_type


async def _ocr_page(client: httpx.AsyncClient, image: Image.Image, page_number: int) -> str:
    payload = {
        "model": MODEL,
        "temperature": 0,
        "max_tokens": 8192,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _image_data_uri(image)}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    }

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty model response")
            return content
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            last_error = exc
            retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code in {
                429, 500, 502, 503, 504
            }
            if not retryable or attempt == 2:
                break
            await asyncio.sleep(0.5 * (2**attempt))
        except (KeyError, TypeError, ValueError) as exc:
            last_error = exc
            break

    detail = f"OCR failed on page {page_number}."
    if isinstance(last_error, httpx.HTTPStatusError):
        detail += f" Upstream returned HTTP {last_error.response.status_code}."
    elif isinstance(last_error, (httpx.TimeoutException, httpx.NetworkError)):
        detail += " The OCR service is unavailable or timed out."
    else:
        detail += " The OCR service returned an unexpected response."
    raise HTTPException(status_code=502, detail=detail)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ocr_client = httpx.AsyncClient(
        base_url=API_BASE_URL,
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        headers={"Authorization": f"Bearer {os.getenv('MONKEYOCR_API_KEY', 'not-required')}"},
    )
    yield
    await app.state.ocr_client.aclose()


app = FastAPI(
    title="MonkeyOCR Document Parser",
    version="1.1.0",
    description="Image and PDF parsing backed by MonkeyOCRv2.",
    lifespan=lifespan,
)


@app.get("/api/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    try:
        response = await request.app.state.ocr_client.get("/models", timeout=10)
        response.raise_for_status()
        models = {item.get("id") for item in response.json().get("data", [])}
        if MODEL not in models:
            return HealthResponse(status="degraded", model=MODEL, upstream="model unavailable")
        return HealthResponse(status="ok", model=MODEL, upstream="connected")
    except Exception:
        return HealthResponse(status="degraded", model=MODEL, upstream="unreachable")


@app.post("/api/preview", response_model=PreviewResponse)
async def preview_document(file: UploadFile = File(...)) -> PreviewResponse:
    data, content_type = await _read_upload(file)
    filename = Path(file.filename or "document").name
    if content_type == PDF_TYPE:
        page_count = await asyncio.to_thread(_pdf_page_count, data)
        rendered = await asyncio.to_thread(
            _render_pdf_pages, data, list(range(1, page_count + 1)), MAX_PREVIEW_SIDE
        )
    else:
        page_count = await asyncio.to_thread(_image_page_count, data)
        rendered = await asyncio.to_thread(
            _render_image_pages, data, list(range(1, page_count + 1)), MAX_PREVIEW_SIDE
        )

    try:
        pages = [
            PagePreview(page_number=number, image_url=_preview_data_uri(image))
            for number, image in rendered
        ]
    finally:
        for _, image in rendered:
            image.close()
    return PreviewResponse(filename=filename, page_count=page_count, pages=pages)


@app.post("/api/parse", response_model=ParseResponse)
async def parse_document(
    request: Request,
    file: UploadFile = File(...),
    selected_pages: str | None = Form(default=None),
) -> ParseResponse:
    data, content_type = await _read_upload(file)
    filename = Path(file.filename or "document").name

    if content_type == PDF_TYPE:
        source_page_count = await asyncio.to_thread(_pdf_page_count, data)
        page_numbers = _parse_page_selection(selected_pages, source_page_count)
        rendered = await asyncio.to_thread(_render_pdf_pages, data, page_numbers, MAX_IMAGE_SIDE)
    else:
        source_page_count = await asyncio.to_thread(_image_page_count, data)
        page_numbers = _parse_page_selection(selected_pages, source_page_count)
        rendered = await asyncio.to_thread(
            _render_image_pages, data, page_numbers, MAX_IMAGE_SIDE
        )

    started = perf_counter()
    semaphore = asyncio.Semaphore(max(1, OCR_CONCURRENCY))

    async def parse_page(page_number: int, image: Image.Image) -> PageResult:
        async with semaphore:
            try:
                raw, image_url = await asyncio.gather(
                    _ocr_page(request.app.state.ocr_client, image, page_number),
                    asyncio.to_thread(_preview_data_uri, image),
                )
                elements = _parse_layout(raw)
                return PageResult(
                    page_number=page_number,
                    markdown=_elements_to_markdown(elements, raw),
                    raw=raw,
                    elements=elements,
                    image_url=image_url,
                )
            finally:
                image.close()

    results = await asyncio.gather(*(parse_page(number, image) for number, image in rendered))
    markdown_pages = [result.markdown for result in results]
    combined = markdown_pages[0] if len(results) == 1 else "\n\n".join(
        f"<!-- Page {result.page_number} -->\n\n{result.markdown}" for result in results
    )

    return ParseResponse(
        filename=filename,
        page_count=len(results),
        source_page_count=source_page_count,
        selected_pages=page_numbers,
        elapsed_seconds=round(perf_counter() - started, 2),
        content=combined,
        pages=markdown_pages,
        page_results=results,
    )


@app.get("/sample")
async def sample() -> Response:
    if SAMPLE_IMAGE.exists():
        return FileResponse(SAMPLE_IMAGE, media_type="image/png", filename="page-62.png")

    image = Image.new("RGB", (1000, 1300), "white")
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("DejaVuSans.ttf", 42)
        body_font = ImageFont.truetype("DejaVuSans.ttf", 28)
    except OSError:
        title_font = body_font = ImageFont.load_default()
    draw.text((90, 100), "MONKEYOCR SAMPLE", fill="#186f4b", font=body_font)
    draw.text((90, 175), "Document intelligence report", fill="#151714", font=title_font)
    draw.line((90, 225, 910, 225), fill="#d8d7d0", width=3)
    draw.text((90, 285), "Revenue", fill="#151714", font=body_font)
    draw.text((720, 285), "$12,500", fill="#151714", font=body_font)
    draw.text(
        (90, 350),
        "Net income increased by 18% this quarter.",
        fill="#151714",
        font=body_font,
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image.close()
    return Response(content=buffer.getvalue(), media_type="image/png")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
