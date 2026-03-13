#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${EDGE_ACTION:=run-once}"
: "${EDGE_LOOP:=0}"
: "${EDGE_INTERVAL_SEC:=5}"
: "${EDGE_DEVICE_ID:=rk3566-dev-01}"
: "${EDGE_CAMERA_ID:=cam-entry-01}"
: "${EDGE_BACKEND_BASE_URL:=http://100.92.134.46:8000}"
: "${EDGE_SNAPSHOT_DIR:=${ROOT_DIR}/data/edge_device/snapshots}"
: "${EDGE_CLIP_DIR:=${ROOT_DIR}/data/edge_device/clips}"
: "${EDGE_SNAPSHOT_BUFFER_SIZE:=32}"
: "${EDGE_CLIP_BUFFER_SIZE:=16}"
: "${PYTHON_BIN:=python3}"

mkdir -p "${EDGE_SNAPSHOT_DIR}" "${EDGE_CLIP_DIR}" "${ROOT_DIR}/logs"
cd "${ROOT_DIR}"

export EDGE_DEVICE_ID
export EDGE_CAMERA_ID
export EDGE_BACKEND_BASE_URL
export EDGE_SNAPSHOT_DIR
export EDGE_CLIP_DIR
export EDGE_SNAPSHOT_BUFFER_SIZE
export EDGE_CLIP_BUFFER_SIZE

echo "[INFO] Starting edge runtime"
echo "[INFO] Action             : ${EDGE_ACTION}"
echo "[INFO] Loop               : ${EDGE_LOOP}"
echo "[INFO] Device             : ${EDGE_DEVICE_ID}"
echo "[INFO] Camera             : ${EDGE_CAMERA_ID}"
echo "[INFO] Backend            : ${EDGE_BACKEND_BASE_URL}"
echo "[INFO] Snapshot dir       : ${EDGE_SNAPSHOT_DIR}"
echo "[INFO] Clip dir           : ${EDGE_CLIP_DIR}"
echo "[INFO] Snapshot buf size  : ${EDGE_SNAPSHOT_BUFFER_SIZE}"
echo "[INFO] Clip buf size      : ${EDGE_CLIP_BUFFER_SIZE}"

if [[ "${EDGE_LOOP}" == "1" ]]; then
  while true; do
    "${PYTHON_BIN}" -m edge_device.api.server "${EDGE_ACTION}"
    sleep "${EDGE_INTERVAL_SEC}"
  done
fi

exec "${PYTHON_BIN}" -m edge_device.api.server "${EDGE_ACTION}"
