# Table Recognition Data Specification and Label Studio Annotation Guide

## 1. Goal

This document defines the annotation format for table recognition data. The goal is to represent each table as both:

1. A **hierarchical tree** of table/cell structures.
2. A **graph** where nodes are table cells or table-level regions, and edges describe structural relations such as `contains`, `equal_to`, `header_for`, or `adjacent_to`.

This format is designed for document parsing, table structure recognition, table cell extraction, and downstream graph-based table reasoning.

---

## 2. Core Concept

A table is represented as a graph of visual regions.

At the table level, the table is modeled as a tree:

```text
table_root
├── header_group / header_cell
│   ├── sub_header_cell
│   └── sub_header_cell
├── data_cell
├── data_cell
└── ...
```

At the graph level, every annotated object is a node, and relations between nodes are edges:

```text
table_root --contains--> header_cell
header_cell --header_for--> data_cell
cell_A --equal_to--> cell_B
cell_A --adjacent_right--> cell_B
cell_A --adjacent_down--> cell_C
```

The tree is a constrained subset of the graph: every node except the table root should have exactly one parent through a `contains` edge. Other edges are optional graph relations.

---

## 3. Data Model

## 3.1 Table Object

Each table should be stored as one JSON object.

```json
{
  "table_id": "page_001_table_001",
  "document_id": "doc_001",
  "page_index": 0,
  "image": {
    "path": "images/page_001.png",
    "width": 2480,
    "height": 3508
  },
  "nodes": [],
  "edges": [],
  "metadata": {
    "annotator": "annotator_01",
    "created_at": "2026-05-26T00:00:00Z",
    "schema_version": "1.0"
  }
}
```

---

## 3.2 Node Definition

A node represents a table region. Usually, a node is one of:

| Node type       | Meaning                                                   |
| --------------- | --------------------------------------------------------- |
| `table_root`    | Bounding box of the whole table                           |
| `header_group`  | A grouped header region containing multiple header cells  |
| `header_cell`   | A visible header cell                                     |
| `data_cell`     | A normal body cell                                        |
| `stub_cell`     | Row-header cell, usually at the left side of a table      |
| `empty_cell`    | A visible blank cell                                      |
| `spanning_cell` | A merged cell spanning multiple rows or columns           |
| `virtual_cell`  | A logical cell that is implied but not visually separated |

Each node has three parts:

