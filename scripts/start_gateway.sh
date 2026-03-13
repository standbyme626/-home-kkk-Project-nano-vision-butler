#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Instance selector: prod | dev
: "${NANOBOT_INSTANCE:=prod}"
: "${NANOBOT_BIN:=nanobot}"
: "${NANOBOT_DRY_RUN:=0}"

if [[ "${NANOBOT_INSTANCE}" != "prod" && "${NANOBOT_INSTANCE}" != "dev" ]]; then
  echo "[ERROR] NANOBOT_INSTANCE must be 'prod' or 'dev', got: ${NANOBOT_INSTANCE}" >&2
  exit 1
fi

if [[ "${NANOBOT_INSTANCE}" == "prod" ]]; then
  DEFAULT_CONFIG="${ROOT_DIR}/config/nanobot.config.json"
  DEFAULT_PORT="18790"
else
  DEFAULT_CONFIG="${ROOT_DIR}/config/nanobot.dev.config.json"
  DEFAULT_PORT="18791"
fi

: "${NANOBOT_CONFIG:=${DEFAULT_CONFIG}}"
: "${NANOBOT_PORT:=${DEFAULT_PORT}}"
: "${NANOBOT_WORKSPACE:=${ROOT_DIR}/gateway/nanobot_workspace/${NANOBOT_INSTANCE}}"
: "${NANOBOT_RUNTIME_DIR:=${ROOT_DIR}/gateway/runtime/${NANOBOT_INSTANCE}}"

mkdir -p "${NANOBOT_WORKSPACE}" "${NANOBOT_RUNTIME_DIR}" "${NANOBOT_RUNTIME_DIR}/logs" "${NANOBOT_RUNTIME_DIR}/tmp"

if [[ ! -f "${NANOBOT_CONFIG}" ]]; then
  echo "[ERROR] Config file not found: ${NANOBOT_CONFIG}" >&2
  echo "[HINT] Copy config/nanobot.config.json to config/nanobot.dev.config.json for dev instance." >&2
  exit 1
fi

echo "[INFO] Starting nanobot gateway"
echo "[INFO] Instance       : ${NANOBOT_INSTANCE}"
echo "[INFO] Config         : ${NANOBOT_CONFIG}"
echo "[INFO] Port           : ${NANOBOT_PORT}"
echo "[INFO] Workspace      : ${NANOBOT_WORKSPACE}"
echo "[INFO] Runtime dir    : ${NANOBOT_RUNTIME_DIR}"
echo "[INFO] Binary         : ${NANOBOT_BIN}"
echo "[INFO] Dry run        : ${NANOBOT_DRY_RUN}"

# nanobot CLI compatibility:
# - new style: nanobot gateway --config <file> --workspace <dir>
# - legacy style: nanobot --config <file> --workspace <dir>
if "${NANOBOT_BIN}" gateway --help 2>/dev/null | grep -q -- '--config'; then
  CMD=(
    "${NANOBOT_BIN}"
    "gateway"
    "--port" "${NANOBOT_PORT}"
    "--config" "${NANOBOT_CONFIG}"
    "--workspace" "${NANOBOT_WORKSPACE}"
  )
else
  CMD=(
    "${NANOBOT_BIN}"
    "--config" "${NANOBOT_CONFIG}"
    "--workspace" "${NANOBOT_WORKSPACE}"
  )
fi

if [[ "${NANOBOT_DRY_RUN}" == "1" ]]; then
  printf "[DRY-RUN] %q " "${CMD[@]}"
  printf "\n"
  exit 0
fi

exec "${CMD[@]}"
