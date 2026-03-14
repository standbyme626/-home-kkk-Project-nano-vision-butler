#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${PYTHON_BIN:=python3}"
: "${BENCH_LOOPS:=20}"
: "${EDGE_DEVICE_ID:=rk3566-dev-01}"
: "${EDGE_CAMERA_ID:=cam-entry-01}"
: "${EDGE_DETECTOR_BACKEND:=rknn}"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <model_rknn_path> [loops]"
  echo "Example: $0 ./models/rknn/main_detector_n_int8.rknn 50"
  exit 1
fi

MODEL_PATH="$1"
if [[ ! -f "${MODEL_PATH}" ]]; then
  echo "[ERROR] RKNN model not found: ${MODEL_PATH}"
  exit 2
fi

if [[ $# -ge 2 ]]; then
  BENCH_LOOPS="$2"
fi

export EDGE_RKNN_MODEL_PATH="${MODEL_PATH}"
export EDGE_DETECTOR_BACKEND
export EDGE_DEVICE_ID
export EDGE_CAMERA_ID

echo "[INFO] Running edge inference benchmark"
echo "[INFO] Model       : ${EDGE_RKNN_MODEL_PATH}"
echo "[INFO] Loops       : ${BENCH_LOOPS}"
echo "[INFO] Detector    : ${EDGE_DETECTOR_BACKEND}"
echo "[INFO] Device/Camera: ${EDGE_DEVICE_ID}/${EDGE_CAMERA_ID}"

total_ms=0
for ((i=1; i<=BENCH_LOOPS; i++)); do
  start_ns=$(date +%s%N)
  output="$("${PYTHON_BIN}" -m edge_device.api.server run-once)"
  end_ns=$(date +%s%N)
  elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))
  total_ms=$(( total_ms + elapsed_ms ))
  model_version="$(echo "${output}" | "${PYTHON_BIN}" -c 'import json,sys; print(json.load(sys.stdin)["data"].get("model_version"))')"
  detector_error="$(echo "${output}" | "${PYTHON_BIN}" -c 'import json,sys; print(json.load(sys.stdin)["data"].get("detector_error"))')"
  echo "[RUN ${i}] ${elapsed_ms} ms | model=${model_version} | detector_error=${detector_error}"
done

avg_ms=$(( total_ms / BENCH_LOOPS ))
fps="$(awk "BEGIN { if (${avg_ms} <= 0) print 0; else print 1000 / ${avg_ms} }")"

echo "[RESULT] avg_latency_ms=${avg_ms}"
echo "[RESULT] approx_fps=${fps}"
