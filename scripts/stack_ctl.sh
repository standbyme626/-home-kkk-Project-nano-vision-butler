#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${ROOT_DIR}/gateway/runtime/stack"
PID_DIR="${RUN_DIR}/pids"
LOG_DIR="${RUN_DIR}/logs"

INSTANCE="${NANOBOT_INSTANCE:-prod}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
MCP_PORT="${MCP_PORT:-8001}"
if [[ "${INSTANCE}" == "dev" ]]; then
  GATEWAY_PORT_DEFAULT="18791"
else
  GATEWAY_PORT_DEFAULT="18790"
fi
GATEWAY_PORT="${NANOBOT_PORT:-${GATEWAY_PORT_DEFAULT}}"
NANOBOT_AUTO_DISABLE_MCP="${NANOBOT_AUTO_DISABLE_MCP:-0}"
EDGE_ENABLED="${EDGE_ENABLED:-1}"
EDGE_ACTION="${EDGE_ACTION:-heartbeat}"
EDGE_LOOP="${EDGE_LOOP:-1}"
EDGE_INTERVAL_SEC="${EDGE_INTERVAL_SEC:-15}"
EDGE_BACKEND_BASE_URL="${EDGE_BACKEND_BASE_URL:-http://127.0.0.1:${BACKEND_PORT}}"

mkdir -p "${PID_DIR}" "${LOG_DIR}"

pid_file() {
  local name="$1"
  echo "${PID_DIR}/${name}.pid"
}

log_file() {
  local name="$1"
  echo "${LOG_DIR}/${name}.log"
}

is_pid_running() {
  local pid="$1"
  if [[ -z "${pid}" ]]; then
    return 1
  fi
  kill -0 "${pid}" >/dev/null 2>&1
}

read_pid() {
  local name="$1"
  local file
  file="$(pid_file "${name}")"
  if [[ -f "${file}" ]]; then
    cat "${file}"
  fi
}

is_port_open() {
  local port="$1"
  python3 - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
s = socket.socket()
s.settimeout(0.2)
try:
    s.connect(("127.0.0.1", port))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
}

wait_for_port() {
  local port="$1"
  local retries="${2:-40}"
  local sleep_sec="${3:-0.25}"
  local i

  for i in $(seq 1 "${retries}"); do
    if is_port_open "${port}"; then
      return 0
    fi
    sleep "${sleep_sec}"
  done
  return 1
}

start_backend() {
  local name="backend"
  local pid
  pid="$(read_pid "${name}")"
  if is_pid_running "${pid}"; then
    echo "[INFO] backend already running (pid=${pid})"
    return 0
  fi
  if is_port_open "${BACKEND_PORT}"; then
    echo "[WARN] backend port ${BACKEND_PORT} already in use (external process), skip start"
    return 0
  fi

  echo "[INFO] starting backend in background..."
  (
    cd "${ROOT_DIR}"
    nohup ./scripts/start_backend.sh >"$(log_file "${name}")" 2>&1 &
    echo $! >"$(pid_file "${name}")"
  )

  if wait_for_port "${BACKEND_PORT}" 50 0.2; then
    echo "[INFO] backend started on :${BACKEND_PORT} (pid=$(read_pid "${name}"))"
    return 0
  fi
  echo "[ERROR] backend failed to open port ${BACKEND_PORT}"
  tail -n 40 "$(log_file "${name}")" || true
  return 1
}

