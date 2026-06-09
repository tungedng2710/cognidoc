# Graph Auxiliary Improvement Summary

Run folder:

```text
/root/tungn197/cognidoc/research/unitable_graph_aux_compare_run
```

Compared variants:

- `baseline`
- `graph_aux`

Training setup from `comparison_summary.json`:

- Epochs: 50
- Batch size: 32
- Learning rate: 0.0003
- Image size: 128
- Model dimension: 128
- Auxiliary losses:
  - `lambda_visual_rel`: 0.2
  - `lambda_graph_rel`: 0.1
  - `lambda_distill`: 0.1
- Relations:
  - `same_row`
  - `same_column`
  - `right_neighbor`
  - `down_neighbor`

## Main Result

Graph auxiliary training gives a small improvement in token-level HTML prediction, especially at the end of training, but it does not improve the measured structure-relation F1 in this run.

Important caveat: `graph_aux.loss` includes auxiliary graph/distillation terms, so compare `html_loss` against the baseline loss for the primary HTML objective.

## Best Validation Metrics

| Metric | Baseline | Graph Aux | Change | Interpretation |
|---|---:|---:|---:|---|
| `loss` | 0.2565 | 0.2790 | +0.0225 | Worse, but graph loss includes auxiliary terms |
| `html_loss` | 0.2565 | 0.2545 | -0.0020 | Better |
| `token_acc` | 0.9478 | 0.9509 | +0.0031 | Better |
| `cell_token_acc` | 0.9721 | 0.9502 | -0.0219 | Worse |
| `structure_relation_precision` | 1.0000 | 1.0000 | +0.0000 | No change |
| `structure_relation_recall` | 0.8544 | 0.8544 | +0.0000 | No change |
| `structure_relation_f1` | 0.9215 | 0.9215 | +0.0000 | No change |

Best validation epochs:

| Metric | Baseline Epoch | Graph Aux Epoch |
|---|---:|---:|
| `loss` | 10 | 17 |
| `html_loss` | 10 | 9 |
| `token_acc` | 26 | 26 |
| `cell_token_acc` | 48 | 24 |
| `structure_relation_f1` | 2 | 2 |

## Final Epoch Validation Metrics

| Metric | Baseline Epoch 50 | Graph Aux Epoch 50 | Change | Relative Change |
|---|---:|---:|---:|---:|
| `loss` | 0.3509 | 0.3630 | +0.0120 | -3.43% worse |
| `html_loss` | 0.3509 | 0.3302 | -0.0207 | +5.90% better |
| `token_acc` | 0.9280 | 0.9438 | +0.0158 | +1.70% better |
| `cell_token_acc` | 0.9419 | 0.9434 | +0.0015 | +0.16% better |
| `structure_relation_precision` | 1.0000 | 1.0000 | +0.0000 | 0.00% |
| `structure_relation_recall` | 0.8236 | 0.8236 | +0.0000 | 0.00% |
| `structure_relation_f1` | 0.9033 | 0.9033 | +0.0000 | 0.00% |

## `token_acc` vs `cell_token_acc`

`token_acc` measures accuracy over the full decoded output sequence. In a table-generation model, this usually includes structural HTML/table tokens, cell-related tokens, and any non-padding special tokens included by the training mask. It is the broadest token-level metric for the generated sequence.

`cell_token_acc` measures accuracy only over tokens associated with table cells or cell contents. It is narrower than `token_acc` and is more sensitive to whether the model predicts cell-level values at the correct positions.

| Metric | Scope | What It Indicates |
|---|---|---|
| `token_acc` | All decoded tokens | Overall sequence quality, including structure and cell tokens |
| `cell_token_acc` | Cell/value tokens only | Accuracy on cell-specific content or cell-token positions |

This difference matters for interpreting the result. Graph auxiliary supervision uses structural relations:

- `same_row`
- `same_column`
- `right_neighbor`
- `down_neighbor`

