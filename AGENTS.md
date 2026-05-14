The **session database** is the central storage layer for one document-processing session. Each uploaded document creates a `session_id`. All pages, parsed elements, tables, figures, extracted fields, evidence spans, validation logs, and final JSON outputs are linked to this session.

The database should support four main goals:

First, it should preserve the **document hierarchy**:

```
DocumentSession
└── Page
    └── LayoutElement
        ├── TextBlock
        ├── Table
        │   └── TableCell
        └── Figure
```

Second, every parsed object should preserve **visual grounding**, including page number, bounding box, confidence score, and links back to the original page image.

Third, the database should support both **human-readable outputs** such as markdown and HTML, and **machine-readable outputs** such as JSON and structured table cells.

#### **2.3.3.1. Entity Relationship Overview**

```mermaid
erDiagram
    DOCUMENT_SESSION ||--o{ PAGE : contains
    DOCUMENT_SESSION ||--o{ LAYOUT_ELEMENT : owns
    PAGE ||--o{ LAYOUT_ELEMENT : contains

    LAYOUT_ELEMENT ||--o| TEXT_BLOCK : represents
    LAYOUT_ELEMENT ||--o| TABLE_OBJECT : represents
    LAYOUT_ELEMENT ||--o| FIGURE : represents

    TABLE_OBJECT ||--o{ TABLE_CELL : contains

    TEXT_BLOCK }o--o{ FIGURE_TEXT_LINK : linked_to
    FIGURE ||--o{ FIGURE_TEXT_LINK : has
```