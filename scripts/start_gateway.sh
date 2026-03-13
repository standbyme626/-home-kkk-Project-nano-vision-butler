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
  if [[ -f "${ROOT_DIR}/config/runtime/nanobot.config.json" ]]; then
    DEFAULT_CONFIG="${ROOT_DIR}/config/runtime/nanobot.config.json"
  else
    DEFAULT_CONFIG="${ROOT_DIR}/config/nanobot.config.json"
  fi
  DEFAULT_PORT="18790"
else
  if [[ -f "${ROOT_DIR}/config/runtime/nanobot.dev.config.json" ]]; then
    DEFAULT_CONFIG="${ROOT_DIR}/config/runtime/nanobot.dev.config.json"
  else
    DEFAULT_CONFIG="${ROOT_DIR}/config/nanobot.dev.config.json"
  fi
  DEFAULT_PORT="18791"
fi

: "${NANOBOT_CONFIG:=${DEFAULT_CONFIG}}"
: "${NANOBOT_PORT:=${DEFAULT_PORT}}"
: "${NANOBOT_WORKSPACE:=${ROOT_DIR}/gateway/nanobot_workspace/${NANOBOT_INSTANCE}}"
: "${NANOBOT_RUNTIME_DIR:=${ROOT_DIR}/gateway/runtime/${NANOBOT_INSTANCE}}"
: "${NANOBOT_AUTO_DISABLE_MCP:=1}"

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

NANOBOT_EFFECTIVE_CONFIG="$(
  python3 - "${NANOBOT_CONFIG}" "${NANOBOT_RUNTIME_DIR}" "${NANOBOT_AUTO_DISABLE_MCP}" <<'PY'
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

config_path = Path(sys.argv[1])
runtime_dir = Path(sys.argv[2])
auto_disable = sys.argv[3] == "1"

payload = json.loads(config_path.read_text(encoding="utf-8"))
effective_path = config_path

if auto_disable:
    tools = payload.get("tools") or {}
    mcp_servers = tools.get("mcpServers") or {}
    if isinstance(mcp_servers, dict) and mcp_servers:
        unreachable = []
        for server_name, spec in mcp_servers.items():
            url = spec.get("url") if isinstance(spec, dict) else None
            if not isinstance(url, str) or not url:
                unreachable.append(f"{server_name}(missing-url)")
                continue
            parsed = urlparse(url)
            host = parsed.hostname
            if not host:
                unreachable.append(f"{server_name}(bad-url:{url})")
                continue
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            try:
                with socket.create_connection((host, port), timeout=1.5):
                    pass
            except OSError as exc:
                unreachable.append(f"{server_name}@{host}:{port}({exc.__class__.__name__})")

        if unreachable:
            payload.setdefault("tools", {})["mcpServers"] = {}
            runtime_dir.mkdir(parents=True, exist_ok=True)
            effective_path = runtime_dir / "nanobot.effective.config.json"
            effective_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                "[WARN] MCP unreachable, auto-disabled mcpServers: "
                + ", ".join(unreachable),
                file=sys.stderr,
            )

print(str(effective_path))
PY
)"

echo "[INFO] Effective cfg  : ${NANOBOT_EFFECTIVE_CONFIG}"

# nanobot CLI compatibility:
# - new style: nanobot gateway --config <file> --workspace <dir>
# - legacy style: nanobot --config <file> --workspace <dir>
if "${NANOBOT_BIN}" gateway --help 2>/dev/null | grep -q -- '--config'; then
  CMD=(
    "${NANOBOT_BIN}"
    "gateway"
    "--port" "${NANOBOT_PORT}"
    "--config" "${NANOBOT_EFFECTIVE_CONFIG}"
    "--workspace" "${NANOBOT_WORKSPACE}"
  )
else
  CMD=(
    "${NANOBOT_BIN}"
    "--config" "${NANOBOT_EFFECTIVE_CONFIG}"
    "--workspace" "${NANOBOT_WORKSPACE}"
  )
fi

if [[ "${NANOBOT_DRY_RUN}" == "1" ]]; then
  printf "[DRY-RUN] %q " "${CMD[@]}"
  printf "\n"
  exit 0
fi

exec "${CMD[@]}"
