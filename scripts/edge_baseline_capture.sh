#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

: "${EDGE_BASELINE_OUTPUT_DIR:=${REPO_ROOT}/data/edge_device/baseline}"
: "${EDGE_BASELINE_DEVICE:=}"
: "${EDGE_BASELINE_WIDTH:=1280}"
: "${EDGE_BASELINE_HEIGHT:=720}"
: "${EDGE_BASELINE_FPS:=25}"
: "${EDGE_BASELINE_PIXEL_FORMAT:=NV12}"
: "${EDGE_BASELINE_DURATION_SEC:=1800}"
: "${EDGE_BASELINE_SKIP_STREAM_TEST:=0}"
: "${EDGE_BASELINE_DRY_RUN:=0}"

usage() {
  cat <<'EOF'
Usage:
  scripts/edge_baseline_capture.sh [options]

Options:
  --output-dir <dir>        Output directory (default: data/edge_device/baseline)
  --device <path>           Camera device path, e.g. /dev/video0
  --width <int>             Capture width (default: 1280)
  --height <int>            Capture height (default: 720)
  --fps <int>               Capture fps (default: 25)
  --pixel-format <fourcc>   Pixel format for v4l2/ffmpeg (default: NV12)
  --duration-sec <int>      Test duration in seconds (default: 1800)
  --skip-stream-test        Only enumerate device baseline, no streaming test
  --dry-run                 Dry-run mode, no real capture
  -h, --help                Show help

Environment overrides:
  EDGE_BASELINE_OUTPUT_DIR
  EDGE_BASELINE_DEVICE
  EDGE_BASELINE_WIDTH
  EDGE_BASELINE_HEIGHT
  EDGE_BASELINE_FPS
  EDGE_BASELINE_PIXEL_FORMAT
  EDGE_BASELINE_DURATION_SEC
  EDGE_BASELINE_SKIP_STREAM_TEST
  EDGE_BASELINE_DRY_RUN
EOF
}

require_positive_int() {
  local label="$1"
  local value="$2"
  if ! [[ "${value}" =~ ^[0-9]+$ ]] || [[ "${value}" == "0" ]]; then
    echo "[ERROR] ${label} must be a positive integer, got: ${value}" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      EDGE_BASELINE_OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --device)
      EDGE_BASELINE_DEVICE="${2:-}"
      shift 2
      ;;
    --width)
      EDGE_BASELINE_WIDTH="${2:-}"
      shift 2
      ;;
    --height)
      EDGE_BASELINE_HEIGHT="${2:-}"
      shift 2
      ;;
    --fps)
      EDGE_BASELINE_FPS="${2:-}"
      shift 2
      ;;
    --pixel-format)
      EDGE_BASELINE_PIXEL_FORMAT="${2:-}"
      shift 2
      ;;
    --duration-sec)
      EDGE_BASELINE_DURATION_SEC="${2:-}"
      shift 2
      ;;
    --skip-stream-test)
      EDGE_BASELINE_SKIP_STREAM_TEST=1
      shift
      ;;
    --dry-run)
      EDGE_BASELINE_DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

require_positive_int "width" "${EDGE_BASELINE_WIDTH}"
require_positive_int "height" "${EDGE_BASELINE_HEIGHT}"
require_positive_int "fps" "${EDGE_BASELINE_FPS}"
require_positive_int "duration-sec" "${EDGE_BASELINE_DURATION_SEC}"

mkdir -p "${EDGE_BASELINE_OUTPUT_DIR}"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${EDGE_BASELINE_OUTPUT_DIR}/capture_${RUN_ID}"
mkdir -p "${RUN_DIR}"

ENUMERATION_LOG="${RUN_DIR}/camera_enumeration.log"
CAPTURE_LOG="${RUN_DIR}/stream_test.log"
SUMMARY_FILE="${RUN_DIR}/capture_summary.txt"

if [[ -z "${EDGE_BASELINE_DEVICE}" ]]; then
  if compgen -G "/dev/video*" > /dev/null; then
    EDGE_BASELINE_DEVICE="$(ls /dev/video* | sort | head -n1)"
  else
    EDGE_BASELINE_DEVICE="/dev/video0"
  fi
fi

log() {
  echo "$*" | tee -a "${SUMMARY_FILE}"
}

enumerate_cameras() {
  {
    echo "=== camera enumeration ($(date -Iseconds)) ==="
    if command -v v4l2-ctl >/dev/null 2>&1; then
      v4l2-ctl --list-devices || true
      for dev in /dev/video*; do
        [[ -e "${dev}" ]] || continue
        echo ""
        echo "--- ${dev} formats ---"
        v4l2-ctl --device "${dev}" --list-formats-ext || true
      done
    else
      echo "[WARN] v4l2-ctl not found; fallback to /dev/video* listing."
      ls -l /dev/video* 2>/dev/null || echo "[WARN] no /dev/video* found."
    fi
  } | tee "${ENUMERATION_LOG}"
}