1. **Visual part**: bounding box and page location.
2. **Logic part**: row/column position and structural role.
3. **Content part**: recognized text or manually corrected text.

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
    "logical_role": "column_header",
    "header_level": 1
  },
  "content": {
    "text": "Revenue",
    "normalized_text": "revenue",
    "tokens": ["Revenue"],
    "language": "en"
  },
  "confidence": {
    "bbox": 1.0,
    "structure": 1.0,
    "text": 0.98
  }
}
```

Use **0-based indexing** for rows and columns. Use **end-exclusive intervals**:

```text
row_start = 0
row_end = 1
row_span = row_end - row_start
```

For a merged cell covering columns 0 and 1:

```json
{
  "col_start": 0,
  "col_end": 2,
  "col_span": 2
}
```

---

## 3.3 Edge Definition

An edge represents a relation between two nodes.

```json
{
  "edge_id": "edge_001",
  "source": "table_root_001",
  "target": "cell_001",
  "relation": "contains",
  "direction": "directed",
  "metadata": {
    "confidence": 1.0
  }
}
```

Recommended relation types:

| Relation         |  Direction | Meaning                                                                            |
| ---------------- | ---------: | ---------------------------------------------------------------------------------- |
| `contains`       |   Directed | Parent node contains child node                                                    |
| `header_for`     |   Directed | Header cell describes a data cell or group                                         |
| `equal_to`       | Undirected | Two cells have the same logical meaning/value                                      |
| `adjacent_right` |   Directed | Source cell is immediately left of target cell                                     |
| `adjacent_down`  |   Directed | Source cell is immediately above target cell                                       |
| `same_row`       | Undirected | Two cells are in the same logical row                                              |
| `same_column`    | Undirected | Two cells are in the same logical column                                           |
| `continues_to`   |   Directed | Cell continues across page/table split                                             |
| `parent_of`      |   Directed | Alternative to `contains`, only if tree relation is semantic rather than geometric |

Recommended rule: use `contains` for the tree structure and use the other relations for additional graph structure.

---

## 4. Example Canonical Annotation

```json
{
  "table_id": "page_001_table_001",
  "document_id": "doc_001",
  "page_index": 0,
  "image": {
    "path": "images/page_001.png",
    "width": 1000,
    "height": 1400
  },
  "nodes": [
    {
      "node_id": "table_001",
      "node_type": "table_root",
      "visual": {
        "bbox": [100, 200, 900, 700],
        "bbox_format": "xyxy",
        "bbox_unit": "pixel",
        "page_index": 0
      },
      "logic": {
        "row_start": 0,
        "row_end": 4,
        "col_start": 0,
        "col_end": 3,
        "row_span": 4,
        "col_span": 3,
        "logical_role": "table"
      },
      "content": {
        "text": ""
      }
    },
    {
      "node_id": "cell_001",
      "node_type": "header_cell",
      "visual": {
        "bbox": [100, 200, 300, 300],
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
        "logical_role": "column_header",
        "header_level": 1
      },
      "content": {
        "text": "Year"
      }
    },
    {
      "node_id": "cell_002",
      "node_type": "data_cell",
      "visual": {
        "bbox": [100, 300, 300, 400],
        "bbox_format": "xyxy",
        "bbox_unit": "pixel",
        "page_index": 0
      },
      "logic": {
        "row_start": 1,
        "row_end": 2,
        "col_start": 0,
        "col_end": 1,
        "row_span": 1,
        "col_span": 1,
        "logical_role": "data"
      },
      "content": {
        "text": "2024"
      }
    }
  ],
  "edges": [
    {
      "edge_id": "edge_001",
      "source": "table_001",
      "target": "cell_001",
      "relation": "contains",
      "direction": "directed"
    },
    {
      "edge_id": "edge_002",
      "source": "table_001",
      "target": "cell_002",
      "relation": "contains",
      "direction": "directed"
    },
    {
      "edge_id": "edge_003",
      "source": "cell_001",
      "target": "cell_002",
      "relation": "header_for",
      "direction": "directed"
    }
  ]
}
```

---

# 5. Label Studio Annotation Guide

## 5.1 Recommended Label Studio Task Unit

Use one Label Studio task for one of the following:

| Task type                             | Recommended use                                        |
| ------------------------------------- | ------------------------------------------------------ |
| Full page image                       | Best when table detection is part of the task          |
| Cropped table image                   | Best when table structure recognition is the main task |
| Pre-detected table crop + model boxes | Best for review/correction workflow                    |

For this project, the recommended setup is:

```text
one task = one page image
annotate table root + all cells + relations
```

Label Studio supports image annotation with bounding boxes through `Image` and `RectangleLabels`; its official object detection template uses an `Image` tag and a `RectangleLabels` control tag inside a `View`. ([Label Studio][1])

---

## 5.2 Label Studio Labeling Configuration

Use this configuration as a starting point.

```xml
<View>
  <Header value="Table Structure Annotation"/>

  <Relations>
    <Relation value="contains"/>
    <Relation value="header_for"/>
    <Relation value="equal_to"/>
    <Relation value="adjacent_right"/>
    <Relation value="adjacent_down"/>
    <Relation value="same_row"/>
    <Relation value="same_column"/>
    <Relation value="continues_to"/>
  </Relations>

  <Image name="image" value="$image"/>

  <RectangleLabels name="node_type" toName="image">
    <Label value="table_root" background="#D4380D"/>
    <Label value="header_group" background="#FA8C16"/>
    <Label value="header_cell" background="#FADB14"/>
    <Label value="data_cell" background="#52C41A"/>
    <Label value="stub_cell" background="#13C2C2"/>
    <Label value="empty_cell" background="#BFBFBF"/>
    <Label value="spanning_cell" background="#722ED1"/>
    <Label value="virtual_cell" background="#2F54EB"/>
  </RectangleLabels>

  <View visibleWhen="region-selected">
    <Header value="Cell content"/>
    <TextArea
      name="cell_text"
      toName="image"
      perRegion="true"
      editable="true"
      rows="2"
      maxSubmissions="1"
      placeholder="Enter cell text. Leave empty for blank cells."
    />

    <Header value="Logical role"/>
    <Choices
      name="logical_role"
      toName="image"
      perRegion="true"
      choice="single-radio"
      showInline="true"
    >
      <Choice value="table"/>
      <Choice value="column_header"/>
      <Choice value="row_header"/>
      <Choice value="data"/>
      <Choice value="group_header"/>
      <Choice value="empty"/>
      <Choice value="unknown"/>
    </Choices>

    <Header value="Logic metadata JSON"/>
    <TextArea
      name="logic_json"
      toName="image"
      perRegion="true"
      editable="true"
      rows="5"
      maxSubmissions="1"
      placeholder='{"row_start":0,"row_end":1,"col_start":0,"col_end":1,"row_span":1,"col_span":1,"header_level":0}'
    />

    <Header value="Quality"/>
    <Choices
      name="quality"
      toName="image"
      perRegion="true"
      choice="single-radio"
      showInline="true"
    >
      <Choice value="clear"/>
      <Choice value="uncertain_bbox"/>
      <Choice value="uncertain_text"/>
      <Choice value="uncertain_structure"/>
    </Choices>
  </View>
