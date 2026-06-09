#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TATR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SRC_DIR="${TATR_ROOT}/src"
REPO_ROOT="$(cd "${TATR_ROOT}/../../../.." && pwd)"

DATA_ROOT="${DATA_ROOT:-${REPO_ROOT}/research/table_recognition/datasets/subsets/pubtables_hard_200_official}"
CONFIG_FILE="${CONFIG_FILE:-${SRC_DIR}/graph_tatr_config.json}"
MODEL_LOAD_PATH="${1:-${MODEL_LOAD_PATH:-${DATA_ROOT}/output/graph_tatr_graph_only/model_best.pth}}"

DEVICE="${DEVICE:-cuda}"
BATCH_SIZE="${BATCH_SIZE:-2}"
NUM_WORKERS="${NUM_WORKERS:-1}"
TEST_MAX_SIZE="${TEST_MAX_SIZE:-}"
TABLE_WORDS_DIR="${TABLE_WORDS_DIR:-}"
METRICS_SAVE_FILEPATH="${METRICS_SAVE_FILEPATH:-}"
DEBUG_SAVE_DIR="${DEBUG_SAVE_DIR:-${DATA_ROOT}/output/graph_tatr_eval_debug}"
DEBUG="${DEBUG:-0}"

CHECKPOINT_DIR="$(dirname "${MODEL_LOAD_PATH}")"
LOG_DIR="${LOG_DIR:-${CHECKPOINT_DIR}/logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/eval_graph_tatr_$(date +%Y%m%d_%H%M%S).log}"
mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

if [[ ! -f "${MODEL_LOAD_PATH}" ]]; then
  echo "Checkpoint not found: ${MODEL_LOAD_PATH}" >&2
  echo "Pass a checkpoint path as the first argument or set MODEL_LOAD_PATH." >&2
  exit 2
fi

cmd=(
  python train_graph_tatr.py
  --mode eval
  --data_type structure
  --config_file "${CONFIG_FILE}"
  --data_root_dir "${DATA_ROOT}"
  --model_load_path "${MODEL_LOAD_PATH}"
  --device "${DEVICE}"
  --batch_size "${BATCH_SIZE}"
  --num_workers "${NUM_WORKERS}"
)

if [[ -n "${TEST_MAX_SIZE}" ]]; then
  cmd+=(--test_max_size "${TEST_MAX_SIZE}")
fi

if [[ -n "${TABLE_WORDS_DIR}" ]]; then
  cmd+=(--table_words_dir "${TABLE_WORDS_DIR}")
fi

if [[ -n "${METRICS_SAVE_FILEPATH}" ]]; then
  cmd+=(--metrics_save_filepath "${METRICS_SAVE_FILEPATH}")
fi

if [[ "${DEBUG}" == "1" ]]; then
  cmd+=(--debug --debug_save_dir "${DEBUG_SAVE_DIR}")
fi

echo "Data root: ${DATA_ROOT}"
echo "Checkpoint: ${MODEL_LOAD_PATH}"
echo "Log file: ${LOG_FILE}"
echo "Command:"
printf ' %q' "${cmd[@]}"
echo

cd "${SRC_DIR}"
"${cmd[@]}"
