# MonkeyOCR document parser

A production-shaped FastAPI application with a responsive web frontend for
parsing images and PDFs through a MonkeyOCRv2 vLLM endpoint.

## Start

```bash
conda run -n ai pip install -r requirements.txt
conda run -n ai python app.py
```

Open <http://127.0.0.1:8000>. API documentation is available at
<http://127.0.0.1:8000/docs>.

## Configuration

| Variable | Default |
| --- | --- |
| `MONKEYOCR_BASE_URL` | Hosted endpoint ending in `/v1` |
| `MONKEYOCR_MODEL` | `MonkeyOCRv2` |
| `MONKEYOCR_PROMPT` | Official end-to-end parsing prompt |
| `MAX_UPLOAD_MB` | `30` |
| `MAX_PDF_PAGES` | `20` |
| `OCR_CONCURRENCY` | `3` |
| `OCR_TIMEOUT_SECONDS` | `300` |
| `HOST` / `PORT` | `127.0.0.1` / `8000` |

The backend validates uploads, renders PDFs to page images, processes pages in
parallel with bounded concurrency, and keeps page order in the combined output.
