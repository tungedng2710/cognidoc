from io import BytesIO

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from backend.main import _elements_to_markdown, _parse_layout, _parse_page_selection, app


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (120, 80), "white").save(buffer, "PNG")
    return buffer.getvalue()


def _pdf(page_count: int = 1) -> bytes:
    buffer = BytesIO()
    pages = [Image.new("RGB", (120, 80), "white") for _ in range(page_count)]
    pages[0].save(buffer, "PDF", save_all=True, append_images=pages[1:])
    return buffer.getvalue()


def _tiff(page_count: int = 2) -> bytes:
    buffer = BytesIO()
    pages = [Image.new("RGB", (120, 80), "white") for _ in range(page_count)]
    pages[0].save(buffer, "TIFF", save_all=True, append_images=pages[1:])
    return buffer.getvalue()


def test_parse_image():
    async def upstream(request: httpx.Request) -> httpx.Response:
        content = "[{'bbox': [10, 20, 400, 80], 'label': 'Title', 'content': 'Parsed'}, " \
            "{'bbox': [10, 100, 400, 150], 'label': 'Text', 'content': 'Hello'}]"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

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
    assert response.json()["selected_pages"] == [1]
    assert response.json()["page_results"][0]["elements"][0]["bbox"] == [10.0, 20.0, 400.0, 80.0]
    assert response.json()["page_results"][0]["image_url"].startswith("data:image/jpeg;base64,")


def test_rejects_unsupported_type():
    with TestClient(app) as client:
        response = client.post(
            "/api/parse", files={"file": ("notes.txt", b"hello", "text/plain")}
        )
    assert response.status_code == 415


def test_parse_pdf():
    calls = 0

    async def upstream(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "PDF page"}}]})

    with TestClient(app) as client:
        real_client = app.state.ocr_client
        app.state.ocr_client = httpx.AsyncClient(
            transport=httpx.MockTransport(upstream), base_url="https://ocr.test/v1"
        )
        try:
            response = client.post(
                "/api/parse",
                files={"file": ("document.pdf", _pdf(3), "application/pdf")},
                data={"selected_pages": "2"},
            )
        finally:
            app.state.ocr_client = real_client

    assert response.status_code == 200
    assert response.json()["content"] == "PDF page"
    assert response.json()["page_count"] == 1
    assert response.json()["source_page_count"] == 3
    assert response.json()["selected_pages"] == [2]
    assert response.json()["page_results"][0]["page_number"] == 2
    assert calls == 1


def test_preview_pdf_pages():
    with TestClient(app) as client:
        response = client.post(
            "/api/preview", files={"file": ("document.pdf", _pdf(2), "application/pdf")}
        )

    assert response.status_code == 200
    assert response.json()["page_count"] == 2
    assert [page["page_number"] for page in response.json()["pages"]] == [1, 2]
    assert all(page["image_url"].startswith("data:image/jpeg;base64,") for page in response.json()["pages"])


def test_parse_selected_tiff_frame():
    calls = 0

    async def upstream(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "TIFF frame"}}]})

    with TestClient(app) as client:
        real_client = app.state.ocr_client
        app.state.ocr_client = httpx.AsyncClient(
            transport=httpx.MockTransport(upstream), base_url="https://ocr.test/v1"
        )
        try:
            response = client.post(
                "/api/parse",
                files={"file": ("scan.tiff", _tiff(3), "image/tiff")},
                data={"selected_pages": "2"},
            )
        finally:
            app.state.ocr_client = real_client

    assert response.status_code == 200
    assert response.json()["source_page_count"] == 3
    assert response.json()["page_results"][0]["page_number"] == 2
    assert calls == 1


def test_generated_sample_is_available():
    with TestClient(app) as client:
        response = client.get("/sample")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")


def test_page_selection_ranges_and_validation():
    assert _parse_page_selection("1,3-5,3", 5) == [1, 3, 4, 5]

    with TestClient(app) as client:
        response = client.post(
            "/api/parse",
            files={"file": ("document.pdf", _pdf(2), "application/pdf")},
            data={"selected_pages": "3"},
        )
    assert response.status_code == 422
    assert "outside" in response.json()["detail"]


def test_monkey_output_parser_supports_code_fenced_python():
    raw = """```python
    [{'bbox': [1, 2, 300, 80], 'label': 'Section-header', 'content': 'Summary'},
     {'bbox': [1, 90, 600, 180], 'label': 'Text', 'content': 'Result text'}]
    ```"""
    elements = _parse_layout(raw)

    assert len(elements) == 2
    assert _elements_to_markdown(elements, raw) == "## Summary\n\nResult text"
