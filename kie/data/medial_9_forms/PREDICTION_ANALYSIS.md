# NuExtract Prediction Analysis

The prediction files contain the model's extracted JSON using the structure
requested by each template. They are stored in [`predictions/`](predictions/),
with one prediction file for each input PDF.

## Overall results

| Metric | Value | Meaning |
| --- | ---: | --- |
| Macro score | 0.7905 | Average document score, giving every PDF equal weight |
| Micro score | 0.7864 | Score across all evaluated leaf fields |
| Macro exact accuracy | 0.6736 | Average exact field accuracy per document |
| Micro exact accuracy | 0.7132 | Exact accuracy across all evaluated leaf fields |
| Macro key F1 | 0.9157 | How accurately the predictions reproduced the expected JSON paths |

String values receive partial credit based on normalized indel similarity.
Numbers, Booleans, nulls, and other non-string values require an exact match.
Missing and additional leaf paths receive a score of zero.

## Metric formulas

Let `G` be the flattened ground-truth JSON and `P` the flattened prediction.
Object keys and array indexes form each leaf path. For example,
`rows[0].result` is one leaf path. Evaluation is performed over the union of
the paths in `G` and `P`, so both missing and extra prediction fields affect the
score.

Before comparing strings, consecutive whitespace is replaced by one space and
leading or trailing whitespace is removed. Let this normalized value be
`N(value)`.

### String leaf score

For two strings, the evaluator uses normalized indel similarity:

```text
                       2 × LCS(N(gt), N(pred))
string_score = -----------------------------------------
                length(N(gt)) + length(N(pred))
```

`LCS` is the length of the longest common subsequence. The score is `1` for
identical normalized strings and approaches `0` as they become less similar.
If both strings are empty, the score is `1`; if only one is empty, it is `0`.

### Non-string leaf score

Numbers, Booleans, nulls, empty containers, and other non-string leaves use
type-aware exact matching:

```text
non_string_score = 1  if type(gt) = type(pred) and gt = pred
                   0  otherwise
```

This prevents values such as Boolean `true` and integer `1` from being treated
as equivalent. A missing or extra leaf also receives `0`.

### Document score

Let `U` be the union of ground-truth and prediction leaf paths:

```text
                 sum of leaf_score(path) for every path in U
document_score = --------------------------------------------
                                  |U|
```

### Exact accuracy

```text
                 number of exactly matching leaves
exact_accuracy = ---------------------------------
                               |U|
```

Whitespace-normalized string equality is considered exact. All other values
must have the same type and value.

### Key precision, recall, and F1

```text
                |paths(G) ∩ paths(P)|
key_precision = ---------------------
                      |paths(P)|

             |paths(G) ∩ paths(P)|
key_recall = ---------------------
                   |paths(G)|

         2 × key_precision × key_recall
key_F1 = --------------------------------
              key_precision + key_recall
```

### Macro and micro scores

```text
              sum of document scores
macro_score = ----------------------
                number of documents

              sum of all leaf scores across all documents
micro_score = --------------------------------------------
               number of union paths across all documents
```

Macro scoring gives every document equal weight. Micro scoring gives every leaf
equal weight, so documents with large tables contribute more heavily.

## Worked metric example

Ground truth:

```json
{
  "name": "Nguyễn Thị Đeng",
  "age": 67
}
```

Prediction:

```json
{
  "name": "Nguyễn Thị Deng",
  "age": 67,
  "room": "H001"
}
```

The union contains three leaf paths:

| Path | Ground truth | Prediction | Leaf score | Reason |
| --- | --- | --- | ---: | --- |
| `name` | `Nguyễn Thị Đeng` | `Nguyễn Thị Deng` | 0.9333 | One-character OCR difference; partial indel credit |
| `age` | `67` | `67` | 1.0000 | Exact integer match |
| `room` | missing | `H001` | 0.0000 | Extra prediction field |

