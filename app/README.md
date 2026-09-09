# MonkeyOCR document parser

A production-shaped FastAPI application with a responsive web frontend for
parsing images and PDFs through a MonkeyOCRv2 vLLM endpoint.

## Start

```bash
source /media/drive-2t/miniconda3/etc/profile.d/conda.sh
conda activate tungn197
pip install -r requirements.txt
python app.py
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
| `MAX_PREVIEW_SIDE` | `1200` |
| `OCR_CONCURRENCY` | `3` |
| `OCR_TIMEOUT_SECONDS` | `300` |
| `HOST` / `PORT` | `127.0.0.1` / `8000` |

The UI prepares thumbnail previews for multi-page PDFs and TIFFs so individual
pages can be selected before OCR. The backend parses MonkeyOCR's JSON or
Python-list layout response into normalized bounding boxes and Markdown, then
returns both a rendered page image and structured elements for every selected
page. Results can be switched between a sanitized Markdown preview and an SVG
layout overlay; Markdown can also be copied or downloaded.

## API

- `POST /api/preview` accepts `file` and returns page thumbnails.
- `POST /api/parse` accepts `file` plus optional `selected_pages` such as
  `1,3-5`. Omitting it processes every page.
