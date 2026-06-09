# Graph-Guided Training for Table Structure Recognition

## 1. Goal

This document describes an experimental model design for improving **table structure recognition (TSR)** by using graph information during training while keeping inference image-only.

The core idea is:

> Use a graph branch as an auxiliary teacher during training, but remove the graph branch during inference.

This allows the deployed model to keep the same inference pipeline as a standard image-based table structure recognition model, while still benefiting from graph-based structural supervision during training.

The main target is not to beat state-of-the-art models. The target is to evaluate whether adding graph-guided training improves performance compared with a Table Transformer-style baseline.

---

## 2. Motivation

Table structure recognition requires the model to understand relationships between cells, such as:

- which cells belong to the same row
- which cells belong to the same column
- which cell is the right neighbor of another cell
- which cell is the bottom neighbor of another cell
- optionally, which header cell describes which data cells

A pure visual model can learn these relationships implicitly from images, but it may fail when tables are complex, sparse, borderless, or have merged cells.

Graph supervision can explicitly encode structural relationships between table cells. However, constructing a graph at inference time can make the runtime pipeline more complex.

Therefore, this experiment uses graph information only during training.

---

## 3. High-Level Idea

The model has two modes:

### Training mode

During training, the model receives:

- table image
- ground-truth cell boxes
- ground-truth cell logical positions
- graph relations between cells

The graph branch is used to provide auxiliary supervision or teacher representations.

### Inference mode

During inference, the model receives only:

- table image

The graph branch is removed. The deployed model predicts table structure directly from the image.

---

## 4. Recommended Design

Do **not** design the graph branch as a required module in the main prediction path if it will be removed during inference.

A bad design would be:

```text
Image
  -> Visual Backbone
  -> GNN Refinement
  -> Prediction Head
```

and then removing `GNN Refinement` during inference.

This creates a train-inference mismatch because the prediction head may become dependent on graph-refined features.

Instead, use the graph branch as:

1. an auxiliary training branch, or
2. a teacher branch for feature distillation.

Recommended design:

```text
Image
  -> Visual Backbone / Table Transformer Encoder
  -> Cell Features / Object Queries
  -> Structure Prediction Head
  -> Output Predictions

Training only:
Ground Truth Cells + Ground Truth Relations
  -> Build Cell Graph
  -> GNN Teacher / Graph Auxiliary Head
  -> Graph Loss / Distillation Loss
```

At inference time:

```text
Image
  -> Visual Backbone / Table Transformer Encoder
  -> Cell Features / Object Queries
  -> Structure Prediction Head
  -> Output Predictions
```

---

## 5. Model Components

### 5.1 Visual Backbone

Use a Table Transformer-style architecture as the baseline.

Possible starting point:

- CNN backbone + Transformer encoder-decoder
- DETR-style object queries
- prediction heads for cells, rows, columns, or table structure elements

The baseline should be implemented first before adding graph-guided training.

### 5.2 Cell Feature Extractor

The model should expose intermediate visual features for each predicted or matched cell.

During training, predicted queries can be matched to ground-truth cells using Hungarian matching or the same matching strategy used by the baseline.

For each matched cell, obtain a visual cell feature:

```text
cell_feature_i = feature of matched query i
```

These cell features will be used for auxiliary graph supervision or distillation.

### 5.3 Graph Construction

During training, construct a graph from ground-truth table annotations.

Each cell is a node.

Node attributes may include:

- bounding box coordinates
- normalized bounding box coordinates
- row index
- column index
- row span
- column span
- optional text embedding if OCR text is available

For the simplest experiment, use only geometry and logical position.

Recommended node feature:

```text
[x1, y1, x2, y2, width, height, center_x, center_y, row_index, col_index, row_span, col_span]
```

All coordinates should be normalized by image width and height.

### 5.4 Edge Types

Start with a simple set of edge types.

Recommended phase-1 edge types:

```text
same_row
same_column
right_neighbor
down_neighbor
```

Optional phase-2 edge type:

```text
header_of
```

Avoid adding too many relation types at the beginning. More relation types increase annotation complexity and may introduce noisy supervision.

### 5.5 GNN Branch

Use a simple Graph Neural Network for the first implementation.

Recommended options:

