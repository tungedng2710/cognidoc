"""SQLite-backed session database for document processing sessions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.parser.models import (
        BoundingBox,
        CuratedDocumentSession,
        PageRepresentation,
        ParserResult,
        ParsedElement,
    )


JsonDict = dict[str, Any]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


def _bbox_from_row(row: sqlite3.Row) -> BoundingBox | None:
    if row["bbox_x"] is None:
        return None
    from src.parser.models import BoundingBox

    return BoundingBox(
        x=row["bbox_x"],
        y=row["bbox_y"],
        width=row["bbox_width"],
        height=row["bbox_height"],
    )


class SQLiteSessionDatabase:
    """Persist document hierarchy, visual grounding, outputs, and extraction logs.

    The schema is intentionally explicit instead of storing one large JSON blob:
    pages own layout elements, layout elements own type-specific records, tables
    own cells, and extraction artifacts are all linked by ``session_id``.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.initialize()

    def initialize(self) -> None:
        """Create the session database schema if it does not exist."""

        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS document_sessions (
                session_id TEXT PRIMARY KEY,
                source_path TEXT,
                markdown TEXT NOT NULL DEFAULT '',
                html TEXT NOT NULL DEFAULT '',
                final_json TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                page_index INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                markdown TEXT NOT NULL DEFAULT '',
                html TEXT NOT NULL DEFAULT '',
                width REAL,
                height REAL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, page_index),
                FOREIGN KEY(session_id) REFERENCES document_sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS layout_elements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                page_index INTEGER NOT NULL,
                element_id TEXT NOT NULL,
                element_type TEXT NOT NULL,
                reading_order INTEGER NOT NULL,
                bbox_x REAL,
                bbox_y REAL,
                bbox_width REAL,
                bbox_height REAL,
                confidence REAL NOT NULL DEFAULT 1.0,
                image_path TEXT,
                markdown TEXT NOT NULL DEFAULT '',
                html TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL DEFAULT '',
                data_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, element_id),
                FOREIGN KEY(session_id, page_index) REFERENCES pages(session_id, page_index)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS text_blocks (
                session_id TEXT NOT NULL,
                element_id TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                markdown TEXT NOT NULL DEFAULT '',
                html TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(session_id, element_id),
                FOREIGN KEY(session_id, element_id) REFERENCES layout_elements(session_id, element_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS table_objects (
                session_id TEXT NOT NULL,
                element_id TEXT NOT NULL,
                markdown TEXT NOT NULL DEFAULT '',
                html TEXT NOT NULL DEFAULT '',
                data_json TEXT NOT NULL DEFAULT '{}',
                row_count INTEGER NOT NULL DEFAULT 0,
                column_count INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(session_id, element_id),
                FOREIGN KEY(session_id, element_id) REFERENCES layout_elements(session_id, element_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS table_cells (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                table_element_id TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                column_index INTEGER NOT NULL,
                row_span INTEGER NOT NULL DEFAULT 1,
                column_span INTEGER NOT NULL DEFAULT 1,
                text TEXT NOT NULL DEFAULT '',
                markdown TEXT NOT NULL DEFAULT '',
                html TEXT NOT NULL DEFAULT '',
                bbox_x REAL,
                bbox_y REAL,
                bbox_width REAL,
                bbox_height REAL,
                confidence REAL NOT NULL DEFAULT 1.0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(session_id, table_element_id, row_index, column_index),
                FOREIGN KEY(session_id, table_element_id) REFERENCES table_objects(session_id, element_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS figures (
                session_id TEXT NOT NULL,
                element_id TEXT NOT NULL,
                caption TEXT,
                summary TEXT,
                image_path TEXT,
                markdown TEXT NOT NULL DEFAULT '',
                html TEXT NOT NULL DEFAULT '',
                data_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(session_id, element_id),
                FOREIGN KEY(session_id, element_id) REFERENCES layout_elements(session_id, element_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS figure_text_links (
                session_id TEXT NOT NULL,
                figure_element_id TEXT NOT NULL,
                text_element_id TEXT NOT NULL,
                link_type TEXT NOT NULL DEFAULT 'caption',
                confidence REAL NOT NULL DEFAULT 1.0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(session_id, figure_element_id, text_element_id, link_type),
                FOREIGN KEY(session_id, figure_element_id) REFERENCES figures(session_id, element_id)
                    ON DELETE CASCADE,
                FOREIGN KEY(session_id, text_element_id) REFERENCES text_blocks(session_id, element_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS extracted_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                value_json TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES document_sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS evidence_spans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                field_name TEXT,
                element_id TEXT,
                page_index INTEGER,
                text TEXT NOT NULL DEFAULT '',
                bbox_x REAL,
                bbox_y REAL,
                bbox_width REAL,
                bbox_height REAL,
                confidence REAL NOT NULL DEFAULT 1.0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES document_sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS validation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES document_sessions(session_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS session_outputs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                output_type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES document_sessions(session_id)
                    ON DELETE CASCADE
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def save_session(self, session: CuratedDocumentSession) -> None:
        """Create or update a document session and its curated pages."""

        source_path = session.metadata.get("source_path")
        self.connection.execute(
            """
            INSERT INTO document_sessions (session_id, source_path, metadata_json)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                source_path = excluded.source_path,
                metadata_json = excluded.metadata_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (session.session_id, source_path, _json_dumps(session.metadata)),
        )
        for page in session.pages:
            self.connection.execute(
                """
                INSERT INTO pages (session_id, page_index, image_path, metadata_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, page_index) DO UPDATE SET
                    image_path = excluded.image_path,
                    metadata_json = excluded.metadata_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (session.session_id, page.page_index, page.image_path, _json_dumps(page.metadata)),
            )
        self.connection.commit()

    def save_parser_result(self, result: ParserResult) -> None:
        """Persist the document-level parser output and all page records."""

        self.connection.execute(
            """
            INSERT INTO document_sessions (session_id, markdown, html, metadata_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                markdown = excluded.markdown,
                html = excluded.html,
                metadata_json = excluded.metadata_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (result.session_id, result.markdown, result.html, _json_dumps(result.metadata)),
        )
        for page in result.pages:
            self.save_page(page, commit=False)
        self.add_session_output(result.session_id, "markdown", result.markdown)
        self.add_session_output(result.session_id, "html", result.html)
        self.connection.commit()

    def save_page(self, page: PageRepresentation, commit: bool = True) -> None:
        """Persist a parsed page and all of its layout elements."""

        image_path = str(page.metadata.get("image_path", ""))
        self.connection.execute(
            """
            INSERT INTO document_sessions (session_id)
            VALUES (?)
            ON CONFLICT(session_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            """,
            (page.session_id,),
        )
        self.connection.execute(
            """
            INSERT INTO pages (session_id, page_index, image_path, markdown, html, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, page_index) DO UPDATE SET
                image_path = excluded.image_path,
                markdown = excluded.markdown,
                html = excluded.html,
                metadata_json = excluded.metadata_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                page.session_id,
                page.page_index,
                image_path,
                page.markdown,
                page.html,
                _json_dumps(page.metadata),
            ),
        )
        self.save_elements(page.session_id, page.elements, commit=False)
        if commit:
            self.connection.commit()

    def save_elements(self, session_id: str, elements: Iterable[ParsedElement], commit: bool = True) -> None:
        """Persist layout elements and their type-specific objects."""

        for element in elements:
            self._save_element(session_id, element)
        if commit:
            self.connection.commit()

    def _save_element(self, session_id: str, element: ParsedElement) -> None:
        from src.parser.models import ElementType

        bbox = element.bbox
        metadata = dict(element.metadata)
        image_path = metadata.get("image_path")
        confidence = float(metadata.get("confidence", getattr(element, "confidence", 1.0)))
        self.connection.execute(
            """
            INSERT INTO layout_elements (
                session_id,
                page_index,
                element_id,
                element_type,
                reading_order,
                bbox_x,
                bbox_y,
                bbox_width,
                bbox_height,
                confidence,
                image_path,
                markdown,
                html,
                text,
                data_json,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, element_id) DO UPDATE SET
                page_index = excluded.page_index,
                element_type = excluded.element_type,
                reading_order = excluded.reading_order,
                bbox_x = excluded.bbox_x,
                bbox_y = excluded.bbox_y,
                bbox_width = excluded.bbox_width,
                bbox_height = excluded.bbox_height,
                confidence = excluded.confidence,
                image_path = excluded.image_path,
                markdown = excluded.markdown,
                html = excluded.html,
                text = excluded.text,
                data_json = excluded.data_json,
                metadata_json = excluded.metadata_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                session_id,
                element.page_index,
                element.element_id,
                element.element_type.value,
                element.reading_order,
                bbox.x if bbox else None,
                bbox.y if bbox else None,
                bbox.width if bbox else None,
                bbox.height if bbox else None,
                confidence,
                image_path,
                element.markdown,
                element.html,
                element.text,
                _json_dumps(element.data),
                _json_dumps(metadata),
            ),
        )

        if element.element_type in {ElementType.TEXT, ElementType.HEADER, ElementType.FOOTER}:
            self._save_text_block(session_id, element)
        elif element.element_type == ElementType.TABLE:
            self._save_table(session_id, element)
        elif element.element_type in {ElementType.FIGURE, ElementType.CHART}:
            self._save_figure(session_id, element)

    def _save_text_block(self, session_id: str, element: ParsedElement) -> None:
        self.connection.execute(
            """
            INSERT INTO text_blocks (session_id, element_id, text, markdown, html, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, element_id) DO UPDATE SET
                text = excluded.text,
                markdown = excluded.markdown,
                html = excluded.html,
                metadata_json = excluded.metadata_json
            """,
            (
                session_id,
                element.element_id,
                element.text,
                element.markdown,
                element.html,
                _json_dumps(element.metadata),
            ),
        )

    def _save_table(self, session_id: str, element: ParsedElement) -> None:
        rows = element.data.get("rows", [])
        cells = element.data.get("cells") or self._cells_from_rows(rows)
        row_count = len(rows) if isinstance(rows, list) else 0
        column_count = max((len(row) for row in rows if isinstance(row, list)), default=0)
        if cells:
            row_count = max(row_count, max(cell.get("row_index", 0) for cell in cells) + 1)
            column_count = max(column_count, max(cell.get("column_index", 0) for cell in cells) + 1)

        self.connection.execute(
            """
            INSERT INTO table_objects (
                session_id,
                element_id,
                markdown,
                html,
                data_json,
                row_count,
                column_count,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, element_id) DO UPDATE SET
                markdown = excluded.markdown,
                html = excluded.html,
                data_json = excluded.data_json,
                row_count = excluded.row_count,
                column_count = excluded.column_count,
                metadata_json = excluded.metadata_json
            """,
            (
                session_id,
                element.element_id,
                element.markdown,
                element.html,
                _json_dumps(element.data),
                row_count,
                column_count,
                _json_dumps(element.metadata),
            ),
        )
        self.connection.execute(
            "DELETE FROM table_cells WHERE session_id = ? AND table_element_id = ?",
            (session_id, element.element_id),
        )
        for cell in cells:
            bbox = cell.get("bbox") or {}
            self.connection.execute(
                """
                INSERT INTO table_cells (
                    session_id,
                    table_element_id,
                    row_index,
                    column_index,
                    row_span,
                    column_span,
                    text,
                    markdown,
                    html,
                    bbox_x,
                    bbox_y,
                    bbox_width,
                    bbox_height,
                    confidence,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    element.element_id,
                    int(cell.get("row_index", 0)),
                    int(cell.get("column_index", 0)),
                    int(cell.get("row_span", 1)),
                    int(cell.get("column_span", 1)),
                    str(cell.get("text", "")),
                    str(cell.get("markdown", cell.get("text", ""))),
                    str(cell.get("html", cell.get("text", ""))),
                    bbox.get("x"),
                    bbox.get("y"),
                    bbox.get("width"),
                    bbox.get("height"),
                    float(cell.get("confidence", 1.0)),
                    _json_dumps(cell.get("metadata", {})),
                ),
            )

    def _save_figure(self, session_id: str, element: ParsedElement) -> None:
        self.connection.execute(
            """
            INSERT INTO figures (
                session_id,
                element_id,
                caption,
                summary,
                image_path,
                markdown,
                html,
                data_json,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, element_id) DO UPDATE SET
                caption = excluded.caption,
                summary = excluded.summary,
                image_path = excluded.image_path,
                markdown = excluded.markdown,
                html = excluded.html,
                data_json = excluded.data_json,
                metadata_json = excluded.metadata_json
            """,
            (
                session_id,
                element.element_id,
                element.data.get("caption"),
                element.data.get("summary") or element.text,
                element.metadata.get("image_path"),
                element.markdown,
                element.html,
                _json_dumps(element.data),
                _json_dumps(element.metadata),
            ),
        )

    @staticmethod
    def _cells_from_rows(rows: Any) -> list[JsonDict]:
        if not isinstance(rows, list):
            return []
        cells = []
        for row_index, row in enumerate(rows):
            if not isinstance(row, list):
                continue
            for column_index, value in enumerate(row):
                cells.append(
                    {
                        "row_index": row_index,
                        "column_index": column_index,
                        "text": "" if value is None else str(value),
                    }
                )
        return cells

    def link_figure_text(
        self,
        session_id: str,
        figure_element_id: str,
        text_element_id: str,
        link_type: str = "caption",
        confidence: float = 1.0,
        metadata: JsonDict | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO figure_text_links (
                session_id,
                figure_element_id,
                text_element_id,
                link_type,
                confidence,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, figure_element_id, text_element_id, link_type)
            DO UPDATE SET
                confidence = excluded.confidence,
                metadata_json = excluded.metadata_json
            """,
            (
                session_id,
                figure_element_id,
                text_element_id,
                link_type,
                confidence,
                _json_dumps(metadata or {}),
            ),
        )
        self.connection.commit()

    def add_extracted_field(
        self,
        session_id: str,
        field_name: str,
        value: Any,
        confidence: float = 1.0,
        metadata: JsonDict | None = None,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO extracted_fields (session_id, field_name, value_json, confidence, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, field_name, _json_dumps(value), confidence, _json_dumps(metadata or {})),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def add_evidence_span(
        self,
        session_id: str,
        field_name: str | None,
        text: str,
        element_id: str | None = None,
        page_index: int | None = None,
        bbox: BoundingBox | None = None,
        confidence: float = 1.0,
        metadata: JsonDict | None = None,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO evidence_spans (
                session_id,
                field_name,
                element_id,
                page_index,
                text,
                bbox_x,
                bbox_y,
                bbox_width,
                bbox_height,
                confidence,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                field_name,
                element_id,
                page_index,
                text,
                bbox.x if bbox else None,
                bbox.y if bbox else None,
                bbox.width if bbox else None,
                bbox.height if bbox else None,
                confidence,
                _json_dumps(metadata or {}),
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def add_validation_log(
        self,
        session_id: str,
        stage: str,
        severity: str,
        message: str,
        metadata: JsonDict | None = None,
    ) -> int:
        cursor = self.connection.execute(
            """
            INSERT INTO validation_logs (session_id, stage, severity, message, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, stage, severity, message, _json_dumps(metadata or {})),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def add_session_output(
        self,
        session_id: str,
        output_type: str,
        content: str | JsonDict | list[Any],
        metadata: JsonDict | None = None,
    ) -> int:
        serialized_content = content if isinstance(content, str) else _json_dumps(content)
        cursor = self.connection.execute(
            """
            INSERT INTO session_outputs (session_id, output_type, content, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, output_type, serialized_content, _json_dumps(metadata or {})),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def save_final_json(
        self,
        session_id: str,
        output: JsonDict | list[Any],
        metadata: JsonDict | None = None,
    ) -> int:
        """Store the latest machine-readable JSON output for a session."""

        serialized_output = _json_dumps(output)
        self.connection.execute(
            """
            INSERT INTO document_sessions (session_id, final_json)
            VALUES (?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                final_json = excluded.final_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (session_id, serialized_output),
        )
        output_id = self.add_session_output(session_id, "json", serialized_output, metadata)
        self.connection.commit()
        return output_id

    def list_pages(self, session_id: str) -> list[PageRepresentation]:
        from src.parser.models import PageRepresentation

        rows = self.connection.execute(
            """
            SELECT session_id, page_index, markdown, html, metadata_json
            FROM pages
            WHERE session_id = ?
            ORDER BY page_index
            """,
            (session_id,),
        ).fetchall()
        return [
            PageRepresentation(
                session_id=row["session_id"],
                page_index=row["page_index"],
                elements=[
                    element for element in self.list_elements(session_id) if element.page_index == row["page_index"]
                ],
                markdown=row["markdown"],
                html=row["html"],
                metadata=_json_loads(row["metadata_json"], {}),
            )
            for row in rows
        ]

    def list_elements(self, session_id: str) -> list[ParsedElement]:
        from src.parser.models import ElementType, ParsedElement

        rows = self.connection.execute(
            """
            SELECT *
            FROM layout_elements
            WHERE session_id = ?
            ORDER BY page_index, reading_order, element_id
            """,
            (session_id,),
        ).fetchall()
        return [
            ParsedElement(
                element_id=row["element_id"],
                element_type=ElementType(row["element_type"]),
                page_index=row["page_index"],
                reading_order=row["reading_order"],
                markdown=row["markdown"],
                html=row["html"],
                text=row["text"],
                data=_json_loads(row["data_json"], {}),
                bbox=_bbox_from_row(row),
                confidence=row["confidence"],
                metadata=_json_loads(row["metadata_json"], {}),
            )
            for row in rows
        ]

    def list_table_cells(self, session_id: str, table_element_id: str) -> list[JsonDict]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM table_cells
            WHERE session_id = ? AND table_element_id = ?
            ORDER BY row_index, column_index
            """,
            (session_id, table_element_id),
        ).fetchall()
        return [
            {
                "row_index": row["row_index"],
                "column_index": row["column_index"],
                "row_span": row["row_span"],
                "column_span": row["column_span"],
                "text": row["text"],
                "markdown": row["markdown"],
                "html": row["html"],
                "bbox": _bbox_from_row(row),
                "confidence": row["confidence"],
                "metadata": _json_loads(row["metadata_json"], {}),
            }
            for row in rows
        ]

    def get_session_summary(self, session_id: str) -> JsonDict:
        """Return counts and document-level outputs for a session."""

        row = self.connection.execute(
            """
            SELECT session_id, source_path, markdown, html, final_json, metadata_json
            FROM document_sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown session_id: {session_id}")

        counts = {}
        for table_name in (
            "pages",
            "layout_elements",
            "text_blocks",
            "table_objects",
            "table_cells",
            "figures",
            "extracted_fields",
            "evidence_spans",
            "validation_logs",
            "session_outputs",
        ):
            count_row = self.connection.execute(
                f"SELECT COUNT(*) AS count FROM {table_name} WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            counts[table_name] = count_row["count"]

        return {
            "session_id": row["session_id"],
            "source_path": row["source_path"],
            "markdown": row["markdown"],
            "html": row["html"],
            "final_json": _json_loads(row["final_json"], None),
            "metadata": _json_loads(row["metadata_json"], {}),
            "counts": counts,
        }
