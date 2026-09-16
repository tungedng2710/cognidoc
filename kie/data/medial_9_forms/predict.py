#!/usr/bin/env python3
"""Submit the medical-form PDFs to the NuExtract demo API."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-extract the medical 9 forms through the FastAPI demo."
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv(
            "NUEXTRACT_DEMO_API", "http://127.0.0.1:8000/api/extract"
        ),
    )
    parser.add_argument("--pdf-dir", type=Path, default=ROOT / "pdfs")
    parser.add_argument("--template-dir", type=Path, default=ROOT / "templates")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "predictions")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--thinking", action="store_true")
    parser.add_argument("--instructions", default="")
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing prediction files"
    )
    return parser.parse_args()


async def extract_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    api_url: str,
    pdf_path: Path,
    template_path: Path,
    output_path: Path,
    thinking: bool,
    instructions: str,
) -> tuple[str, dict[str, Any]]:
    async with semaphore:
        response = await client.post(
            api_url,
            files={
                "document": (
                    pdf_path.name,
                    pdf_path.read_bytes(),
                    "application/pdf",
                ),
                "template": (
                    template_path.name,
                    template_path.read_bytes(),
                    "application/json",
                ),
            },
            data={
                "thinking": str(thinking).lower(),
                "instructions": instructions,
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text[:1000]
            raise RuntimeError(
                f"{pdf_path.name}: API returned HTTP {response.status_code}: {detail}"
            ) from exc

        payload = response.json()
        if "result" not in payload:
            raise RuntimeError(f"{pdf_path.name}: API response has no 'result' field")

        temporary_path = output_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(payload["result"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(output_path)
        return pdf_path.stem, payload.get("metadata", {})


async def run(args: argparse.Namespace) -> int:
    if args.concurrency < 1:
        raise SystemExit("--concurrency must be at least 1")

    pdf_paths = sorted(args.pdf_dir.glob("*.pdf"))
    if not pdf_paths:
        raise SystemExit(f"No PDF files found in {args.pdf_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(args.concurrency)
    jobs = []
    skipped = 0

    async with httpx.AsyncClient(timeout=args.timeout) as client:
        for pdf_path in pdf_paths:
            template_path = args.template_dir / f"{pdf_path.stem}.template.json"
            output_path = args.output_dir / f"{pdf_path.stem}.json"
            if not template_path.is_file():
                raise SystemExit(f"Missing template for {pdf_path.name}: {template_path}")
            if output_path.exists() and not args.force:
                print(f"SKIP  {pdf_path.name} (prediction already exists)")
                skipped += 1
                continue

            jobs.append(
                asyncio.create_task(
                    extract_one(
                        client,
                        semaphore,
                        args.api_url,
                        pdf_path,
                        template_path,
                        output_path,
                        args.thinking,
                        args.instructions,
                    )
                )
            )

        failures = 0
        for job in asyncio.as_completed(jobs):
            try:
                name, metadata = await job
                pages = metadata.get("pages", "?")
                seconds = metadata.get("elapsed_ms", 0) / 1000
                print(f"OK    {name}.pdf ({pages} pages, {seconds:.1f}s)")
            except Exception as exc:
                failures += 1
                print(f"ERROR {exc}")

    completed = len(jobs) - failures
    print(
        f"\nCompleted: {completed}  Skipped: {skipped}  Failed: {failures}  "
        f"Output: {args.output_dir}"
    )
    return 1 if failures else 0


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