These relations directly supervise table layout and adjacency, not cell content. Therefore, graph auxiliary training can improve the overall sequence or structural-token behavior while not improving, or even slightly hurting, peak cell-token accuracy.

The likely reasons the best `cell_token_acc` is worse for `graph_aux` are:

- The auxiliary graph losses compete with the cell-token objective for model capacity and gradient budget.
- The graph losses emphasize structure, so the model may allocate more capacity to relation-aware representations than cell-content prediction.
- Sequence metrics are alignment-sensitive: if structural token choices shift where cell tokens appear, cell tokens can be counted wrong even when many local predictions are reasonable.
- The best validation epochs differ. Baseline reaches its best `cell_token_acc` at epoch 48, while `graph_aux` reaches its best at epoch 24. At the final epoch, `graph_aux` is slightly better on `cell_token_acc` than baseline.

In this run, the graph auxiliary branch appears to regularize the full sequence objective more than the cell-token objective. That matches the observed pattern: final `token_acc` and `html_loss` improve, while best `cell_token_acc` is worse.

## Auxiliary Relation Head

The auxiliary relation branch learned meaningful relation predictions.

| Metric | Best Validation | Epoch | Final Validation |
|---|---:|---:|---:|
| `visual_relation_loss` | 0.0489 | 18 | 0.0679 |
| `graph_relation_loss` | 0.0588 | 6 | 0.1728 |
| `distill_loss` | 0.0182 | 49 | 0.0189 |
| `aux_relation_precision` | 1.0000 | 1 | 0.9220 |
| `aux_relation_recall` | 0.9736 | 13 | 0.9562 |
| `aux_relation_f1` | 0.9586 | 14 | 0.9388 |

This shows that the graph auxiliary objective is learnable. The limitation is that this learned auxiliary signal did not improve the downstream structure-relation F1 reported by the main decoder.

## Validation Trend Snapshots

| Epoch | Baseline `html_loss` | Graph Aux `html_loss` | Baseline `token_acc` | Graph Aux `token_acc` | Baseline `structure_relation_f1` | Graph Aux `structure_relation_f1` | Graph Aux `aux_relation_f1` |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2.4262 | 2.4273 | 0.8343 | 0.8340 | 0.8137 | 0.8125 | 0.0501 |
| 2 | 1.4310 | 1.4340 | 0.8797 | 0.8797 | 0.9215 | 0.9215 | 0.0696 |
| 3 | 0.8384 | 0.8441 | 0.9300 | 0.9300 | 0.9033 | 0.9033 | 0.4253 |
| 5 | 0.3857 | 0.3995 | 0.9300 | 0.9300 | 0.9033 | 0.9033 | 0.6354 |
| 10 | 0.2565 | 0.2565 | 0.9286 | 0.9475 | 0.9033 | 0.9033 | 0.7686 |
| 20 | 0.2815 | 0.2658 | 0.9373 | 0.9466 | 0.9033 | 0.9033 | 0.9365 |
| 30 | 0.3085 | 0.2909 | 0.9331 | 0.9331 | 0.9033 | 0.9033 | 0.9306 |
| 40 | 0.3460 | 0.3227 | 0.9303 | 0.9399 | 0.9033 | 0.9033 | 0.9396 |
| 50 | 0.3509 | 0.3302 | 0.9280 | 0.9438 | 0.9033 | 0.9033 | 0.9388 |

## Conclusion

Graph auxiliary training improved the stability of the HTML/token objective near the end of training:

- Final `html_loss` improved by 0.0207 absolute, about 5.90%.
- Final `token_acc` improved by 0.0158 absolute, about 1.70%.
- Final `cell_token_acc` improved slightly by 0.0015 absolute.

However:

- Best `structure_relation_f1` did not improve.
- Final `structure_relation_f1` did not improve.
- Best `cell_token_acc` was worse for `graph_aux`.

Overall, this run supports the conclusion that the auxiliary graph objective is learnable and can regularize token generation, but it has not yet produced a measurable improvement in the main structure-relation F1 metric.
