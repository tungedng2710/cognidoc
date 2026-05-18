"""Dummy parser processors that preserve the intended workflow shape."""

from __future__ import annotations

from .models import (
    CuratedPage,
    ElementType,
    LayoutRegion,
    PageLayoutGraph,
    ParsedElement,
)
from .tools_manager import OCRToolManager


class PageIterator:
    """Yield curated pages in document order."""

    def iter_pages(self, pages: list[CuratedPage]) -> list[CuratedPage]:
        return sorted(pages, key=lambda page: page.page_index)


class LayoutDetector:
    """Detect page layout through the configured OCR tool manager."""

    def __init__(self, tool_manager: OCRToolManager | None = None, tool_name: str | None = None) -> None:
        self.tool_manager = tool_manager or OCRToolManager()
        self.tool_name = tool_name

    def detect(self, session_id: str, page: CuratedPage) -> PageLayoutGraph:
        return self.tool_manager.analyze_layout(session_id=session_id, page=page, tool_name=self.tool_name)


class OCRTextBlockProcessor:
    """OCR and paragraph reconstruction processor."""

    def __init__(self, tool_manager: OCRToolManager | None = None, tool_name: str | None = None) -> None:
        self.tool_manager = tool_manager or OCRToolManager()
        self.tool_name = tool_name

    def process(self, page: CuratedPage, region: LayoutRegion) -> ParsedElement:
        return self.tool_manager.recognize_text(session_id="", page=page, region=region, tool_name=self.tool_name)


class TableRecognitionProcessor:
    """Table structure and logical cell processor."""

    def __init__(self, tool_manager: OCRToolManager | None = None, tool_name: str | None = None) -> None:
        self.tool_manager = tool_manager or OCRToolManager()
        self.tool_name = tool_name

    def process(self, page: CuratedPage, region: LayoutRegion) -> ParsedElement:
        return self.tool_manager.detect_table(session_id="", page=page, region=region, tool_name=self.tool_name)


class FigureProcessor:
    """Figure, chart, and caption processor."""

    def __init__(self, tool_manager: OCRToolManager | None = None, tool_name: str | None = None) -> None:
        self.tool_manager = tool_manager or OCRToolManager()
        self.tool_name = tool_name

    def process(self, page: CuratedPage, region: LayoutRegion) -> ParsedElement:
        return self.tool_manager.detect_figure(session_id="", page=page, region=region, tool_name=self.tool_name)


class RegionTypeRouter:
    """Dispatch layout regions to the processor matching their type."""

    def __init__(
        self,
        text_processor: OCRTextBlockProcessor | None = None,
        table_processor: TableRecognitionProcessor | None = None,
        figure_processor: FigureProcessor | None = None,
        tool_manager: OCRToolManager | None = None,
    ) -> None:
        shared_tool_manager = tool_manager or OCRToolManager()
        self.text_processor = text_processor or OCRTextBlockProcessor(shared_tool_manager)
        self.table_processor = table_processor or TableRecognitionProcessor(shared_tool_manager)
        self.figure_processor = figure_processor or FigureProcessor(shared_tool_manager)

    def process(self, page: CuratedPage, region: LayoutRegion) -> ParsedElement:
        if region.element_type in {ElementType.TEXT, ElementType.HEADER, ElementType.FOOTER}:
            return self.text_processor.process(page, region)
        if region.element_type == ElementType.TABLE:
            return self.table_processor.process(page, region)
        if region.element_type in {ElementType.FIGURE, ElementType.CHART}:
            return self.figure_processor.process(page, region)
        raise ValueError(f"Unsupported region type: {region.element_type}")
