"""Session metadata storage scaffold."""

from __future__ import annotations

from .models import PageRepresentation, ParsedElement


class InMemorySessionDatabase:
    """Minimal storage adapter for testing parser flow without a real database."""

    def __init__(self) -> None:
        self.pages: dict[tuple[str, int], PageRepresentation] = {}
        self.elements: dict[str, ParsedElement] = {}

    def save_page(self, page: PageRepresentation) -> None:
        self.pages[(page.session_id, page.page_index)] = page

    def save_elements(self, session_id: str, elements: list[ParsedElement]) -> None:
        for element in elements:
            key = f"{session_id}:{element.page_index}:{element.element_id}"
            self.elements[key] = element

    def list_pages(self, session_id: str) -> list[PageRepresentation]:
        return [
            page
            for (stored_session_id, _page_index), page in sorted(self.pages.items(), key=lambda item: item[0][1])
            if stored_session_id == session_id
        ]

    def list_elements(self, session_id: str) -> list[ParsedElement]:
        prefix = f"{session_id}:"
        return [element for key, element in sorted(self.elements.items()) if key.startswith(prefix)]


class SessionMetadataStore:
    """Storage facade used by the parser workflow."""

    def __init__(self, database: InMemorySessionDatabase | None = None) -> None:
        self.database = database or InMemorySessionDatabase()

    def save_page_representation(self, page: PageRepresentation) -> None:
        self.database.save_page(page)
        self.database.save_elements(page.session_id, page.elements)