start_mcp() {
  local name="mcp"
  local pid
  pid="$(read_pid "${name}")"
  if is_pid_running "${pid}"; then
    echo "[INFO] mcp already running (pid=${pid})"
    return 0
  fi
  if is_port_open "${MCP_PORT}"; then
    echo "[WARN] mcp port ${MCP_PORT} already in use (external process), skip start"
    return 0
  fi

  echo "[INFO] starting mcp in background..."
  (
    cd "${ROOT_DIR}"
    nohup ./scripts/start_mcp.sh >"$(log_file "${name}")" 2>&1 &
    echo $! >"$(pid_file "${name}")"
  )

  if wait_for_port "${MCP_PORT}" 50 0.2; then
    echo "[INFO] mcp started on :${MCP_PORT} (pid=$(read_pid "${name}"))"
    return 0
  fi
  echo "[ERROR] mcp failed to open port ${MCP_PORT}"
  tail -n 40 "$(log_file "${name}")" || true
  return 1
}

start_gateway() {
  local name="gateway"
  local pid
  pid="$(read_pid "${name}")"
  if is_pid_running "${pid}"; then
    echo "[INFO] gateway already running (pid=${pid})"
    return 0
  fi
  if pgrep -f "nanobot.*gateway" >/dev/null 2>&1; then
    echo "[WARN] gateway process already running (external), skip start"
    return 0
  fi
  if is_port_open "${GATEWAY_PORT}"; then
    echo "[WARN] gateway port ${GATEWAY_PORT} already in use (external process), skip start"
    return 0
  fi

  echo "[INFO] starting gateway in background..."
  (
    cd "${ROOT_DIR}"
    nohup env NANOBOT_INSTANCE="${INSTANCE}" NANOBOT_AUTO_DISABLE_MCP="${NANOBOT_AUTO_DISABLE_MCP}" ./scripts/start_gateway.sh >"$(log_file "${name}")" 2>&1 &
    echo $! >"$(pid_file "${name}")"
  )

  pid="$(read_pid "${name}")"
  for _ in $(seq 1 80); do
    if ! is_pid_running "${pid}"; then
      break
    fi
    if grep -q "Telegram bot @.* connected" "$(log_file "${name}")" 2>/dev/null; then
      echo "[INFO] gateway started (pid=${pid})"
      return 0
    fi
    sleep 0.2
  done

  if is_pid_running "${pid}"; then
    echo "[INFO] gateway process is running (pid=${pid}), waiting for Telegram connect logs..."
    return 0
  fi

  echo "[ERROR] gateway process exited during startup"
  tail -n 80 "$(log_file "${name}")" || true
  return 1
}

start_edge() {
  local name="edge"
  local pid
  pid="$(read_pid "${name}")"
  if is_pid_running "${pid}"; then
    echo "[INFO] edge already running (pid=${pid})"
    return 0
  fi
  if pgrep -f "edge_device.api.server" >/dev/null 2>&1; then
    echo "[WARN] edge process already running (external), skip start"
    return 0
  fi

  echo "[INFO] starting edge in background..."
  (
    cd "${ROOT_DIR}"
    nohup env \
      EDGE_ACTION="${EDGE_ACTION}" \
      EDGE_LOOP="${EDGE_LOOP}" \
      EDGE_INTERVAL_SEC="${EDGE_INTERVAL_SEC}" \
      EDGE_BACKEND_BASE_URL="${EDGE_BACKEND_BASE_URL}" \
      ./scripts/start_edge.sh "${EDGE_ACTION}" >"$(log_file "${name}")" 2>&1 &
    echo $! >"$(pid_file "${name}")"
  )

  pid="$(read_pid "${name}")"
  for _ in $(seq 1 20); do
    if ! is_pid_running "${pid}"; then
      break
    fi
    if grep -q "\"type\": \"heartbeat_response\"" "$(log_file "${name}")" 2>/dev/null; then
      echo "[INFO] edge started (pid=${pid})"
      return 0
    fi
    sleep 0.2
  done

  if is_pid_running "${pid}"; then
    echo "[INFO] edge process is running (pid=${pid})"
    return 0
  fi

  echo "[ERROR] edge process exited during startup"
  tail -n 80 "$(log_file "${name}")" || true
  return 1
}

