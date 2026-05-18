# Dataloader Annotation Guidelines

This directory defines the sample annotation format for page-level document data. Use it when building datasets for OCR, layout detection, table extraction, figure extraction, and downstream field extraction.

The annotation format follows the parser and session database hierarchy:

```text
DocumentSession
└── Page
    └── LayoutElement
        ├── TextBlock
        ├── Table
        │   └── TableCell
        └── Figure
```

## File Layout

Store one annotation JSON file per document, with all annotated pages in the `pages` list.

Recommended path pattern:

```text
src/dataloader/annotations/<document_id>.json
```

The sample file is:

```text
src/dataloader/sample_page_annotation.json
```

## Required Page Fields

Each page annotation should include:

- `page_id`: stable page identifier inside the dataset
- `session_id`: document/session identifier
- `page_index`: 1-based page number in document order
- `image_path`: source or curated page image path
- `width`: image width in pixels
- `height`: image height in pixels
- `layout_elements`: annotated regions on the page

## Required Layout Element Fields

Each layout element should include:

- `element_id`: stable element identifier
- `element_type`: one of `text`, `table`, `figure`, `chart`, `header`, `footer`
- `reading_order`: integer order used to reconstruct the page
- `bbox`: page-space bounding box
- `confidence`: annotator or model confidence
- `text`: plain text when applicable
- `markdown`: human-readable markdown output when applicable
- `html`: human-readable HTML output when applicable
- `data`: machine-readable payload for type-specific structures

Bounding boxes use pixel coordinates unless `bbox_units` says otherwise:

```json
{
  "x": 120,
  "y": 96,
  "width": 960,
  "height": 180
}
```

## Type-Specific Data

For text blocks, put paragraph or line data in `data.lines`.

For tables, include:

- `data.rows`: row matrix for simple table content
- `data.cells`: structured cells with row/column indexes, spans, text, bounding boxes, and confidence

For figures and charts, include:

- `data.caption`: caption text if available
- `data.summary`: human-readable visual summary
- `data.linked_text_element_ids`: related text blocks if known

## Annotation Quality Rules

- Keep `element_id` stable across annotation updates.
- Use one coordinate system consistently inside a file.
- Preserve page image paths so annotations can be visually inspected.
- Prefer exact table cells over only `rows` when cell-level boxes are available.
- Use `confidence: 1.0` for human verified annotations.
- Use lower confidence values for model-generated or weak annotations.

## Minimal Validation Checklist

Before using an annotation file:

- Every page has `session_id`, `page_index`, `image_path`, `width`, and `height`.
- Every layout element has `element_id`, `element_type`, `reading_order`, `bbox`, and `confidence`.
- Table cell indexes are zero-based and consistent with `data.rows`.
- Figure links reference existing text element IDs on the same page.
- Reading order values are unique within a page.
