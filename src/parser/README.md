# Parser Guidelines

The parser turns curated page images into grounded document outputs. Keep parser code aligned with the session database model:

```text
DocumentSession
└── Page
    └── LayoutElement
        ├── TextBlock
        ├── Table
        │   └── TableCell
        └── Figure
```

Every parsed object should preserve:

- `session_id`
- `page_index`
- `element_id`
- `element_type`
- `bbox`
- `confidence`
- `image_path`
- human-readable output such as markdown or HTML
- machine-readable output such as text, rows, cells, captions, or JSON data

## Main Flow

The high-level parser flow is:

1. `ParserWorkflow.parse_session()` receives a `CuratedDocumentSession`.
2. `PageIterator` sorts pages by `page_index`.
3. `LayoutDetector` calls `OCRToolManager.analyze_layout()`.
4. `RegionTypeRouter` routes each `LayoutRegion` by `ElementType`.
5. Region processors call the tool manager:
   - text/header/footer -> `recognize_text`
   - table -> `detect_table`
   - figure/chart -> `detect_figure`
6. `PageAssembler` orders elements by `reading_order` and builds page markdown and HTML.
7. `SessionMetadataStore` persists pages, elements, table cells, figures, and final outputs.

## OCR Tool Template

All OCR tools should inherit from `OCRTool` in `src/parser/tools_manager.py`.

Each backend may implement any subset of these methods:

```python
def analyze_layout(self, context: OCRToolContext) -> PageLayoutGraph:
    ...

def detect_table(self, context: OCRToolContext) -> ParsedElement:
    ...

def detect_figure(self, context: OCRToolContext) -> ParsedElement:
    ...

def recognize_text(self, context: OCRToolContext) -> ParsedElement:
    ...
```

If a tool does not support a capability, do not implement fake behavior. Leave the base method in place and do not list that capability in `tool_library.json`.

## Tool Library

OCR tools are configured in `src/parser/tool_library.json`.

Each tool entry must include:

- `name`: stable tool identifier used by `OCRToolManager`
- `class_path`: import path to the backend class
- `enabled`: whether the manager can select this tool
- `priority`: lower number wins when multiple enabled tools support the same capability
- `capabilities`: one or more of `analyze_layout`, `detect_table`, `detect_figure`, `recognize_text`
- `config`: backend-specific options passed into the tool constructor

Example:

```json
{
  "name": "my_ocr",
  "class_path": "src.parser.tools.my_ocr.MyOCRTool",
  "enabled": false,
  "priority": 40,
  "capabilities": ["recognize_text"],
  "config": {
    "language": "en"
  }
}
```

Keep new tools disabled by default unless their dependencies are already part of the standard project environment.

## Adding A New OCR Tool

1. Create a module under `src/parser/tools/`.
2. Define a class that inherits from `OCRTool`.
3. Set `name` and `capabilities`.
4. Implement only the capabilities the backend actually supports.
5. Return parser contracts from `src/parser/models.py`, not backend-native raw objects.
6. Add the tool to `tool_library.json`.
7. Add tests for manager loading, capability selection, and output shape.

Skeleton:

```python
from src.parser.models import ParsedElement
from src.parser.tools_manager import OCRTool, OCRToolContext


class MyOCRTool(OCRTool):
    name = "my_ocr"
    capabilities = frozenset({"recognize_text"})

    def recognize_text(self, context: OCRToolContext) -> ParsedElement:
        ...
```

## Output Rules

Use these contracts consistently:

- `analyze_layout` returns `PageLayoutGraph`.
- `recognize_text` returns a `ParsedElement` with `text`, `markdown`, and optionally `html`.
- `detect_table` returns a `ParsedElement` with `data["rows"]` and, when available, `data["cells"]`.
- `detect_figure` returns a `ParsedElement` with `data["summary"]`, `data["caption"]`, or other structured visual metadata.

For visual grounding:

- Use page-space coordinates in `BoundingBox`.
- Preserve the source `page.image_path` in `metadata["image_path"]`.
- Preserve backend confidence when available.
- If backend confidence is unavailable, use a conservative default and document the choice in metadata.

## Dependency Rules

Do not load heavy OCR models at module import time. Optional backends such as PaddleOCR and Chandra should be lazy-loaded inside the tool method or a private loader.

If an optional dependency is missing, raise `OCRToolUnavailableError` with a clear message.

## Testing

Run:

```bash
python -m unittest discover -s tests -v
python -m compileall src tests
```

Use the `dummy` backend for deterministic tests. Tests for optional OCR backends should mock the external library unless the dependency is guaranteed in CI.
