import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import SQLiteSessionDatabase
from src.parser import CuratedDocumentSession, CuratedPage, ElementType, ParserWorkflow
from src.parser.models import BoundingBox, PageRepresentation, ParsedElement
from src.parser.storage import SessionMetadataStore


class SessionDatabaseTest(unittest.TestCase):
    def test_persists_document_hierarchy_and_visual_grounding(self) -> None:
        database = SQLiteSessionDatabase()
        page = PageRepresentation(
            session_id="session-db-1",
            page_index=1,
            markdown="Body\n\n| A | B |",
            html="<p>Body</p><table></table>",
            metadata={"image_path": "page-1.png"},
            elements=[
                ParsedElement(
                    element_id="text-1",
                    element_type=ElementType.TEXT,
                    page_index=1,
                    reading_order=1,
                    markdown="Body",
                    html="<p>Body</p>",
                    text="Body",
                    bbox=BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4),
                    confidence=0.91,
                    metadata={"image_path": "page-1.png"},
                ),
                ParsedElement(
                    element_id="table-1",
                    element_type=ElementType.TABLE,
                    page_index=1,
                    reading_order=2,
                    markdown="| A | B |\n| --- | --- |\n| 1 | 2 |",
                    html="<table></table>",
                    data={"rows": [["A", "B"], ["1", "2"]]},
                    bbox=BoundingBox(x=0.1, y=0.5, width=0.8, height=0.2),
                    confidence=0.88,
                    metadata={"image_path": "page-1.png"},
                ),
            ],
        )

        database.save_page(page)

        stored_pages = database.list_pages("session-db-1")
        stored_elements = database.list_elements("session-db-1")
        table_cells = database.list_table_cells("session-db-1", "table-1")
        summary = database.get_session_summary("session-db-1")

        self.assertEqual(len(stored_pages), 1)
        self.assertEqual([element.element_id for element in stored_elements], ["text-1", "table-1"])
        self.assertEqual(stored_elements[0].bbox, BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4))
        self.assertEqual(stored_elements[0].confidence, 0.91)
        self.assertEqual([cell["text"] for cell in table_cells], ["A", "B", "1", "2"])
        self.assertEqual(summary["counts"]["pages"], 1)
        self.assertEqual(summary["counts"]["layout_elements"], 2)
        self.assertEqual(summary["counts"]["table_cells"], 4)

    def test_workflow_persists_session_outputs_and_extraction_artifacts(self) -> None:
        database = SQLiteSessionDatabase()
        workflow = ParserWorkflow(metadata_store=SessionMetadataStore(database))
        session = CuratedDocumentSession(
            session_id="session-db-2",
            pages=[CuratedPage(page_index=1, image_path="page-1.png")],
            metadata={"source_path": "document.pdf"},
        )

        workflow.parse_session(session)
        database.save_final_json("session-db-2", {"invoice_total": {"amount": 100, "currency": "USD"}})
        database.add_extracted_field("session-db-2", "invoice_total", {"amount": 100, "currency": "USD"})
        database.add_evidence_span(
            "session-db-2",
            field_name="invoice_total",
            element_id="p1-text-1",
            page_index=1,
            text="Total: $100",
            bbox=BoundingBox(x=0.2, y=0.3, width=0.4, height=0.05),
        )
        database.add_validation_log("session-db-2", "schema", "info", "Schema validation passed")

        summary = database.get_session_summary("session-db-2")

        self.assertEqual(summary["source_path"], "document.pdf")
        self.assertEqual(summary["final_json"], {"invoice_total": {"amount": 100, "currency": "USD"}})
        self.assertEqual(summary["counts"]["pages"], 1)
        self.assertEqual(summary["counts"]["layout_elements"], 3)
        self.assertEqual(summary["counts"]["text_blocks"], 1)
        self.assertEqual(summary["counts"]["table_objects"], 1)
        self.assertEqual(summary["counts"]["figures"], 1)
        self.assertEqual(summary["counts"]["session_outputs"], 3)
        self.assertEqual(summary["counts"]["extracted_fields"], 1)
        self.assertEqual(summary["counts"]["evidence_spans"], 1)
        self.assertEqual(summary["counts"]["validation_logs"], 1)


if __name__ == "__main__":
    unittest.main()
