import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.parser import CuratedDocumentSession, CuratedPage, ElementType, ParserWorkflow
from src.parser.storage import InMemorySessionDatabase, SessionMetadataStore


class ParserWorkflowTest(unittest.TestCase):
    def test_parse_session_moves_pages_through_dummy_flow(self) -> None:
        database = InMemorySessionDatabase()
        workflow = ParserWorkflow(metadata_store=SessionMetadataStore(database))
        session = CuratedDocumentSession(
            session_id="session-1",
            pages=[
                CuratedPage(page_index=2, image_path="page-2.png"),
                CuratedPage(page_index=1, image_path="page-1.png"),
            ],
        )

        result = workflow.parse_session(session)

        self.assertEqual(result.session_id, "session-1")
        self.assertEqual([page.page_index for page in result.pages], [1, 2])
        self.assertEqual(result.metadata["page_count"], 2)
        self.assertIn("Dummy text block for page 1.", result.markdown)
        self.assertEqual(len(database.list_pages("session-1")), 2)
        self.assertEqual(len(database.list_elements("session-1")), 6)
        self.assertEqual(
            [element.element_type for element in result.pages[0].elements],
            [ElementType.TEXT, ElementType.TABLE, ElementType.FIGURE],
        )


if __name__ == "__main__":
    unittest.main()