- GraphSAGE
- GCN
- GAT
- Relational GCN if edge types are used explicitly

For phase 1, a small relational GNN is enough.

Example design:

```text
Input node features
  -> Linear projection
  -> 2-layer R-GCN / GraphSAGE
  -> Graph-enhanced node embeddings
  -> Relation prediction head
```

The GNN branch is used only during training.

---

## 6. Loss Design

The total training loss can be written as:

```text
L_total = L_baseline + lambda_graph * L_graph_aux + lambda_distill * L_distill
```

Where:

- `L_baseline` is the original Table Transformer / TSR loss
- `L_graph_aux` is the graph relation prediction loss
- `L_distill` is the distillation loss between visual cell features and graph-enhanced features

### 6.1 Baseline Loss

This is the original loss used by the baseline model.

Depending on the implementation, it may include:

- bounding box loss
- class loss
- GIoU loss
- row/column classification loss
- cell structure loss
- spanning cell loss

Do not change the baseline loss at first.

### 6.2 Graph Auxiliary Loss

The graph branch predicts relations between cell pairs.

For a pair of cells `(i, j)`, predict whether relation `r` exists.

Example relations:

```text
same_row(i, j)
same_column(i, j)
right_neighbor(i, j)
down_neighbor(i, j)
```

This can be formulated as multi-label classification:

```text
relation_logits_ij = MLP([h_i, h_j, h_i - h_j, h_i * h_j])
```

Use binary cross-entropy loss for relation prediction:

```text
L_graph_aux = BCEWithLogitsLoss(relation_logits, relation_labels)
```

### 6.3 Feature Distillation Loss

The graph branch produces graph-enhanced cell embeddings.

The visual branch produces image-only cell embeddings.

The distillation loss encourages the visual branch to learn graph-aware structural representations.

Example:

```text
L_distill = MSE(project_visual(cell_feature_i), stop_gradient(project_graph(graph_feature_i)))
```

Use `stop_gradient` on the graph teacher representation if the graph branch is treated as a teacher.

A simple version:

```text
visual_proj = Linear(cell_visual_feature)
graph_proj = Linear(graph_node_embedding)
L_distill = MSE(visual_proj, graph_proj.detach())
```

---

## 7. Training and Inference Behavior

### 7.1 Training

Training uses both the image branch and the graph branch.

Training inputs:

```text
image
ground_truth_cells
ground_truth_cell_boxes
ground_truth_logical_positions
ground_truth_relations
```

Training outputs:

```text
baseline_predictions
graph_relation_predictions
graph_node_embeddings
```

Training losses:

```text
baseline_loss
graph_auxiliary_loss
distillation_loss
```

### 7.2 Inference

Inference uses only the image branch.

Inference input:

```text
image
```

Inference output:

```text
predicted table structure
```

No graph is required during inference.

This keeps the deployment pipeline simple.

---

## 8. Annotation Format

The dataset should provide cell-level annotations.

Each table should include:

```json
{
  "image_id": "sample_001",
  "width": 1000,
  "height": 800,
  "cells": [
    {
      "cell_id": "c1",
      "bbox": [50, 100, 200, 150],
      "row_index": 0,
      "col_index": 0,
      "row_span": 1,
      "col_span": 1,
      "text": "Header A",
      "role": "header"
    },
    {
      "cell_id": "c2",
      "bbox": [200, 100, 350, 150],
      "row_index": 0,
      "col_index": 1,
      "row_span": 1,
      "col_span": 1,
      "text": "Header B",
      "role": "header"
    }
  ],
  "relations": [
    {
      "source": "c1",
      "target": "c2",
      "type": "right_neighbor"
    },
    {
      "source": "c1",
      "target": "c2",
      "type": "same_row"
    }
  ]
}
```

Relations can be generated automatically from logical positions. Manual relation annotation is not required for the initial experiment.

---

## 9. Automatic Relation Generation

Given annotated cells with row and column indices, generate graph relations automatically.

### 9.1 same_row

Two cells have a `same_row` relation if their row ranges overlap.

```text
cell_a.row_range intersects cell_b.row_range
```

### 9.2 same_column

Two cells have a `same_column` relation if their column ranges overlap.

