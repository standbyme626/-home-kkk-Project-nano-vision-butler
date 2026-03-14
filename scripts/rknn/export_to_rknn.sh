#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${PYTHON_BIN:=python3}"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <onnx_model_path> <output_rknn_path> [target_platform]"
  echo "Example: $0 ./models/onnx/yolov8n.onnx ./models/rknn/yolov8n_official_i8_rk3566.rknn rk3566"
  exit 1
fi

ONNX_MODEL="$1"
OUTPUT_RKNN="$2"
TARGET_PLATFORM="${3:-rk3566}"

if [[ ! -f "${ONNX_MODEL}" ]]; then
  echo "[ERROR] ONNX model not found: ${ONNX_MODEL}"
  exit 2
fi

mkdir -p "$(dirname "${OUTPUT_RKNN}")"

echo "[INFO] Exporting ONNX -> RKNN"
echo "[INFO] ONNX   : ${ONNX_MODEL}"
echo "[INFO] RKNN   : ${OUTPUT_RKNN}"
echo "[INFO] Target : ${TARGET_PLATFORM}"

"${PYTHON_BIN}" - <<'PY' "${ONNX_MODEL}" "${OUTPUT_RKNN}" "${TARGET_PLATFORM}"
import sys
from pathlib import Path

onnx_path = Path(sys.argv[1])
rknn_path = Path(sys.argv[2])
target = sys.argv[3]

try:
    from rknn.api import RKNN
except Exception as exc:
    raise SystemExit(f"[ERROR] Failed to import rknn.api.RKNN: {exc}")

rknn = RKNN(verbose=True)
ret = rknn.config(target_platform=target)
if ret != 0:
    raise SystemExit(f"[ERROR] rknn.config failed: {ret}")

ret = rknn.load_onnx(model=str(onnx_path))
if ret != 0:
    raise SystemExit(f"[ERROR] rknn.load_onnx failed: {ret}")

ret = rknn.build(do_quantization=False)
if ret != 0:
    raise SystemExit(f"[ERROR] rknn.build failed: {ret}")

ret = rknn.export_rknn(str(rknn_path))
if ret != 0:
    raise SystemExit(f"[ERROR] rknn.export_rknn failed: {ret}")

rknn.release()
print(f"[OK] RKNN exported to {rknn_path}")
PY
