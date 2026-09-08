from __future__ import annotations

import asyncio
import base64
import os
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from time import perf_counter

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel


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
OCR_CONCURRENCY = int(os.getenv("OCR_CONCURRENCY", "3"))
REQUEST_TIMEOUT = float(os.getenv("OCR_TIMEOUT_SECONDS", "300"))

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/bmp", "image/tiff"}
PDF_TYPE = "application/pdf"
ALLOWED_TYPES = IMAGE_TYPES | {PDF_TYPE}


class ParseResponse(BaseModel):
    filename: str
    page_count: int
    elapsed_seconds: float
    content: str
    pages: list[str]


class HealthResponse(BaseModel):
    status: str
    model: str
    upstream: str


def _normalize_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    if max(image.size) > MAX_IMAGE_SIDE:
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.Resampling.LANCZOS)
    return image


def _load_image(data: bytes) -> list[Image.Image]:
    try:
        with Image.open(BytesIO(data)) as source:
            return [_normalize_image(source.copy())]
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="The uploaded image is invalid or corrupted.") from exc


def _load_pdf(data: bytes) -> list[Image.Image]:
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(data)
        try:
            page_count = len(document)
            if page_count == 0:
                raise HTTPException(status_code=422, detail="The PDF contains no pages.")
            if page_count > MAX_PAGES:
                raise HTTPException(
                    status_code=422,
                    detail=f"The PDF has {page_count} pages; the limit is {MAX_PAGES}.",
                )

            pages: list[Image.Image] = []
            for index in range(page_count):
                page = document[index]
                try:
                    pages.append(_normalize_image(page.render(scale=2.0).to_pil()))
                finally:
                    page.close()
            return pages
        finally:
            document.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="The uploaded PDF is invalid, encrypted, or unsupported.",
        ) from exc


def _image_data_uri(image: Image.Image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=3)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


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
    version="1.0.0",
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


@app.post("/api/parse", response_model=ParseResponse)
async def parse_document(request: Request, file: UploadFile = File(...)) -> ParseResponse:
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_TYPES:
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

    pages = await asyncio.to_thread(_load_pdf if content_type == PDF_TYPE else _load_image, data)
    started = perf_counter()
    semaphore = asyncio.Semaphore(max(1, OCR_CONCURRENCY))

    async def parse_page(index: int, page: Image.Image) -> str:
        async with semaphore:
            try:
                return await _ocr_page(request.app.state.ocr_client, page, index + 1)
            finally:
                page.close()

    results = await asyncio.gather(*(parse_page(i, page) for i, page in enumerate(pages)))
    combined = results[0] if len(results) == 1 else "\n\n".join(
        f"<!-- Page {index} -->\n\n{content}"
        for index, content in enumerate(results, start=1)
    )

    return ParseResponse(
        filename=Path(file.filename or "document").name,
        page_count=len(results),
        elapsed_seconds=round(perf_counter() - started, 2),
        content=combined,
        pages=results,
    )


@app.get("/sample")
async def sample() -> FileResponse:
    if not SAMPLE_IMAGE.exists():
        raise HTTPException(status_code=404, detail="Sample image not found.")
    return FileResponse(SAMPLE_IMAGE, media_type="image/png", filename="page-62.png")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
