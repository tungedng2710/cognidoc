"""Parser-facing storage facade for the session database."""

from __future__ import annotations

from pathlib import Path

from src.database import SQLiteSessionDatabase

from .models import CuratedDocumentSession, PageRepresentation, ParserResult


class InMemorySessionDatabase(SQLiteSessionDatabase):
    """Compatibility adapter backed by an in-memory SQLite session database."""

    def __init__(self) -> None:
        super().__init__(":memory:")


class SessionMetadataStore:
    """Storage facade used by the parser workflow."""

    def __init__(self, database: SQLiteSessionDatabase | str | Path | None = None) -> None:
        if database is None:
            self.database = InMemorySessionDatabase()
        elif isinstance(database, SQLiteSessionDatabase):
            self.database = database
        else:
            self.database = SQLiteSessionDatabase(database)

    def save_session(self, session: CuratedDocumentSession) -> None:
        self.database.save_session(session)

    def save_page_representation(self, page: PageRepresentation) -> None:
        self.database.save_page(page)

    def save_parser_result(self, result: ParserResult) -> None:
        self.database.save_parser_result(result)
