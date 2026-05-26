# Table Recognition Annotation

## Table of Contents

- [Overview](#overview)
- [Schema](#schema)
- [Annotation Workflow](#annotation-workflow)
- [Example](#example)
- [Dataset Structure](#dataset-structure)
- [Final Checklist](#final-checklist)

## Overview

This document defines a simple annotation format for table recognition. A table is represented as a hierarchical graph: the table contains cells, cells may contain sub-cells for hierarchical headers, and relations describe containment, header scope, and repeated logical cells.

Each annotated object should preserve three kinds of information:

1. **Visual grounding**: page index and bounding box.
2. **Logical position**: row, column, span, and role in the table grid.
3. **Content**: original and normalized text.

Basic tree shape:

```text
table_root
├── header_cell
├── header_cell
├── data_cell
├── data_cell
└── ...
```

Hierarchical headers can be represented with nested `contains` edges:

```text
table_root
├── header_cell: Revenue
│   ├── header_cell: 2023
│   └── header_cell: 2024
├── data_cell
└── ...
```

## Schema

Use one node per table region and a small set of relation types.

| Node type | Use for |
| --- | --- |
| `table_root` | The whole table. |
| `header_cell` | A column header, row header, or group header. |
| `data_cell` | A normal body cell. |
| `merged_cell` | A visible cell spanning multiple rows or columns. |
| `empty_cell` | A visible blank cell that belongs to the table structure. |

| Relation | Direction | Use for |
| --- | ---: | --- |
| `contains` | Directed | Parent node contains child node. Every non-root node needs this relation. |
| `header_for` | Directed | A header describes a data cell or another header. Use only when clear. |
| `same_as` | Undirected | Two cells are logically equivalent, such as repeated headers or continued tables. |

Each cell node contains `visual`, `logic`, and `content` fields:

```json
{
  "node_id": "cell_001",
  "node_type": "header_cell",
  "visual": {
    "bbox": [120, 240, 520, 310],
    "bbox_format": "xyxy",
    "bbox_unit": "pixel",
    "page_index": 0
  },
  "logic": {
    "row_start": 0,
    "row_end": 1,
    "col_start": 0,
    "col_end": 2,
    "row_span": 1,
    "col_span": 2,
    "logical_role": "column_header"
  },
  "content": {
    "text": "Revenue",
    "normalized_text": "revenue"
  }
}
```

Field rules:

| Field | Rule |
| --- | --- |
| `bbox` | Use `[x_min, y_min, x_max, y_max]`. |
| `bbox_format` | Use `xyxy`. |
| `bbox_unit` | Use `pixel`. |
| `page_index` | Use 0-based page index. |
| `row_start`, `col_start` | Use 0-based start indices. |
| `row_end`, `col_end` | Use end-exclusive indices. |
| `row_span`, `col_span` | Must equal `end - start`. |
| `content.text` | Keep the original OCR or transcribed cell text. |
| `content.normalized_text` | Store cleaned text. Use `""` for empty cells. |

Example merged cell covering columns 0 and 1:

```json
{
  "row_start": 0,
  "row_end": 1,
  "col_start": 0,
  "col_end": 2,
  "row_span": 1,
  "col_span": 2
}
```

## Annotation Workflow

1. Draw one `table_root` box around the full table, including all headers and body cells.
2. Annotate each visible cell once with a bounding box, node type, grid position, span, and text.
3. Treat merged cells as one node. Do not split a visually merged cell into smaller cells.
4. Annotate blank cells as `empty_cell` when they are part of the table grid.
5. Add `contains` edges from the table root to each cell. For hierarchical headers, add `contains` from the parent header to its sub-headers.
6. Add `header_for` edges from headers to the cells they describe when the relationship is clear.
7. Add `same_as` only for repeated or equivalent cells, such as repeated headers across pages.

Minimum table graph:

```text
table_root --contains--> cell
header_cell --header_for--> data_cell
cell_A --same_as-- cell_B
```

## Example

Original table:

```markdown
| Year | Revenue | Profit |
|---|---:|---:|
| 2023 | 1000 | 200 |
| 2024 | 1500 | 300 |
```

Rendered table:

| Year | Revenue | Profit |
| --- | ---: | ---: |
| 2023 | 1000 | 200 |
| 2024 | 1500 | 300 |

Annotation nodes:

| Node ID | Node Type | BBox Example | Row | Column | Text |
| --- | --- | ---: | ---: | ---: | --- |
| `table_001` | `table_root` | `[0, 0, 600, 300]` | `0-3` | `0-3` | `""` |
| `cell_001` | `header_cell` | `[0, 0, 200, 80]` | `0` | `0` | `Year` |
| `cell_002` | `header_cell` | `[200, 0, 400, 80]` | `0` | `1` | `Revenue` |
| `cell_003` | `header_cell` | `[400, 0, 600, 80]` | `0` | `2` | `Profit` |
| `cell_004` | `data_cell` | `[0, 80, 200, 160]` | `1` | `0` | `2023` |
| `cell_005` | `data_cell` | `[200, 80, 400, 160]` | `1` | `1` | `1000` |
| `cell_006` | `data_cell` | `[400, 80, 600, 160]` | `1` | `2` | `200` |
| `cell_007` | `data_cell` | `[0, 160, 200, 240]` | `2` | `0` | `2024` |
| `cell_008` | `data_cell` | `[200, 160, 400, 240]` | `2` | `1` | `1500` |
| `cell_009` | `data_cell` | `[400, 160, 600, 240]` | `2` | `2` | `300` |

Common relations:

| Source | Relation | Target | Meaning |
| --- | --- | --- | --- |
| `table_001` | `contains` | `cell_001` | Table contains Year header. |
| `table_001` | `contains` | `cell_002` | Table contains Revenue header. |
| `table_001` | `contains` | `cell_003` | Table contains Profit header. |
| `table_001` | `contains` | `cell_004` to `cell_009` | Table contains body cells. |
| `cell_001` | `header_for` | `cell_004`, `cell_007` | Year describes the year values. |
| `cell_002` | `header_for` | `cell_005`, `cell_008` | Revenue describes revenue values. |
| `cell_003` | `header_for` | `cell_006`, `cell_009` | Profit describes profit values. |

Compact JSON shape:

```json
{
  "table_id": "table_001",
  "page_index": 0,
  "nodes": [
    {
      "node_id": "table_001",
      "node_type": "table_root",
      "visual": {
        "bbox": [0, 0, 600, 300],
        "bbox_format": "xyxy",
        "bbox_unit": "pixel",
        "page_index": 0
      },
      "logic": {
        "row_start": 0,
        "row_end": 3,
        "col_start": 0,
        "col_end": 3,
        "row_span": 3,
        "col_span": 3,
        "logical_role": "table"
      },
      "content": {
        "text": "",
        "normalized_text": ""
      }
    },
    {
      "node_id": "cell_001",
      "node_type": "header_cell",
      "visual": {
        "bbox": [0, 0, 200, 80],
        "bbox_format": "xyxy",
        "bbox_unit": "pixel",
        "page_index": 0
      },
      "logic": {
        "row_start": 0,
        "row_end": 1,
        "col_start": 0,
        "col_end": 1,
        "row_span": 1,
        "col_span": 1,
        "logical_role": "column_header"
      },
      "content": {
        "text": "Year",
        "normalized_text": "year"
      }
    }
  ],
  "edges": [
    {
      "edge_id": "edge_001",
      "source": "table_001",
      "target": "cell_001",
      "relation": "contains"
    }
  ]
}
```

## Dataset Structure

```text
dataset/
├── images/
│   ├── page_001.png
│   └── page_002.png
├── annotations/
│   ├── page_001_table_001.json
│   └── page_002_table_001.json
└── README.md
```

## Final Checklist

- [ ] Each table has exactly one `table_root`.
- [ ] Every visible cell is annotated once.
- [ ] Merged cells use one node with correct `row_span` and `col_span`.
- [ ] Empty structural cells are annotated as `empty_cell`.
- [ ] All nodes have `visual`, `logic`, and `content` fields.
- [ ] Row and column indices are 0-based and end-exclusive.
- [ ] Every non-root node has a `contains` relation.
- [ ] `header_for` and `same_as` edges are used only when the relationship is clear.
- [ ] The `contains` graph has no cycles.
