# AuxGraphTATR Training Guide

AuxGraphTATR implements the training-only graph branch described in
`aux_graph_guided_table_structure_recognition.md`.

The inference path is unchanged from the baseline Table Transformer:

```text
image -> backbone -> transformer -> class/bbox heads -> predictions
```

During training only, targets are passed into the model and a ground-truth graph
branch adds:

```text
total_loss = DETR_loss
           + lambda_graph * graph_relation_BCE
           + lambda_distill * visual_graph_MSE
```

## Files

| File | Purpose |
|---|---|
| `detr/models/aux_graph_tatr.py` | AuxGraphTATR model and graph losses |
| `src/train_aux_graph_tatr.py` | training/evaluation entrypoint |
| `src/aux_graph_tatr_config.json` | default config |
| `scripts/train_aux_graph_tatr_hard200.sh` | convenience launcher |
| `src/export_aux_graph_tatr_pth.py` | TorchScript `.pth` export for visualization |

## Train

```bash
cd research/table_recognition/baselines/table-transformer/src
python train_aux_graph_tatr.py \
  --data_type structure \
  --config_file aux_graph_tatr_config.json \
  --data_root_dir /path/to/structure_data \
  --model_save_dir /path/to/output/aux_graph_tatr
```

Or use the hard-200 launcher:

```bash
cd research/table_recognition/baselines/table-transformer
DATA_ROOT=/path/to/structure_data \
OUTPUT_DIR=/path/to/output/aux_graph_tatr \
scripts/train_aux_graph_tatr_hard200.sh
```

## Load A Baseline Checkpoint

```bash
python train_aux_graph_tatr.py \
  --data_type structure \
  --config_file aux_graph_tatr_config.json \
  --data_root_dir /path/to/structure_data \
  --model_load_path /path/to/baseline/model.pth \
  --load_weights_only \
  --model_save_dir /path/to/output/aux_graph_tatr
```

Baseline Table Transformer weights are mapped into `base.*`. The auxiliary graph
branch is initialized from scratch.

## Strategies

| Strategy | Effect |
|---|---|
| `full` | train the whole image model plus aux graph branch |
| `decoder_aux` | freeze backbone/encoder, train decoder, heads, and aux branch |
| `aux_only` | freeze the image model; useful only for graph-head sanity checks |

Default is `full`, because the auxiliary graph losses are meant to improve the
image-only model used at inference.

## Export `.pth` For Visualization

```bash
cd research/table_recognition/baselines/table-transformer/src
python export_aux_graph_tatr_pth.py \
  --checkpoint /path/to/output/aux_graph_tatr/model_best.pth \
  --output ../artifacts/aux_graph_tatr_image_only_torchscript.pth
```

The exported `.pth` is a traced TorchScript model of the deployable image-only
path. The training-only graph branch is intentionally absent from this export.