stop_one() {
  local name="$1"
  local pid
  pid="$(read_pid "${name}")"

  if ! is_pid_running "${pid}"; then
    rm -f "$(pid_file "${name}")"
    echo "[INFO] ${name} already stopped"
    return 0
  fi

  echo "[INFO] stopping ${name} (pid=${pid})..."
  kill "${pid}" >/dev/null 2>&1 || true
  for _ in $(seq 1 30); do
    if ! is_pid_running "${pid}"; then
      rm -f "$(pid_file "${name}")"
      echo "[INFO] ${name} stopped"
      return 0
    fi
    sleep 0.2
  done

  echo "[WARN] ${name} did not exit gracefully, force killing..."
  kill -9 "${pid}" >/dev/null 2>&1 || true
  rm -f "$(pid_file "${name}")"
}

status_one() {
  local name="$1"
  local port="$2"
  local pid
  pid="$(read_pid "${name}")"

  if is_pid_running "${pid}"; then
    echo "[STATUS] ${name}: running pid=${pid} port=${port}"
    return 0
  fi

  if [[ "${name}" == "gateway" ]]; then
    if pgrep -f "nanobot.*gateway" >/dev/null 2>&1; then
      echo "[STATUS] ${name}: running(external) pid=unknown"
      return 0
    fi
  elif [[ "${name}" == "edge" ]]; then
    if pgrep -f "edge_device.api.server" >/dev/null 2>&1; then
      echo "[STATUS] ${name}: running(external) pid=unknown"
      return 0
    fi
  elif is_port_open "${port}"; then
    echo "[STATUS] ${name}: running(external) port=${port} pid=unknown"
    return 0
  fi

  if [[ "${name}" == "gateway" ]]; then
    echo "[STATUS] ${name}: stopped"
  else
    echo "[STATUS] ${name}: stopped"
  fi
}

cmd_start() {
  start_backend
  start_mcp
  start_gateway
  if [[ "${EDGE_ENABLED}" == "1" ]]; then
    start_edge
  else
    echo "[INFO] edge auto-start disabled (EDGE_ENABLED=${EDGE_ENABLED})"
  fi
  echo "[INFO] all requested services handled."
}

cmd_stop() {
  stop_one "edge"
  stop_one "gateway"
  stop_one "mcp"
  stop_one "backend"
}

cmd_status() {
  status_one "backend" "${BACKEND_PORT}"
  status_one "mcp" "${MCP_PORT}"
  status_one "gateway" "${GATEWAY_PORT}"
  status_one "edge" "n/a"
  echo "[INFO] logs directory: ${LOG_DIR}"
}

cmd_logs() {
  local name="${1:-gateway}"
  local file
  file="$(log_file "${name}")"
  if [[ ! -f "${file}" ]]; then
    echo "[ERROR] log not found: ${file}" >&2
    exit 1
  fi
  tail -f "${file}"
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/stack_ctl.sh start
  ./scripts/stack_ctl.sh stop
  ./scripts/stack_ctl.sh restart
  ./scripts/stack_ctl.sh status
  ./scripts/stack_ctl.sh logs [backend|mcp|gateway|edge]

Common env vars:
  NANOBOT_INSTANCE=prod|dev
  NANOBOT_AUTO_DISABLE_MCP=0|1
  EDGE_ENABLED=0|1
  EDGE_ACTION=heartbeat|run-once
  EDGE_LOOP=0|1
  EDGE_INTERVAL_SEC=15
  EDGE_BACKEND_BASE_URL=http://127.0.0.1:8000
  BACKEND_PORT=8000
  MCP_PORT=8001
  NANOBOT_PORT=18790|18791
EOF
}

main() {
  local action="${1:-status}"
  case "${action}" in
    start)
      cmd_start
      ;;
    stop)
      cmd_stop
      ;;
    restart)
      cmd_stop
      cmd_start
      ;;
    status)
      cmd_status
      ;;
    logs)
      cmd_logs "${2:-gateway}"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
