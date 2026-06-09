# GraphTATR Training Guide

GraphTATR adds a small graph refinement module after the Table Transformer decoder for table structure recognition. It uses decoder queries as graph nodes, builds edges from the initial predicted boxes, and predicts refined class logits and bounding boxes.

## Files

- `detr/models/graph_tatr.py`: GraphTATR model, graph builder, and graph attention layers.
- `src/train_graph_tatr.py`: training/evaluation entrypoint.
- `src/export_graph_tatr_netron.py`: dummy-input export utility for Netron.
- `src/graph_tatr_config.json`: default structure-recognition graph config.
- `GRAPH_TATR_ARCHITECTURE.md`: visual architecture diagrams.
- `graph_tatr_implementation_guide.md`: experiment design and modeling rationale.

## Data Format

Use the same PASCAL VOC-style structure dataset expected by the original Table Transformer code:

```text
/path/to/structure_data/
|-- images/
|   |-- table_0001.jpg
|   `-- ...
|-- train/
|   |-- table_0001.xml
|   `-- ...
|-- val/
|   `-- ...
|-- test/
|   `-- ...
|-- train_filelist.txt
|-- val_filelist.txt
`-- test_filelist.txt
```

For structure recognition, labels follow the existing class map:

```text
0 table
1 table column
2 table row
3 table column header
4 table projected row header
5 table spanning cell
6 no object
```

## 1. Train Or Load Baseline TATR

Train the normal Table Transformer baseline first:

```bash
cd research/table_recognition/baselines/table-transformer/src
python main.py \
  --data_type structure \
  --config_file structure_config.json \
  --data_root_dir /path/to/structure_data \
  --model_save_dir /path/to/output/tatr_baseline
```

You can also start from an existing baseline checkpoint such as:

```text
/path/to/output/tatr_baseline/model_20.pth
```

## 2. Train Graph Head With Frozen Base

This is the recommended first graph experiment. It freezes the base Table Transformer and trains only the GNN plus refined prediction heads.

```bash
cd research/table_recognition/baselines/table-transformer/src
python train_graph_tatr.py \
  --data_type structure \
  --config_file graph_tatr_config.json \
  --data_root_dir /path/to/structure_data \
  --model_load_path /path/to/output/tatr_baseline/model_20.pth \
  --load_weights_only \
  --train_strategy graph_only \
  --model_save_dir /path/to/output/graph_tatr_graph_only
```

`train_graph_tatr.py` can load either baseline TATR weights or GraphTATR weights. When loading a baseline checkpoint, it maps baseline weights into `base.*` and initializes the refined class/bbox heads from the baseline heads.

## 3. Fine-Tune Decoder Plus Graph

After graph-only training works, unfreeze the decoder, object queries, and original prediction heads:

```bash
python train_graph_tatr.py \
  --data_type structure \
  --config_file graph_tatr_config.json \
  --data_root_dir /path/to/structure_data \
  --model_load_path /path/to/output/graph_tatr_graph_only/model.pth \
  --load_weights_only \
  --train_strategy decoder_graph \
  --initial_loss_coef 1.0 \
  --model_save_dir /path/to/output/graph_tatr_decoder_graph
```

Use `--initial_loss_coef 1.0` if you want the original TATR heads to keep receiving DETR loss while the refined graph output is trained. The refined graph loss is controlled by `--lambda_graph`, default `1.0`.

## 4. Optional Full Fine-Tune

Full fine-tuning can overfit on small subsets, so run it after the frozen-base and decoder+graph experiments:

```bash
python train_graph_tatr.py \
  --data_type structure \
  --config_file graph_tatr_config.json \
  --data_root_dir /path/to/structure_data \
  --model_load_path /path/to/output/graph_tatr_decoder_graph/model.pth \
  --load_weights_only \
  --train_strategy full \
  --initial_loss_coef 1.0 \
  --model_save_dir /path/to/output/graph_tatr_full
```

## 5. Evaluate

For COCO AP/mAP only:

```bash
python train_graph_tatr.py \
  --mode eval \
  --data_type structure \
  --config_file graph_tatr_config.json \
  --data_root_dir /path/to/structure_data \
  --model_load_path /path/to/output/graph_tatr_graph_only/model_20.pth
```

For structure metrics that need table words, provide the words JSON directory:

```bash
python train_graph_tatr.py \
  --mode eval \
  --data_type structure \
  --config_file graph_tatr_config.json \
  --data_root_dir /path/to/structure_data \
  --model_load_path /path/to/output/graph_tatr_graph_only/model_20.pth \
  --table_words_dir /path/to/table_words_json
```

## Useful Ablations

Run the same dataset split and compare validation/test AP:

```bash
# kNN edges only
python train_graph_tatr.py ... \
  --graph_use_knn_edges \
  --no_graph_use_geometry_edges \
  --model_save_dir /path/to/output/graph_tatr_knn

# geometry overlap edges only
python train_graph_tatr.py ... \
  --no_graph_use_knn_edges \
  --graph_use_geometry_edges \
  --model_save_dir /path/to/output/graph_tatr_geometry

# add bbox features to query node features
python train_graph_tatr.py ... \
  --graph_use_bbox_features \
  --model_save_dir /path/to/output/graph_tatr_bbox_features

# add bbox and class probability features
python train_graph_tatr.py ... \
  --graph_use_bbox_features \
  --graph_use_class_features \
  --model_save_dir /path/to/output/graph_tatr_bbox_class_features
```

Primary comparison table:

| Model | mAP | AP50 | AP row | AP column | AP header | AP span | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Baseline TATR |  |  |  |  |  |  | Original model |
| GraphTATR graph only |  |  |  |  |  |  | Frozen base |
| GraphTATR decoder+graph |  |  |  |  |  |  | Decoder unfrozen |
| GraphTATR full |  |  |  |  |  |  | Full fine-tune |

## Notes

- The graph is built from predicted boxes during both training and inference.
- Default edges are `near`, `same_row_like`, `same_col_like`, plus self edges for stable message passing.
- Checkpoint `model.pth` contains optimizer state and can resume training. Checkpoints like `model_20.pth` are model weights only and should be loaded with `--load_weights_only`.
- Start with `train_strategy=graph_only`; it is the cleanest test of whether graph refinement adds value over the baseline.
