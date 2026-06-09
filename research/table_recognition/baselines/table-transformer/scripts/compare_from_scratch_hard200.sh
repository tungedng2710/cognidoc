#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TATR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${TATR_ROOT}/../../../.." && pwd)"

DATA_ROOT="${DATA_ROOT:-${REPO_ROOT}/research/table_recognition/datasets/subsets/pubtables_hard_200_official}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
EXP_ROOT="${EXP_ROOT:-${REPO_ROOT}/research/table_recognition/outputs/hard200_from_scratch_${RUN_ID}}"

DEVICE="${DEVICE:-cuda}"
EPOCHS="${EPOCHS:-20}"
BATCH_SIZE="${BATCH_SIZE:-2}"
NUM_WORKERS="${NUM_WORKERS:-1}"
RUN_EVAL="${RUN_EVAL:-1}"
GRAPH_INITIAL_LOSS_COEF="${GRAPH_INITIAL_LOSS_COEF:-1.0}"

TRAIN_MAX_SIZE="${TRAIN_MAX_SIZE:-}"
VAL_MAX_SIZE="${VAL_MAX_SIZE:-}"
TEST_MAX_SIZE="${TEST_MAX_SIZE:-}"

TATR_OUTPUT_DIR="${TATR_OUTPUT_DIR:-${EXP_ROOT}/tatr_no_graph}"
GRAPH_OUTPUT_DIR="${GRAPH_OUTPUT_DIR:-${EXP_ROOT}/graph_tatr_full}"

LOG_DIR="${LOG_DIR:-${EXP_ROOT}/logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/compare_from_scratch_$(date +%Y%m%d_%H%M%S).log}"
mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

COMMON_ENV=(
  "DATA_ROOT=${DATA_ROOT}"
  "DEVICE=${DEVICE}"
  "EPOCHS=${EPOCHS}"
  "BATCH_SIZE=${BATCH_SIZE}"
  "NUM_WORKERS=${NUM_WORKERS}"
)

if [[ -n "${TRAIN_MAX_SIZE}" ]]; then
  COMMON_ENV+=("TRAIN_MAX_SIZE=${TRAIN_MAX_SIZE}")
fi

if [[ -n "${VAL_MAX_SIZE}" ]]; then
  COMMON_ENV+=("VAL_MAX_SIZE=${VAL_MAX_SIZE}")
fi

echo "Experiment root: ${EXP_ROOT}"
echo "Dataset: ${DATA_ROOT}"
echo "Master log file: ${LOG_FILE}"
echo "Training baseline TATR without graph from scratch..."
env "${COMMON_ENV[@]}" \
  "OUTPUT_DIR=${TATR_OUTPUT_DIR}" \
  "LOG_DIR=${TATR_OUTPUT_DIR}/logs" \
  "${SCRIPT_DIR}/train_tatr_hard200.sh"

echo "Training GraphTATR with graph from scratch..."
env "${COMMON_ENV[@]}" \
  "OUTPUT_DIR=${GRAPH_OUTPUT_DIR}" \
  "LOG_DIR=${GRAPH_OUTPUT_DIR}/logs" \
  "TRAIN_STRATEGY=full" \
  "INITIAL_LOSS_COEF=${GRAPH_INITIAL_LOSS_COEF}" \
  "${SCRIPT_DIR}/train_graph_tatr_hard200.sh"

if [[ "${RUN_EVAL}" == "1" ]]; then
  TATR_CKPT="${TATR_OUTPUT_DIR}/model_best.pth"
  GRAPH_CKPT="${GRAPH_OUTPUT_DIR}/model_best.pth"
  EVAL_ENV=(
    "DATA_ROOT=${DATA_ROOT}"
    "DEVICE=${DEVICE}"
    "BATCH_SIZE=${BATCH_SIZE}"
    "NUM_WORKERS=${NUM_WORKERS}"
  )
  if [[ -n "${TEST_MAX_SIZE}" ]]; then
    EVAL_ENV+=("TEST_MAX_SIZE=${TEST_MAX_SIZE}")
  fi

  echo "Evaluating baseline TATR without graph..."
  if [[ -f "${TATR_CKPT}" ]]; then
    env "${EVAL_ENV[@]}" "LOG_DIR=${TATR_OUTPUT_DIR}/logs" "${SCRIPT_DIR}/eval_tatr_hard200.sh" "${TATR_CKPT}"
  else
    echo "Skipping baseline eval; checkpoint not found: ${TATR_CKPT}" >&2
  fi

  echo "Evaluating GraphTATR with graph..."
  if [[ -f "${GRAPH_CKPT}" ]]; then
    env "${EVAL_ENV[@]}" "LOG_DIR=${GRAPH_OUTPUT_DIR}/logs" "${SCRIPT_DIR}/eval_graph_tatr_hard200.sh" "${GRAPH_CKPT}"
  else
    echo "Skipping GraphTATR eval; checkpoint not found: ${GRAPH_CKPT}" >&2
  fi
fi

cat <<EOF

Done.
Baseline output: ${TATR_OUTPUT_DIR}
GraphTATR output: ${GRAPH_OUTPUT_DIR}

Each output directory keeps only:
- model.pth: last checkpoint
- model_best.pth: best validation AP checkpoint

Compare the printed COCO metrics:
- AP
- AP50
- AP75
- AR
EOF