```text
cell_a.col_range intersects cell_b.col_range
```

### 9.3 right_neighbor

Cell `b` is the right neighbor of cell `a` if:

- they overlap in row range
- `b` starts immediately after the right boundary of `a` in logical column space

Example:

```text
a.col_end + 1 == b.col_start
```

### 9.4 down_neighbor

Cell `b` is the down neighbor of cell `a` if:

- they overlap in column range
- `b` starts immediately after the bottom boundary of `a` in logical row space

Example:

```text
a.row_end + 1 == b.row_start
```

---

## 10. Experiment Plan

Implement and compare at least three settings.

### 10.1 Experiment A: Baseline

Train the original Table Transformer-style model.

```text
Train: image only
Infer: image only
```

Purpose:

- establish baseline performance

### 10.2 Experiment B: Graph-Auxiliary Training

Train the model with additional graph auxiliary loss.

```text
Train: image + graph auxiliary loss
Infer: image only
```

Purpose:

- test whether graph supervision improves the visual model

### 10.3 Experiment C: Graph Distillation

Train the model with graph teacher representation and feature distillation.

```text
Train: image + graph teacher + distillation loss
Infer: image only
```

Purpose:

- test whether graph-enhanced features can be transferred into the image-only branch

### 10.4 Optional Experiment D: Graph at Inference

Use predicted cells to construct a graph during inference and run the GNN branch.

```text
Train: image + graph
Infer: image + predicted graph
```

Purpose:

- estimate the upper bound of graph usefulness
- compare runtime complexity versus accuracy gain

This experiment is optional because it makes inference more complex.

---

## 11. Evaluation Metrics

Use the same evaluation metrics as the baseline TSR task.

Recommended metrics:

- cell detection precision / recall / F1
- row structure accuracy
- column structure accuracy
- adjacency relation F1
- TEDS if HTML output is available
- exact table structure match if feasible

For graph-specific evaluation during training, also measure:

- same-row relation F1
- same-column relation F1
- right-neighbor relation F1
- down-neighbor relation F1

The most important comparison is:

```text
Graph-guided image-only inference vs baseline image-only inference
```

---

## 12. Expected Outcomes

Possible outcomes:

### Case 1: Graph-guided training improves baseline

This means graph supervision helps the visual branch learn better table structure representations.

This is the desired result.

### Case 2: Graph-guided training is similar to baseline

This may mean:

- graph loss is too weak
- graph labels are not informative enough
- graph branch is not well aligned with TSR output
- distillation is not effective

### Case 3: Graph-guided training is worse than baseline

This may mean:

- relation labels are noisy
- graph loss weight is too high
- graph features are leaking information in a way that hurts visual learning
- train-inference mismatch still exists

### Case 4: Graph-at-inference is much better than graph-guided inference

This means graph reasoning is useful, but it may need to be part of the runtime pipeline.

---

## 13. Implementation Tasks for Agentic Coder

### Task 1: Prepare Baseline

- Load or implement a Table Transformer-style TSR baseline.
- Train and evaluate the baseline on the target dataset.
- Save baseline metrics.

### Task 2: Define Cell Annotation Schema

- Ensure each cell has:
  - `cell_id`
  - `bbox`
  - `row_index`
  - `col_index`
  - `row_span`
  - `col_span`
  - optional `text`
  - optional `role`

### Task 3: Implement Relation Generator

Create a utility function:

```python
def build_cell_relations(cells):
    """
    Build graph relations from cell logical positions.

    Returns:
        relations: list of dictionaries with source, target, and type.
    """
```

Required relation types:

```text
same_row
same_column
right_neighbor
down_neighbor
```

### Task 4: Implement Graph Dataset Wrapper

Extend the dataset loader to return:

```python
{
    "image": image,
    "baseline_targets": baseline_targets,
    "graph_nodes": graph_nodes,
    "graph_edges": graph_edges,
    "graph_edge_types": graph_edge_types,
    "relation_labels": relation_labels
}
```

### Task 5: Implement GNN Branch

Implement a lightweight GNN module:

```python
class GraphTeacher(nn.Module):
    def __init__(self, node_dim, hidden_dim, num_layers, num_relation_types):
        ...

    def forward(self, node_features, edge_index, edge_type):
        ...
```