The resulting metrics are:

```text
document_score = (0.9333 + 1.0000 + 0.0000) / 3 = 0.6444
exact_accuracy = 1 / 3                            = 0.3333
key_precision  = 2 / 3                            = 0.6667
key_recall     = 2 / 2                            = 1.0000
key_F1         = 2 × 0.6667 × 1 / (0.6667 + 1)   = 0.8000
```

This example demonstrates why a prediction can contain nearly correct text and
all required fields but still lose substantial document-level score when it
adds fields that are not present in the ground truth.

## Per-document analysis

| Document | Score | Exact | Key F1 | Analysis |
| --- | ---: | ---: | ---: | --- |
| `2300030376-23` | 0.981 | 0.950 | 1.000 | Excellent result. All 100 fields and all 15 laboratory rows were returned. Differences were mainly accents, timestamp formatting, and a missing signer credential. |
| `2300030376-24-25` | 0.511 | 0.403 | 0.681 | All ground-truth fields were found, but the model extracted 10 care records while the ground truth contains 4. The resulting 30 additional leaves were penalized. |
| `2300030376-3` | 0.965 | 0.818 | 1.000 | Excellent structure and content extraction. Most differences were formatting variations, such as a numeric date versus a Vietnamese written date. |
| `2300030376-34` | 0.593 | 0.400 | 1.000 | All 16 vital-sign rows and all expected paths were present. The dense grid values were frequently shifted or misread, and blank cells were often returned as `null` instead of empty strings. |
| `2300030376-38-41` | 0.543 | 0.310 | 0.739 | The ground truth contains one treatment record, while the model extracted five records from the four-page PDF. The 12 additional leaves caused much of the penalty. |
| `2300030376-4` | 0.979 | 0.857 | 1.000 | Near-perfect extraction with every expected field present. Differences were limited to minor OCR and timestamp-format variations. |
| `2300030376-60` | 0.933 | 0.769 | 1.000 | Strong result with a complete JSON structure. Differences included an incomplete national heading and placeholder dots being extracted instead of `null`. |
| `2300030376-61` | 0.789 | 0.759 | 0.910 | Good billing extraction, but one group or summary structure was misaligned. The prediction had 7 missing and 24 additional leaves. |
| `2300030376-62-63` | 0.821 | 0.794 | 0.912 | All 424 expected paths were found. The model extracted eight service groups while the ground truth contains five, producing 82 additional leaves. A few date-cell values were also shifted. |

## Important interpretation caveat

The lower scores for `2300030376-24-25` and `2300030376-38-41` do not
automatically mean that the additional predicted records are hallucinations.
The model may have extracted visible records from the complete PDFs that are not
included in the reference JSON. Those rows should be checked against the source
PDFs before treating them as errors.

The same issue affects `2300030376-62-63`: the prediction contains three more
service groups than the ground truth. The evaluator intentionally penalizes
these additional paths because it treats the supplied ground truth as complete.

## Error patterns

The predictions show four recurring error patterns:

1. **Formatting differences.** Dates and times can be returned in written form
   instead of the exact printed representation.
2. **Minor OCR differences.** Vietnamese accents and medical credentials can be
   misread, such as `Đeng` becoming `Deng`.
3. **Blank-cell representation.** Empty table cells may be returned as `null`,
   an empty string, placeholder dots, or occasionally `0`.
4. **Table-row alignment.** Dense forms can produce shifted values or additional
   rows, particularly when the PDF contains more visible entries than the
   ground-truth JSON.

## Reproducing the evaluation

Generate predictions:

```bash
conda activate tungn197
python data/medial_9_forms/predict.py --force --concurrency 2
```

Evaluate them:

```bash
python data/medial_9_forms/eval.py \
  --report data/medial_9_forms/evaluation_report.json \
  --show-errors 3
```

The complete machine-readable metrics are available in
[`evaluation_report.json`](evaluation_report.json).
