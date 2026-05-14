"""High-level parser workflow scaffold."""

from __future__ import annotations

from .models import CuratedDocumentSession, CuratedPage, PageRepresentation, ParserResult, ParsedElement
from .processors import LayoutDetector, PageIterator, RegionTypeRouter
from .storage import SessionMetadataStore


class PageAssembler:
    """Assemble processed elements into page markdown and HTML."""

    def assemble(self, session_id: str, page: CuratedPage, elements: list[ParsedElement]) -> PageRepresentation:
        ordered_elements = sorted(elements, key=lambda element: element.reading_order)
        markdown = "\n\n".join(element.markdown for element in ordered_elements if element.markdown)
        html = "\n".join(element.html for element in ordered_elements if element.html)
        return PageRepresentation(
            session_id=session_id,
            page_index=page.page_index,
            elements=ordered_elements,
            markdown=markdown,
            html=html,
            metadata={"image_path": page.image_path, "element_count": len(ordered_elements)},
        )


class ParserWorkflow:
    """Coordinate the parser from curated pages to persisted structured output."""

    def __init__(
        self,
        page_iterator: PageIterator | None = None,
        layout_detector: LayoutDetector | None = None,
        router: RegionTypeRouter | None = None,
        assembler: PageAssembler | None = None,
        metadata_store: SessionMetadataStore | None = None,
    ) -> None:
        self.page_iterator = page_iterator or PageIterator()
        self.layout_detector = layout_detector or LayoutDetector()
        self.router = router or RegionTypeRouter()
        self.assembler = assembler or PageAssembler()
        self.metadata_store = metadata_store or SessionMetadataStore()

    def parse_session(self, session: CuratedDocumentSession) -> ParserResult:
        self.metadata_store.save_session(session)
        pages = [self.parse_page(session.session_id, page) for page in self.page_iterator.iter_pages(session.pages)]
        result = ParserResult(
            session_id=session.session_id,
            pages=pages,
            markdown="\n\n".join(page.markdown for page in pages),
            html="\n".join(page.html for page in pages),
            metadata={"page_count": len(pages), **session.metadata},
        )
        self.metadata_store.save_parser_result(result)
        return result

    def parse_page(self, session_id: str, page: CuratedPage) -> PageRepresentation:
        layout_graph = self.layout_detector.detect(session_id=session_id, page=page)
        elements = [self.router.process(page, region) for region in layout_graph.regions]
        page_representation = self.assembler.assemble(session_id=session_id, page=page, elements=elements)
        self.metadata_store.save_page_representation(page_representation)
        return page_representation
