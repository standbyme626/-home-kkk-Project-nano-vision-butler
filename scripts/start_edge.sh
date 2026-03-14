#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${EDGE_ACTION:=run-once}"
: "${EDGE_LOOP:=0}"
: "${EDGE_INTERVAL_SEC:=5}"
: "${EDGE_DEVICE_ID:=rk3566-dev-01}"
: "${EDGE_CAMERA_ID:=cam-entry-01}"
: "${EDGE_BACKEND_BASE_URL:=http://100.92.134.46:8000}"
: "${EDGE_CAPTURE_SOURCE:=}"
: "${EDGE_CAPTURE_RESOLUTION:=1280x720}"
: "${EDGE_CAPTURE_FPS:=30}"
: "${EDGE_CAPTURE_PIXEL_FORMAT:=MJPG}"
: "${EDGE_CAPTURE_BACKEND:=auto}"
: "${EDGE_CAPTURE_APPLY_V4L2_TUNING:=1}"
: "${EDGE_CAPTURE_DISABLE_DYNAMIC_FRAMERATE:=0}"
: "${EDGE_CAPTURE_PARALLEL:=1}"
: "${EDGE_CAPTURE_PARALLEL_WAIT_SEC:=0.4}"
: "${EDGE_CAPTURE_RETRY_COUNT:=3}"
: "${EDGE_CAPTURE_RETRY_DELAY_SEC:=1.0}"
: "${EDGE_DETECTOR_BACKEND:=auto}"
: "${EDGE_DETECT_MIN_CONFIDENCE:=0.35}"
: "${EDGE_DETECT_MODEL_VERSION:=stub-detector-v1}"
: "${EDGE_RKNN_MODEL_PATH:=./models/rknn/yolov8n_official_i8_rk3566.rknn}"
: "${EDGE_RKNN_MODEL_VERSION:=}"
: "${EDGE_RKNN_INPUT_SIZE:=640x640}"
: "${EDGE_RKNN_LABELS:=person,package,car}"
: "${EDGE_ANALYSIS_ENABLE:=1}"
: "${EDGE_ANALYSIS_OCR_ENABLE:=1}"
: "${EDGE_ANALYSIS_MIN_IMPORTANCE_OCR:=4}"
: "${EDGE_ANALYSIS_PROFILE:=backend_heavy_v1}"
: "${EDGE_SNAPSHOT_DIR:=${ROOT_DIR}/data/edge_device/snapshots}"
: "${EDGE_CLIP_DIR:=${ROOT_DIR}/data/edge_device/clips}"
: "${EDGE_SNAPSHOT_BUFFER_SIZE:=32}"
: "${EDGE_CLIP_BUFFER_SIZE:=16}"
: "${EDGE_PENDING_EVENT_DIR:=${ROOT_DIR}/data/edge_device/pending_events}"
: "${EDGE_PENDING_EVENT_MAX:=256}"
: "${EDGE_PENDING_FLUSH_BATCH:=32}"
: "${PYTHON_BIN:=python3}"
: "${VISION_BUTLER_TIME_MODE:=local}"
: "${TZ:=Asia/Shanghai}"

