#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TATR_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SRC_DIR="${TATR_ROOT}/src"
REPO_ROOT="$(cd "${TATR_ROOT}/../../../.." && pwd)"

DATA_ROOT="${DATA_ROOT:-${REPO_ROOT}/research/table_recognition/datasets/subsets/pubtables_hard_200_official}"
CONFIG_FILE="${CONFIG_FILE:-${SRC_DIR}/structure_config.json}"
OUTPUT_DIR="${OUTPUT_DIR:-${DATA_ROOT}/output/tatr_no_graph_from_scratch}"

DEVICE="${DEVICE:-cuda}"
EPOCHS="${EPOCHS:-20}"
BATCH_SIZE="${BATCH_SIZE:-2}"
NUM_WORKERS="${NUM_WORKERS:-1}"
LR="${LR:-}"
LR_BACKBONE="${LR_BACKBONE:-}"
LR_DROP="${LR_DROP:-}"
LR_GAMMA="${LR_GAMMA:-}"

TRAIN_MAX_SIZE="${TRAIN_MAX_SIZE:-}"
VAL_MAX_SIZE="${VAL_MAX_SIZE:-}"
MODEL_LOAD_PATH="${MODEL_LOAD_PATH:-}"
LOAD_WEIGHTS_ONLY="${LOAD_WEIGHTS_ONLY:-1}"

LOG_DIR="${LOG_DIR:-${OUTPUT_DIR}/logs}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/train_tatr_$(date +%Y%m%d_%H%M%S).log}"
mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

cmd=(
  python main.py
  --data_type structure
  --config_file "${CONFIG_FILE}"
  --data_root_dir "${DATA_ROOT}"
  --device "${DEVICE}"
  --epochs "${EPOCHS}"
  --batch_size "${BATCH_SIZE}"
  --num_workers "${NUM_WORKERS}"
  --model_save_dir "${OUTPUT_DIR}"
)

if [[ -n "${TRAIN_MAX_SIZE}" ]]; then
  cmd+=(--train_max_size "${TRAIN_MAX_SIZE}")
fi

if [[ -n "${VAL_MAX_SIZE}" ]]; then
  cmd+=(--val_max_size "${VAL_MAX_SIZE}")
fi

if [[ -n "${LR}" ]]; then
  cmd+=(--lr "${LR}")
fi

if [[ -n "${LR_BACKBONE}" ]]; then
  cmd+=(--lr_backbone "${LR_BACKBONE}")
fi

if [[ -n "${LR_DROP}" ]]; then
  cmd+=(--lr_drop "${LR_DROP}")
fi

if [[ -n "${LR_GAMMA}" ]]; then
  cmd+=(--lr_gamma "${LR_GAMMA}")
fi

if [[ -n "${MODEL_LOAD_PATH}" ]]; then
  cmd+=(--model_load_path "${MODEL_LOAD_PATH}")
  if [[ "${LOAD_WEIGHTS_ONLY}" == "1" ]]; then
    cmd+=(--load_weights_only)
  fi
fi

echo "Mode: baseline TATR without graph"
echo "Data root: ${DATA_ROOT}"
echo "Output dir: ${OUTPUT_DIR}"
echo "Log file: ${LOG_FILE}"
echo "Command:"
printf ' %q' "${cmd[@]}"
echo

cd "${SRC_DIR}"
"${cmd[@]}"
