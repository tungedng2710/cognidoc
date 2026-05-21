# Table Recognition TODO

## 1. Examine Public Datasets

Study PubTabNet and FinTabNet to understand available annotations, table formats, and task definitions.

- [ ] Download or locate dataset metadata and samples.
- [ ] Review annotation formats for cells, spans, structure, and text.
- [ ] Identify useful fields for graph-based table recognition.
- [ ] Note dataset limitations such as missing OCR, noisy labels, or domain bias.

## 2. Run Dataset EDA

Analyze table statistics to understand data quality and modeling difficulty.

- [ ] Count tables, rows, columns, merged cells, and empty cells.
- [ ] Measure distributions of table size and cell-span patterns.
- [ ] Inspect OCR/layout quality where available.
- [ ] Summarize train, validation, and test split characteristics.

## 3. Sample Dataset Subsets

Create small representative subsets for faster experiments and debugging.

- [ ] Define sampling criteria by table size, complexity, and document type.
- [ ] Build tiny, small, and medium subsets for iteration.
- [ ] Preserve difficult cases such as merged cells and irregular layouts.
- [ ] Save subset manifests with source IDs and split labels.

## 4. Construct Table Graphs

Convert sampled tables into graph representations suitable for graph-based models.

- [ ] Define nodes for cells, text boxes, or layout elements.
- [ ] Define edges for spatial, row, column, and adjacency relations.
- [ ] Attach visual features such as bounding boxes and page coordinates.
- [ ] Validate graph construction with visual or JSON debug outputs.

## 5. Define Graph Feature Schema

Standardize graph inputs so experiments are reproducible and easy to compare.

- [ ] Specify node features: text, bbox, row/column hints, and confidence.
- [ ] Specify edge features: relation type, distance, overlap, and direction.
- [ ] Define labels for structure prediction or cell relation prediction.
- [ ] Document input/output formats for training and evaluation.

## 6. Implement Non-Graph Baselines

Build baseline models that do not use graph features to establish comparison points.

- [ ] Implement rule-based or heuristic structure extraction.
- [ ] Train simple ML/deep models using text and layout features only.
- [ ] Evaluate on sampled subsets first.
- [ ] Record baseline metrics and failure cases.

## 7. Develop Graph-Based Baselines

Add graph features and graph models to test whether structure improves recognition.

- [ ] Implement a simple GNN baseline.
- [ ] Train with spatial and structural edge features.
- [ ] Compare node classification, edge classification, or relation prediction setups.
- [ ] Analyze cases where graph features help or fail.

## 8. Compare Models

Evaluate non-graph and graph-based methods using consistent metrics and splits.

- [ ] Choose metrics for table structure, cell matching, and text alignment.
- [ ] Run experiments on the same sampled subsets.
- [ ] Compare accuracy, robustness, runtime, and complexity.
- [ ] Summarize findings and next research directions.