if [[ $# -gt 0 ]]; then
  EDGE_ACTION="$1"
  shift
fi

mkdir -p "${EDGE_SNAPSHOT_DIR}" "${EDGE_CLIP_DIR}" "${EDGE_PENDING_EVENT_DIR}" "${ROOT_DIR}/logs"
cd "${ROOT_DIR}"

parse_capture_resolution() {
  local raw normalized
  raw="${EDGE_CAPTURE_RESOLUTION:-1280x720}"
  normalized="${raw,,}"
  if [[ "${normalized}" =~ ^([0-9]+)x([0-9]+)$ ]]; then
    echo "${BASH_REMATCH[1]} ${BASH_REMATCH[2]}"
    return 0
  fi
  echo "1280 720"
}

apply_v4l2_tuning() {
  local dims width height
  if [[ "${EDGE_CAPTURE_APPLY_V4L2_TUNING}" != "1" ]]; then
    return 0
  fi
  if [[ -z "${EDGE_CAPTURE_SOURCE}" || ! "${EDGE_CAPTURE_SOURCE}" =~ ^/dev/video[0-9]+$ ]]; then
    return 0
  fi
  if ! command -v v4l2-ctl >/dev/null 2>&1; then
    echo "[WARN] v4l2-ctl not found, skip camera tuning"
    return 0
  fi

  dims="$(parse_capture_resolution)"
  width="${dims%% *}"
  height="${dims##* }"

  if ! v4l2-ctl -d "${EDGE_CAPTURE_SOURCE}" \
    --set-fmt-video="width=${width},height=${height},pixelformat=${EDGE_CAPTURE_PIXEL_FORMAT}" >/dev/null 2>&1; then
    echo "[WARN] set-fmt-video failed for ${EDGE_CAPTURE_SOURCE}"
  fi
  if ! v4l2-ctl -d "${EDGE_CAPTURE_SOURCE}" --set-parm="${EDGE_CAPTURE_FPS}" >/dev/null 2>&1; then
    echo "[WARN] set-parm failed for ${EDGE_CAPTURE_SOURCE}"
  fi
  if [[ "${EDGE_CAPTURE_DISABLE_DYNAMIC_FRAMERATE}" == "1" ]]; then
    v4l2-ctl -d "${EDGE_CAPTURE_SOURCE}" --set-ctrl=exposure_dynamic_framerate=0 >/dev/null 2>&1 || true
  fi

  echo "[INFO] Applied v4l2 tuning: source=${EDGE_CAPTURE_SOURCE} resolution=${width}x${height} fps=${EDGE_CAPTURE_FPS} format=${EDGE_CAPTURE_PIXEL_FORMAT}"
  v4l2-ctl -d "${EDGE_CAPTURE_SOURCE}" --get-fmt-video 2>/dev/null | sed 's/^/[INFO] /'
  v4l2-ctl -d "${EDGE_CAPTURE_SOURCE}" --get-parm 2>/dev/null | sed 's/^/[INFO] /'
}

export EDGE_DEVICE_ID
export EDGE_CAMERA_ID
export EDGE_BACKEND_BASE_URL
export EDGE_CAPTURE_SOURCE
export EDGE_CAPTURE_RESOLUTION
export EDGE_CAPTURE_FPS
export EDGE_CAPTURE_PIXEL_FORMAT
export EDGE_CAPTURE_BACKEND
export EDGE_CAPTURE_APPLY_V4L2_TUNING
export EDGE_CAPTURE_DISABLE_DYNAMIC_FRAMERATE
export EDGE_CAPTURE_PARALLEL
export EDGE_CAPTURE_PARALLEL_WAIT_SEC
export EDGE_CAPTURE_RETRY_COUNT
export EDGE_CAPTURE_RETRY_DELAY_SEC
export EDGE_DETECTOR_BACKEND
export EDGE_DETECT_MIN_CONFIDENCE
export EDGE_DETECT_MODEL_VERSION
export EDGE_RKNN_MODEL_PATH
export EDGE_RKNN_MODEL_VERSION
export EDGE_RKNN_INPUT_SIZE
export EDGE_RKNN_LABELS
export EDGE_ANALYSIS_ENABLE
export EDGE_ANALYSIS_OCR_ENABLE
export EDGE_ANALYSIS_MIN_IMPORTANCE_OCR
export EDGE_ANALYSIS_PROFILE
export EDGE_SNAPSHOT_DIR
export EDGE_CLIP_DIR
export EDGE_SNAPSHOT_BUFFER_SIZE
export EDGE_CLIP_BUFFER_SIZE
export EDGE_PENDING_EVENT_DIR
export EDGE_PENDING_EVENT_MAX
export EDGE_PENDING_FLUSH_BATCH
export VISION_BUTLER_TIME_MODE
export TZ

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
echo "[INFO] Capture tuning     : ${EDGE_CAPTURE_APPLY_V4L2_TUNING} (disable_dynamic_framerate=${EDGE_CAPTURE_DISABLE_DYNAMIC_FRAMERATE})"
echo "[INFO] Capture parallel   : ${EDGE_CAPTURE_PARALLEL} (wait=${EDGE_CAPTURE_PARALLEL_WAIT_SEC}s)"
echo "[INFO] Capture retries    : ${EDGE_CAPTURE_RETRY_COUNT} (delay=${EDGE_CAPTURE_RETRY_DELAY_SEC}s)"
echo "[INFO] Detector backend   : ${EDGE_DETECTOR_BACKEND}"
echo "[INFO] Detector min conf  : ${EDGE_DETECT_MIN_CONFIDENCE}"
echo "[INFO] RKNN model path    : ${EDGE_RKNN_MODEL_PATH:-<auto>}"
echo "[INFO] RKNN model version : ${EDGE_RKNN_MODEL_VERSION:-<auto>}"
echo "[INFO] RKNN input size    : ${EDGE_RKNN_INPUT_SIZE}"
echo "[INFO] RKNN labels        : ${EDGE_RKNN_LABELS}"
echo "[INFO] Analysis enable    : ${EDGE_ANALYSIS_ENABLE}"
echo "[INFO] Analysis OCR       : ${EDGE_ANALYSIS_OCR_ENABLE}"
echo "[INFO] Analysis min imp   : ${EDGE_ANALYSIS_MIN_IMPORTANCE_OCR}"
echo "[INFO] Analysis profile   : ${EDGE_ANALYSIS_PROFILE}"
echo "[INFO] Snapshot dir       : ${EDGE_SNAPSHOT_DIR}"
echo "[INFO] Clip dir           : ${EDGE_CLIP_DIR}"
echo "[INFO] Snapshot buf size  : ${EDGE_SNAPSHOT_BUFFER_SIZE}"
echo "[INFO] Clip buf size      : ${EDGE_CLIP_BUFFER_SIZE}"
echo "[INFO] Pending event dir  : ${EDGE_PENDING_EVENT_DIR}"
echo "[INFO] Pending event max  : ${EDGE_PENDING_EVENT_MAX}"
echo "[INFO] Flush batch size   : ${EDGE_PENDING_FLUSH_BATCH}"
echo "[INFO] Time mode          : ${VISION_BUTLER_TIME_MODE} (TZ=${TZ})"

apply_v4l2_tuning

if [[ "${EDGE_LOOP}" == "1" ]]; then
  while true; do
    "${PYTHON_BIN}" -m edge_device.api.server "${EDGE_ACTION}"
    sleep "${EDGE_INTERVAL_SEC}"
  done
fi

exec "${PYTHON_BIN}" -m edge_device.api.server "${EDGE_ACTION}"
