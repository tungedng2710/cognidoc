import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.parser.models import CuratedPage, ElementType
from src.parser.tools_manager import OCRToolManager, UnsupportedOCRCapabilityError


class OCRToolManagerTest(unittest.TestCase):
    def test_loads_json_library_and_dispatches_dummy_tool(self) -> None:
        manager = OCRToolManager()
        page = CuratedPage(page_index=1, image_path="page-1.png")

        layout = manager.analyze_layout(session_id="session-1", page=page)
        text = manager.recognize_text(session_id="session-1", page=page, region=layout.regions[0])
        table = manager.detect_table(session_id="session-1", page=page, region=layout.regions[1])
        figure = manager.detect_figure(session_id="session-1", page=page, region=layout.regions[2])

        self.assertEqual([region.element_type for region in layout.regions], [ElementType.TEXT, ElementType.TABLE, ElementType.FIGURE])
        self.assertEqual(text.text, "Dummy text block for page 1.")
        self.assertEqual(table.data["rows"][0], ["Header A", "Header B"])
        self.assertEqual(figure.metadata["tool"], "dummy")

    def test_rejects_preferred_tool_without_capability(self) -> None:
        manager = OCRToolManager()
        page = CuratedPage(page_index=1, image_path="page-1.png")

        with self.assertRaises(UnsupportedOCRCapabilityError):
            manager.detect_table(session_id="session-1", page=page, tool_name="paddle")


if __name__ == "__main__":
    unittest.main()
