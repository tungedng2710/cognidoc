from io import BytesIO

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from backend.main import app


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (120, 80), "white").save(buffer, "PNG")
    return buffer.getvalue()


def _pdf() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (120, 80), "white").save(buffer, "PDF")
    return buffer.getvalue()


def test_parse_image():
    async def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "# Parsed\n\nHello"}}]})

    with TestClient(app) as client:
        real_client = app.state.ocr_client
        mock_client = httpx.AsyncClient(
            transport=httpx.MockTransport(upstream), base_url="https://ocr.test/v1"
        )
        app.state.ocr_client = mock_client
        try:
            response = client.post(
                "/api/parse", files={"file": ("page.png", _png(), "image/png")}
            )
        finally:
            app.state.ocr_client = real_client

    assert response.status_code == 200
    assert response.json()["content"] == "# Parsed\n\nHello"
    assert response.json()["page_count"] == 1


def test_rejects_unsupported_type():
    with TestClient(app) as client:
        response = client.post(
            "/api/parse", files={"file": ("notes.txt", b"hello", "text/plain")}
        )
    assert response.status_code == 415


def test_parse_pdf():
    async def upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "PDF page"}}]})

    with TestClient(app) as client:
        real_client = app.state.ocr_client
        app.state.ocr_client = httpx.AsyncClient(
            transport=httpx.MockTransport(upstream), base_url="https://ocr.test/v1"
        )
        try:
            response = client.post(
                "/api/parse", files={"file": ("document.pdf", _pdf(), "application/pdf")}
            )
        finally:
            app.state.ocr_client = real_client

    assert response.status_code == 200
    assert response.json()["content"] == "PDF page"
    assert response.json()["page_count"] == 1
