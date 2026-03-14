#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${EDGE_ACTION:=run-once}"
: "${EDGE_LOOP:=0}"
: "${EDGE_INTERVAL_SEC:=5}"
: "${EDGE_DEVICE_ID:=rk3566-dev-01}"
: "${EDGE_CAMERA_ID:=cam-entry-01}"
: "${EDGE_BACKEND_BASE_URL:=http://127.0.0.1:8000}"
: "${EDGE_CAPTURE_SOURCE:=}"
: "${EDGE_CAPTURE_RESOLUTION:=1280x720}"
: "${EDGE_CAPTURE_FPS:=25}"
: "${EDGE_CAPTURE_PIXEL_FORMAT:=MJPG}"
: "${EDGE_CAPTURE_BACKEND:=auto}"
: "${EDGE_CAPTURE_RETRY_COUNT:=3}"
: "${EDGE_CAPTURE_RETRY_DELAY_SEC:=1.0}"
: "${EDGE_DETECTOR_BACKEND:=auto}"
: "${EDGE_DETECT_MIN_CONFIDENCE:=0.35}"
: "${EDGE_DETECT_MODEL_VERSION:=stub-detector-v1}"
: "${EDGE_RKNN_MODEL_PATH:=}"
: "${EDGE_RKNN_MODEL_VERSION:=}"
: "${EDGE_RKNN_INPUT_SIZE:=640x640}"
: "${EDGE_RKNN_LABELS:=person,package,car}"
: "${EDGE_SNAPSHOT_DIR:=${ROOT_DIR}/data/edge_device/snapshots}"
: "${EDGE_CLIP_DIR:=${ROOT_DIR}/data/edge_device/clips}"
: "${EDGE_SNAPSHOT_BUFFER_SIZE:=32}"
: "${EDGE_CLIP_BUFFER_SIZE:=16}"
: "${EDGE_PENDING_EVENT_DIR:=${ROOT_DIR}/data/edge_device/pending_events}"
: "${EDGE_PENDING_EVENT_MAX:=256}"
: "${EDGE_PENDING_FLUSH_BATCH:=32}"
: "${PYTHON_BIN:=python3}"

if [[ $# -gt 0 ]]; then
  EDGE_ACTION="$1"
  shift
fi

mkdir -p "${EDGE_SNAPSHOT_DIR}" "${EDGE_CLIP_DIR}" "${EDGE_PENDING_EVENT_DIR}" "${ROOT_DIR}/logs"
cd "${ROOT_DIR}"

export EDGE_DEVICE_ID
export EDGE_CAMERA_ID
export EDGE_BACKEND_BASE_URL
export EDGE_CAPTURE_SOURCE
export EDGE_CAPTURE_RESOLUTION
export EDGE_CAPTURE_FPS
export EDGE_CAPTURE_PIXEL_FORMAT
export EDGE_CAPTURE_BACKEND
export EDGE_CAPTURE_RETRY_COUNT
export EDGE_CAPTURE_RETRY_DELAY_SEC
export EDGE_DETECTOR_BACKEND
export EDGE_DETECT_MIN_CONFIDENCE
export EDGE_DETECT_MODEL_VERSION
export EDGE_RKNN_MODEL_PATH
export EDGE_RKNN_MODEL_VERSION
export EDGE_RKNN_INPUT_SIZE
export EDGE_RKNN_LABELS
export EDGE_SNAPSHOT_DIR
export EDGE_CLIP_DIR
export EDGE_SNAPSHOT_BUFFER_SIZE
export EDGE_CLIP_BUFFER_SIZE
export EDGE_PENDING_EVENT_DIR
export EDGE_PENDING_EVENT_MAX
export EDGE_PENDING_FLUSH_BATCH

echo "[INFO] Starting edge runtime"
echo "[INFO] Action             : ${EDGE_ACTION}"
echo "[INFO] Loop               : ${EDGE_LOOP}"
echo "[INFO] Device             : ${EDGE_DEVICE_ID}"
echo "[INFO] Camera             : ${EDGE_CAMERA_ID}"
echo "[INFO] Backend            : ${EDGE_BACKEND_BASE_URL}"
echo "[INFO] Capture source     : ${EDGE_CAPTURE_SOURCE:-stub://camera}"
echo "[INFO] Capture resolution : ${EDGE_CAPTURE_RESOLUTION}"
echo "[INFO] Capture fps        : ${EDGE_CAPTURE_FPS}"
echo "[INFO] Capture pixel fmt  : ${EDGE_CAPTURE_PIXEL_FORMAT}"
echo "[INFO] Capture backend    : ${EDGE_CAPTURE_BACKEND}"
echo "[INFO] Capture retries    : ${EDGE_CAPTURE_RETRY_COUNT} (delay=${EDGE_CAPTURE_RETRY_DELAY_SEC}s)"
echo "[INFO] Detector backend   : ${EDGE_DETECTOR_BACKEND}"
echo "[INFO] Detector min conf  : ${EDGE_DETECT_MIN_CONFIDENCE}"
echo "[INFO] RKNN model path    : ${EDGE_RKNN_MODEL_PATH:-<auto>}"
echo "[INFO] RKNN model version : ${EDGE_RKNN_MODEL_VERSION:-<auto>}"
echo "[INFO] RKNN input size    : ${EDGE_RKNN_INPUT_SIZE}"
echo "[INFO] RKNN labels        : ${EDGE_RKNN_LABELS}"
echo "[INFO] Snapshot dir       : ${EDGE_SNAPSHOT_DIR}"
echo "[INFO] Clip dir           : ${EDGE_CLIP_DIR}"
echo "[INFO] Snapshot buf size  : ${EDGE_SNAPSHOT_BUFFER_SIZE}"
echo "[INFO] Clip buf size      : ${EDGE_CLIP_BUFFER_SIZE}"
echo "[INFO] Pending event dir  : ${EDGE_PENDING_EVENT_DIR}"
echo "[INFO] Pending event max  : ${EDGE_PENDING_EVENT_MAX}"
echo "[INFO] Flush batch size   : ${EDGE_PENDING_FLUSH_BATCH}"

if [[ "${EDGE_LOOP}" == "1" ]]; then
  while true; do
    "${PYTHON_BIN}" -m edge_device.api.server "${EDGE_ACTION}"
    sleep "${EDGE_INTERVAL_SEC}"
  done
fi

exec "${PYTHON_BIN}" -m edge_device.api.server "${EDGE_ACTION}"
