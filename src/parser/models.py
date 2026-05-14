"""Data contracts for the parser workflow scaffold."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ElementType(str, Enum):
    """Region and element categories handled by the parser."""

    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"
    CHART = "chart"
    HEADER = "header"
    FOOTER = "footer"


@dataclass(frozen=True)
class CuratedPage:
    """A page image already prepared by the curator module."""

    page_index: int
    image_path: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CuratedDocumentSession:
    """All pages belonging to the same source document."""

    session_id: str
    pages: list[CuratedPage]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BoundingBox:
    """Page-space coordinates for a detected region."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class LayoutRegion:
    """A detected page region before type-specific processing."""

    region_id: str
    element_type: ElementType
    bbox: BoundingBox
    reading_order: int
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PageLayoutGraph:
    """Layout output for one page."""

    session_id: str
    page_index: int
    regions: list[LayoutRegion]
    edges: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedElement:
    """Structured output from a type-specific region processor."""

    element_id: str
    element_type: ElementType
    page_index: int
    reading_order: int
    markdown: str = ""
    html: str = ""
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    bbox: BoundingBox | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PageRepresentation:
    """Complete page-level parser result."""

    session_id: str
    page_index: int
    elements: list[ParsedElement]
    markdown: str
    html: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParserResult:
    """Complete document-level parser result."""

    session_id: str
    pages: list[PageRepresentation]
    markdown: str
    html: str
    metadata: dict[str, Any] = field(default_factory=dict)
