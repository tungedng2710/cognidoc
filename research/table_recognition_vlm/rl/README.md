# Table Recognition RLVR

Fine-tunes `Qwen/Qwen3.5-4B` with vision GRPO and verifiable rewards on
`tungedng2710/table_html_with_reasoning`. The policy input is one or more table
images and the policy output is only complete `<table>...</table>` HTML.

## Dataset Findings

The Hugging Face dataset has 28,341 train rows and 3,149 test rows. Its columns
include `images`, `table_html`, a `logical_table_reasoning_v1.0` JSON trace,
table dimensions, cell count, merged-cell status, and validation status.
Some labels are full HTML documents; preprocessing extracts only their complete
`<table>...</table>` element before they are passed to the verifier.

The trace is structured privileged supervision, not a desirable model output.
It contains cell coordinates and spans, a logical grid, relations, validation
checks, and a deterministic placement trace. Including it in the prompt would
leak the answer; training the model to emit it would also conflict with the
HTML-only inference contract. This implementation therefore:

- never puts reasoning in the prompt or completion;
- uses `num_rows`, `num_cols`, `num_cells`, and `has_merged_cells`, which are
  compact facts materialized from the trace, as private verifier inputs;
- removes the raw reasoning JSON before training because it is very large;
- filters `validation_passed=False` rows by default (535 train rows); and
- keeps the test split separate for evaluation.

All current rows contain one image, but the prompt and trainer retain list-of-
images support.

## Rewards

`reward.py` contains deterministic rewards with no learned reward model:

| Reward | Weight | Purpose |
| --- | ---: | --- |
| `format_reward` | 0.25 | Exactly one balanced table, no prose, reasoning, or Markdown |
| `exact_reward` | 1.0 | Canonical HTML match while ignoring indentation and attribute order |
| `structure_reward` | 1.0 | Ordered table/section/row/cell tags and rowspan/colspan agreement |
| `content_reward` | 1.0 | Ordered normalized visible-text token agreement by cell |
| `reasoning_metadata_reward` | 0.5 | Rows, logical columns, physical cells, and merged-cell status match trace facts |

The dense structure and content rewards avoid the all-zero groups caused by an
exact-match-only verifier. The format reward enforces the deployment contract,
and exact match supplies a high-confidence terminal signal. Parsing results are
cached and sequence comparisons are linear in table size so reward computation
remains practical for long tables.

## Loss

Training uses TRL's clipped GRPO objective with group-relative advantages,
`epsilon=0.2`, and a small reference-policy KL coefficient `beta=0.001`.
`loss_type="dr_grpo"` uses a constant completion-length normalizer instead of
normalizing each sample by its generated length. This matters here because
table lengths vary substantially and per-sample normalization can bias updates
toward short outputs. Reward standard-deviation scaling is disabled as
recommended for Dr. GRPO, while rewards are still centered within each group.
Truncated completions are masked because a partial table should not become a
positive policy target. `loss.py` provides a small readable reference version;
the actual run uses TRL/Unsloth's optimized implementation.

The default `num_iterations=1` performs one update per sampled group, so the
old and current policies initially coincide and clipping is normally inactive.
Set `--num-iterations 2` or higher to reuse each sampled group for multiple
updates where the clipping bound becomes active, at additional compute cost.

## Install

Activate the requested environment and install any missing dependencies:

```bash
conda activate tungn197
pip install -U unsloth unsloth_zoo datasets trl accelerate pillow torch
```

The implementation was checked against Unsloth `2026.6.9`, TRL `0.24.0`,
Transformers `5.13.1`, and Datasets `4.3.0`.

## Validate

Run unit tests and a dataset dry run before allocating the model:

```bash
conda activate tungn197
python -m unittest -v test_reward.py test_loss.py
python grpo.py --dry-run --max-train-samples 16 --max-eval-samples 8
```

## Train

The default is 4-bit QLoRA, four sampled completions per image, an effective
generation batch of four, and 500 optimizer steps:

```bash
conda activate tungn197
python grpo.py
```

Use 16-bit LoRA or language-only adapters when appropriate:

```bash
python grpo.py --load-in-16bit
python grpo.py --language-only
```

Resume from a trainer checkpoint:

```bash
python grpo.py --resume-from-checkpoint qwen35_4b_table_html_grpo/checkpoint-100
```

Both the effective training generation batch and global evaluation batch must
be divisible by `num_generations`. Long references can exceed the default
8,192-token generation cap; truncated outputs are intentionally excluded from
the policy loss. Increase both `--max-completion-length` and, if necessary,
`--max-seq-length` when memory permits. For a cold base model that produces no
valid tables across a generation group, run supervised table-HTML fine-tuning
before RLVR. Colocated vLLM is intentionally disabled because the checked
Unsloth release does not support this Qwen3.5 vision training path reliably.