The output should include:

```python
graph_node_embeddings
relation_logits
```

### Task 6: Implement Graph Auxiliary Loss

Implement relation prediction loss:

```python
loss_graph_aux = BCEWithLogitsLoss(relation_logits, relation_labels)
```

### Task 7: Implement Distillation Loss

Implement feature alignment between visual cell features and graph node embeddings:

```python
loss_distill = MSELoss(visual_projection(cell_features), graph_projection(graph_embeddings).detach())
```

### Task 8: Add Loss Weights

Add config options:

```yaml
lambda_graph: 0.5
lambda_distill: 0.5
use_graph_aux: true
use_graph_distill: true
```

Total loss:

```python
loss = baseline_loss + lambda_graph * loss_graph_aux + lambda_distill * loss_distill
```

### Task 9: Disable Graph Branch During Inference

Ensure inference only calls the image-based model path.

There should be no dependency on graph inputs during inference.

### Task 10: Run Experiments

Run these experiments:

```text
A. Baseline
B. Baseline + graph auxiliary loss
C. Baseline + graph distillation
D. Optional: graph at inference
```

Save metrics for each experiment.

---

## 14. Suggested Project Structure

```text
project/
  configs/
    baseline.yaml
    graph_aux.yaml
    graph_distill.yaml

  datasets/
    table_dataset.py
    graph_builder.py

  models/
    table_transformer.py
    graph_teacher.py
    relation_head.py
    distillation.py

  losses/
    baseline_loss.py
    graph_loss.py
    distill_loss.py

  train.py
  evaluate.py
  infer.py

  experiments/
    README.md
```

---

## 15. Minimal Pseudocode

```python
def training_step(batch):
    image = batch["image"]
    baseline_targets = batch["baseline_targets"]

    outputs = table_model(image, targets=baseline_targets, return_cell_features=True)

    baseline_loss = compute_baseline_loss(outputs, baseline_targets)

    total_loss = baseline_loss

    if cfg.use_graph_aux or cfg.use_graph_distill:
        graph_nodes = batch["graph_nodes"]
        graph_edges = batch["graph_edges"]
        graph_edge_types = batch["graph_edge_types"]
        relation_labels = batch["relation_labels"]

        graph_outputs = graph_teacher(
            node_features=graph_nodes,
            edge_index=graph_edges,
            edge_type=graph_edge_types,
        )

        if cfg.use_graph_aux:
            graph_loss = compute_graph_relation_loss(
                graph_outputs["relation_logits"],
                relation_labels,
            )
            total_loss = total_loss + cfg.lambda_graph * graph_loss

        if cfg.use_graph_distill:
            distill_loss = compute_distillation_loss(
                outputs["matched_cell_features"],
                graph_outputs["node_embeddings"],
            )
            total_loss = total_loss + cfg.lambda_distill * distill_loss

    return total_loss
```

Inference pseudocode:

```python
def inference(image):
    outputs = table_model(image)
    table_structure = decode_table_structure(outputs)
    return table_structure
```

---

## 16. Important Notes

- The graph branch must not be required during inference.
- Avoid using graph-refined features directly as the only input to the prediction head.
- Use graph supervision as an auxiliary loss or teacher signal.
- Keep relation types simple in the first experiment.
- Generate relations automatically from cell logical positions to avoid expensive manual graph annotation.
- Carefully tune `lambda_graph` and `lambda_distill`.
- Always compare against the image-only baseline.

---

## 17. Recommended First Milestone

The first milestone should be small and measurable:

1. Train the image-only baseline.
2. Add automatic graph relation generation.
3. Add graph auxiliary relation prediction loss.
4. Train with graph auxiliary loss.
5. Compare metrics with baseline.

Only after this works, add graph distillation.

---

## 18. Summary

This experiment investigates whether graph supervision can improve table structure recognition without increasing inference complexity.

The preferred approach is:

```text
Training: image model + graph auxiliary teacher
Inference: image model only
```

This can be described as:

> Graph-guided training for image-only table structure recognition.

or:

> Graph distillation for table structure recognition.

This design is suitable for an experimental research prototype because it keeps deployment simple while still testing whether graph features improve structural learning.