</View>
```

Notes:

Label Studio supports `Relations` for creating labeled relations between regions, which maps naturally to graph edges such as `contains`, `header_for`, and `equal_to`. ([Label Studio][2])

For OCR-style annotation, Label Studio supports per-region text fields using `TextArea perRegion="true"`, and the OCR template uses this pattern to attach transcription text to each drawn region. ([Label Studio][3])

`Choices` also supports `perRegion="true"`, which is useful for attaching a logical role or quality label to each selected bounding box. ([Label Studio][4])

---

# 6. Annotation Instructions

## 6.1 Step 1: Draw the Table Root

Draw one bounding box around the whole table.

Label it as:

```text
table_root
```

The table root should include:

* all header cells
* all body cells
* visible table borders
* captions only if the caption is visually part of the table; otherwise annotate caption separately in another task/schema

For the `logic_json` of the table root:

```json
{
  "row_start": 0,
  "row_end": 5,
  "col_start": 0,
  "col_end": 4,
  "row_span": 5,
  "col_span": 4,
  "header_level": null
}
```

---

## 6.2 Step 2: Draw All Visible Cells

Draw a bounding box for every visible table cell.

Rules:

1. Annotate **merged cells as one box**, not multiple boxes.
2. Annotate **blank cells** if the cell exists visually.
3. If a cell has no visible border but is logically clear, annotate it as a normal cell.
4. If a logical cell is implied but not visually separable, annotate it as `virtual_cell`.
5. Do not overlap cells unless one cell is a parent/group cell containing child cells.

Recommended labels:

```text
header_cell
data_cell
stub_cell
empty_cell
spanning_cell
```

---

## 6.3 Step 3: Add Cell Text

For every cell, fill `cell_text`.

Examples:

```text
Revenue
```

```text
2024
```

```text
Total assets
```

For blank cells, leave the text empty:

```text
```

Do not include unnecessary line breaks unless the cell content is truly multi-line.

---

## 6.4 Step 4: Add Logic Metadata

For every cell, fill `logic_json`.

Example for a normal cell:

```json
{
  "row_start": 2,
  "row_end": 3,
  "col_start": 1,
  "col_end": 2,
  "row_span": 1,
  "col_span": 1,
  "header_level": 0
}
```

Example for a merged column header:

```json
{
  "row_start": 0,
  "row_end": 1,
  "col_start": 1,
  "col_end": 4,
  "row_span": 1,
  "col_span": 3,
  "header_level": 1
}
```

Example for a row header:

```json
{
  "row_start": 3,
  "row_end": 4,
  "col_start": 0,
  "col_end": 1,
  "row_span": 1,
  "col_span": 1,
  "header_level": 1
}
```

---

## 6.5 Step 5: Add Relations

After drawing all nodes, create relations between regions.

Label Studio lets annotators create relations between two annotation regions and then assign a predefined relation label to the relation. ([Label Studio][5])

Use the following direction rules:

## `contains`

Use from parent to child.

```text
table_root -> cell
header_group -> header_cell
```

Example:

```text
table_001 --contains--> cell_001
```

## `header_for`

Use from header cell to the data cell it describes.

```text
header_cell -> data_cell
```

Example:

```text
"Year" --header_for--> "2024"
```

## `equal_to`

Use when two cells are logically equivalent.

```text
cell_A --equal_to-- cell_B
```

This relation is logically undirected. In Label Studio, draw it in either direction, then normalize it during post-processing.

## `adjacent_right`

Use from left cell to right cell.

```text
cell_A -> cell_B
```

## `adjacent_down`

Use from upper cell to lower cell.

```text
cell_A -> cell_C
```

## `continues_to`

Use when a table or cell continues across pages.

```text
cell_page_1 -> cell_page_2
```

---

# 7. Label Studio Export Mapping

Label Studio exports annotations in JSON. Image annotation bounding boxes are exported as percentages of the image size, not raw pixels. ([Label Studio][6])

A Label Studio rectangle result usually contains values like:

```json
{
  "id": "abc123",
  "from_name": "node_type",
  "to_name": "image",
  "type": "rectanglelabels",
  "value": {
    "x": 10.0,
    "y": 20.0,
    "width": 30.0,
    "height": 5.0,
    "rotation": 0,
    "rectanglelabels": ["header_cell"]
  }
}
```

Convert percentage coordinates to pixel coordinates:

```python
x0 = value["x"] / 100 * image_width
y0 = value["y"] / 100 * image_height
x1 = (value["x"] + value["width"]) / 100 * image_width
y1 = (value["y"] + value["height"]) / 100 * image_height
```

Target canonical format:

```json
"visual": {
  "bbox": [x0, y0, x1, y1],
  "bbox_format": "xyxy",
  "bbox_unit": "pixel"
}
```

Label Studio stores each annotation as results, and results for the same region share the same `id`, which is useful for combining the box, text, choices, and metadata into one canonical node. ([Human Signal][7])

---

# 8. Import Format for Label Studio

For manual annotation, each task can be imported like this:

```json
[
  {
    "data": {
      "image": "https://example.com/images/page_001.png",
      "document_id": "doc_001",
      "page_index": 0
    }
  }
]
```

For model-assisted annotation, use pre-annotations with the `predictions` key. Label Studio expects pre-annotation tasks to contain a `data` object and a `predictions` array, and the prediction result format must match the labeling configuration. ([Label Studio][8])

Example:

```json
[
  {
    "data": {
      "image": "https://example.com/images/page_001.png",
      "document_id": "doc_001",
      "page_index": 0
    },
    "predictions": [
      {
        "model_version": "table-detector-v1",
        "result": [
          {
            "id": "cell_001",
            "from_name": "node_type",
            "to_name": "image",
            "type": "rectanglelabels",
            "value": {
              "x": 10.0,
              "y": 20.0,
              "width": 20.0,
              "height": 5.0,
              "rotation": 0,
              "rectanglelabels": ["header_cell"]
            }
          },
          {
            "id": "cell_001",
            "from_name": "cell_text",
            "to_name": "image",
            "type": "textarea",
            "value": {
              "text": ["Revenue"]
            }
          }
        ]
      }
    ]
  }
]
```

---

# 9. Annotation Quality Checklist

Before submitting a task, check:

* [ ] The whole table has exactly one `table_root`.
* [ ] Every visible cell has one bounding box.
* [ ] Merged cells are annotated as one cell with correct `row_span` and `col_span`.
* [ ] Empty cells are annotated if they are part of the table grid.
* [ ] Every cell has valid `logic_json`.
* [ ] Row and column indices are 0-based.
* [ ] `row_end` and `col_end` are end-exclusive.
* [ ] Every cell has a `contains` relation from the table root or from a parent group.
* [ ] Header cells use `header_for` relations when the relationship is clear.
* [ ] Ambiguous cells are marked with `quality = uncertain_*`.
* [ ] Text is copied exactly as shown unless normalization is handled separately.

---

# 10. Recommended Post-processing

After exporting Label Studio annotations:

1. Group all results by Label Studio region `id`.
2. Convert rectangle percentage coordinates to pixel coordinates.
3. Parse `cell_text`.
4. Parse `logic_json`.
5. Parse `logical_role`.
6. Convert Label Studio relations into canonical graph edges.
7. Validate tree constraints:

   * one `table_root`
   * every non-root node has one `contains` parent
   * no cycles in `contains` edges
8. Validate table grid constraints:

   * no unintended overlap between cells
   * correct row/column spans
   * all required row/column positions are covered
9. Export final canonical JSON.

---

# 11. Recommended File Structure

```text
dataset/
├── images/
│   ├── doc_001_page_001.png
│   └── doc_001_page_002.png
├── label_studio/
│   ├── tasks.json
│   └── exported_annotations.json
├── canonical/
│   ├── doc_001_page_001_table_001.json
│   └── doc_001_page_002_table_001.json
└── README.md
```

---

# 12. Versioning

Use a schema version in every exported canonical file:

```json
{
  "schema_version": "1.0"
}
```

Recommended version policy:

| Version | Meaning                                |
| ------- | -------------------------------------- |
| `1.0`   | Initial table tree/graph schema        |
| `1.1`   | Add new relation types                 |
| `1.2`   | Add confidence fields or OCR metadata  |
| `2.0`   | Breaking change in node/edge structure |

---

# 13. Summary

This annotation format treats a table as a structured visual graph:

* The **table root** defines the full table boundary.
* Each **cell** is a node with visual, logical, and content information.
* The **tree structure** is represented by `contains` edges.
* Additional table semantics are represented by graph edges such as `header_for`, `equal_to`, `adjacent_right`, and `adjacent_down`.
* Label Studio is used to annotate bounding boxes, per-region text, per-region metadata, and relations.
* A post-processing step converts Label Studio JSON into the final canonical table graph JSON.

[1]: https://labelstud.io/templates/image_bbox "Label Studio — Image Object Detection Data Labeling Template"
[2]: https://labelstud.io/tags/relations "Label Studio — Relations Tag for Multiple Relations"
[3]: https://labelstud.io/templates/optical_character_recognition "Label Studio — Optical Character Recognition (OCR) Data Labeling Template"
[4]: https://labelstud.io/tags/choices "Label Studio — Choices Tag for Multiple Choice Labels"
[5]: https://labelstud.io/guide/labeling/ "Label Studio Documentation — Label and annotate data"
[6]: https://labelstud.io/guide/export "Label Studio Documentation — Export Annotations"
[7]: https://docs.humansignal.com/guide/task_format "Label Studio Enterprise Documentation — Label Studio Task Format"
[8]: https://labelstud.io/guide/predictions "Label Studio Documentation — Import pre-annotated data into Label Studio"