run_capture_via_ffmpeg() {
  ffmpeg -hide_banner -loglevel info \
    -f v4l2 \
    -framerate "${EDGE_BASELINE_FPS}" \
    -video_size "${EDGE_BASELINE_WIDTH}x${EDGE_BASELINE_HEIGHT}" \
    -input_format "${EDGE_BASELINE_PIXEL_FORMAT}" \
    -i "${EDGE_BASELINE_DEVICE}" \
    -t "${EDGE_BASELINE_DURATION_SEC}" \
    -f null - 2>&1 | tee "${CAPTURE_LOG}"
}

run_capture_via_gst() {
  timeout "$((EDGE_BASELINE_DURATION_SEC + 10))" \
    gst-launch-1.0 -q -e \
      v4l2src device="${EDGE_BASELINE_DEVICE}" \
      num-buffers="$((EDGE_BASELINE_DURATION_SEC * EDGE_BASELINE_FPS))" \
      ! "video/x-raw,width=${EDGE_BASELINE_WIDTH},height=${EDGE_BASELINE_HEIGHT},framerate=${EDGE_BASELINE_FPS}/1,format=${EDGE_BASELINE_PIXEL_FORMAT}" \
      ! fakesink sync=false 2>&1 | tee "${CAPTURE_LOG}"
}

run_capture_via_v4l2ctl() {
  local frame_count
  frame_count="$((EDGE_BASELINE_DURATION_SEC * EDGE_BASELINE_FPS))"
  v4l2-ctl \
    --device "${EDGE_BASELINE_DEVICE}" \
    --set-fmt-video="width=${EDGE_BASELINE_WIDTH},height=${EDGE_BASELINE_HEIGHT},pixelformat=${EDGE_BASELINE_PIXEL_FORMAT}" \
    --stream-mmap=3 \
    --stream-count="${frame_count}" \
    --stream-to=/dev/null 2>&1 | tee "${CAPTURE_LOG}"
}

stream_test() {
  : > "${CAPTURE_LOG}"
  if [[ "${EDGE_BASELINE_DRY_RUN}" == "1" ]]; then
    echo "[DRY-RUN] stream test skipped." | tee -a "${CAPTURE_LOG}"
    return 0
  fi

  if [[ ! -e "${EDGE_BASELINE_DEVICE}" ]]; then
    echo "[ERROR] Camera device not found: ${EDGE_BASELINE_DEVICE}" | tee -a "${CAPTURE_LOG}" >&2
    return 1
  fi

  if command -v ffmpeg >/dev/null 2>&1; then
    echo "[INFO] stream backend: ffmpeg" | tee -a "${CAPTURE_LOG}"
    run_capture_via_ffmpeg
    return $?
  fi
  if command -v gst-launch-1.0 >/dev/null 2>&1; then
    echo "[INFO] stream backend: gstreamer" | tee -a "${CAPTURE_LOG}"
    run_capture_via_gst
    return $?
  fi
  if command -v v4l2-ctl >/dev/null 2>&1; then
    echo "[INFO] stream backend: v4l2-ctl" | tee -a "${CAPTURE_LOG}"
    run_capture_via_v4l2ctl
    return $?
  fi

  echo "[ERROR] no capture backend found (ffmpeg/gst-launch-1.0/v4l2-ctl)." | tee -a "${CAPTURE_LOG}" >&2
  return 2
}

{
  echo "run_id=${RUN_ID}"
  echo "started_at=$(date -Iseconds)"
  echo "output_dir=${RUN_DIR}"
  echo "device=${EDGE_BASELINE_DEVICE}"
  echo "resolution=${EDGE_BASELINE_WIDTH}x${EDGE_BASELINE_HEIGHT}"
  echo "fps=${EDGE_BASELINE_FPS}"
  echo "pixel_format=${EDGE_BASELINE_PIXEL_FORMAT}"
  echo "duration_sec=${EDGE_BASELINE_DURATION_SEC}"
  echo "dry_run=${EDGE_BASELINE_DRY_RUN}"
  echo "skip_stream_test=${EDGE_BASELINE_SKIP_STREAM_TEST}"
} > "${SUMMARY_FILE}"

log "[INFO] Enumerating cameras..."
enumerate_cameras

if [[ "${EDGE_BASELINE_SKIP_STREAM_TEST}" == "1" ]]; then
  log "[INFO] skip_stream_test=1, stream test skipped."
else
  log "[INFO] Running stream test..."
  if stream_test; then
    log "[INFO] stream test finished successfully."
  else
    log "[ERROR] stream test failed; see ${CAPTURE_LOG}"
    exit 1
  fi
fi

log "finished_at=$(date -Iseconds)"
log "enum_log=${ENUMERATION_LOG}"
log "capture_log=${CAPTURE_LOG}"
log "summary=${SUMMARY_FILE}"

echo "[OK] Baseline capture artifacts saved under: ${RUN_DIR}"
