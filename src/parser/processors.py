"""Dummy parser processors that preserve the intended workflow shape."""

from __future__ import annotations

from .models import (
    BoundingBox,
    CuratedPage,
    ElementType,
    LayoutRegion,
    PageLayoutGraph,
    ParsedElement,
)


class PageIterator:
    """Yield curated pages in document order."""

    def iter_pages(self, pages: list[CuratedPage]) -> list[CuratedPage]:
        return sorted(pages, key=lambda page: page.page_index)


class LayoutDetector:
    """Placeholder layout detector with deterministic dummy regions."""

    def detect(self, session_id: str, page: CuratedPage) -> PageLayoutGraph:
        regions = [
            LayoutRegion(
                region_id=f"p{page.page_index}-text-1",
                element_type=ElementType.TEXT,
                bbox=BoundingBox(x=0.05, y=0.08, width=0.9, height=0.2),
                reading_order=1,
            ),
            LayoutRegion(
                region_id=f"p{page.page_index}-table-1",
                element_type=ElementType.TABLE,
                bbox=BoundingBox(x=0.05, y=0.32, width=0.9, height=0.28),
                reading_order=2,
            ),
            LayoutRegion(
                region_id=f"p{page.page_index}-figure-1",
                element_type=ElementType.FIGURE,
                bbox=BoundingBox(x=0.1, y=0.66, width=0.8, height=0.24),
                reading_order=3,
            ),
        ]
        edges = [(regions[index].region_id, regions[index + 1].region_id) for index in range(len(regions) - 1)]
        return PageLayoutGraph(session_id=session_id, page_index=page.page_index, regions=regions, edges=edges)


class OCRTextBlockProcessor:
    """Placeholder OCR and paragraph reconstruction processor."""

    def process(self, page: CuratedPage, region: LayoutRegion) -> ParsedElement:
        text = f"Dummy text block for page {page.page_index}."
        return ParsedElement(
            element_id=region.region_id,
            element_type=region.element_type,
            page_index=page.page_index,
            reading_order=region.reading_order,
            markdown=text,
            html=f"<p>{text}</p>",
            text=text,
            bbox=region.bbox,
            confidence=region.confidence,
            metadata={"processor": self.__class__.__name__, "image_path": page.image_path},
        )


class TableRecognitionProcessor:
    """Placeholder table structure and logical cell processor."""

    def process(self, page: CuratedPage, region: LayoutRegion) -> ParsedElement:
        table_rows = [["Header A", "Header B"], ["Value A", "Value B"]]
        markdown = "| Header A | Header B |\n| --- | --- |\n| Value A | Value B |"
        html = "<table><tr><th>Header A</th><th>Header B</th></tr><tr><td>Value A</td><td>Value B</td></tr></table>"
        return ParsedElement(
            element_id=region.region_id,
            element_type=region.element_type,
            page_index=page.page_index,
            reading_order=region.reading_order,
            markdown=markdown,
            html=html,
            data={"rows": table_rows, "cells": []},
            bbox=region.bbox,
            confidence=region.confidence,
            metadata={"processor": self.__class__.__name__, "image_path": page.image_path},
        )


class FigureProcessor:
    """Placeholder figure, chart, and caption processor."""

    def process(self, page: CuratedPage, region: LayoutRegion) -> ParsedElement:
        summary = f"Dummy visual summary for {region.element_type} on page {page.page_index}."
        return ParsedElement(
            element_id=region.region_id,
            element_type=region.element_type,
            page_index=page.page_index,
            reading_order=region.reading_order,
            markdown=f"![{summary}]({page.image_path})",
            html=f'<figure><img src="{page.image_path}" alt="{summary}"><figcaption>{summary}</figcaption></figure>',
            text=summary,
            data={"summary": summary, "caption": None},
            bbox=region.bbox,
            confidence=region.confidence,
            metadata={"processor": self.__class__.__name__, "image_path": page.image_path},
        )


class RegionTypeRouter:
    """Dispatch layout regions to the processor matching their type."""

    def __init__(
        self,
        text_processor: OCRTextBlockProcessor | None = None,
        table_processor: TableRecognitionProcessor | None = None,
        figure_processor: FigureProcessor | None = None,
    ) -> None:
        self.text_processor = text_processor or OCRTextBlockProcessor()
        self.table_processor = table_processor or TableRecognitionProcessor()
        self.figure_processor = figure_processor or FigureProcessor()

    def process(self, page: CuratedPage, region: LayoutRegion) -> ParsedElement:
        if region.element_type in {ElementType.TEXT, ElementType.HEADER, ElementType.FOOTER}:
            return self.text_processor.process(page, region)
        if region.element_type == ElementType.TABLE:
            return self.table_processor.process(page, region)
        if region.element_type in {ElementType.FIGURE, ElementType.CHART}:
            return self.figure_processor.process(page, region)
        raise ValueError(f"Unsupported region type: {region.element_type}")
