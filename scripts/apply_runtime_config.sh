#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

: "${RUNTIME_CONFIG_DIR:=${REPO_ROOT}/config/runtime}"
: "${STRICT_CONFIG:=0}"

mkdir -p "${RUNTIME_CONFIG_DIR}"

python3 - "${REPO_ROOT}" "${RUNTIME_CONFIG_DIR}" "${STRICT_CONFIG}" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path


def required(name: str, strict: bool, default: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    if strict:
        raise SystemExit(f"[ERROR] Missing required env var: {name}")
    return default


repo_root = Path(sys.argv[1])
runtime_dir = Path(sys.argv[2])
strict = sys.argv[3] == "1"

replacements = {
    "__SET_TELEGRAM_USER_ID__": required("TELEGRAM_USER_ID", strict, "42"),
    "__SET_TELEGRAM_USER_ID_DEV__": required("TELEGRAM_USER_ID_DEV", strict, required("TELEGRAM_USER_ID", strict, "42")),
    "__SET_TELEGRAM_BOT_TOKEN__": required("TELEGRAM_BOT_TOKEN", strict, "DUMMY_TELEGRAM_BOT_TOKEN"),
    "__SET_TELEGRAM_BOT_TOKEN_DEV__": required("TELEGRAM_BOT_TOKEN_DEV", strict, "DUMMY_TELEGRAM_BOT_TOKEN_DEV"),
    "__SET_TELEGRAM_WEBHOOK_URL__": required("TELEGRAM_WEBHOOK_URL", strict, "http://127.0.0.1:18790/telegram/webhook"),
    "__SET_QWEN_MODEL_NAME__": required("QWEN_MODEL_NAME", strict, "qwen3.5-35b-a3b"),
    "__SET_QWEN_MODEL_NAME_DEV__": required("QWEN_MODEL_NAME_DEV", strict, required("QWEN_MODEL_NAME", strict, "qwen3.5-35b-a3b")),
    "__SET_QWEN_API_BASE__": required("QWEN_API_BASE", strict, "http://127.0.0.1:8000/v1"),
    "__SET_QWEN_API_BASE_DEV__": required("QWEN_API_BASE_DEV", strict, required("QWEN_API_BASE", strict, "http://127.0.0.1:8000/v1")),
    "__SET_QWEN_API_KEY__": required("QWEN_API_KEY", strict, "DUMMY_OR_REAL_API_KEY"),
    "__SET_QWEN_API_KEY_DEV__": required("QWEN_API_KEY_DEV", strict, required("QWEN_API_KEY", strict, "DUMMY_OR_REAL_API_KEY")),
    "__SET_DEVICE_API_KEY__": required("DEVICE_API_KEY", strict, "__SET_DEVICE_API_KEY__"),
    "__SET_CAMERA_URL__": required("CAMERA_RTSP_URL", strict, "rtsp://127.0.0.1/live"),
}

for src in (repo_root / "config").iterdir():
    if not src.is_file():
        continue
    if src.name == ".gitkeep":
        continue
    content = src.read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(key, value)
    (runtime_dir / src.name).write_text(content, encoding="utf-8")

print(f"[OK] Runtime config rendered: {runtime_dir}")
PY

echo "[INFO] Runtime config ready at: ${RUNTIME_CONFIG_DIR}"
echo "[INFO] Suggested backend start:"
echo "       BACKEND_CONFIG_DIR=${RUNTIME_CONFIG_DIR} ./scripts/start_backend.sh"
echo "[INFO] Suggested gateway dry-run:"
echo "       NANOBOT_DRY_RUN=1 NANOBOT_INSTANCE=dev NANOBOT_CONFIG=${RUNTIME_CONFIG_DIR}/nanobot.dev.config.json ./scripts/start_gateway.sh"
