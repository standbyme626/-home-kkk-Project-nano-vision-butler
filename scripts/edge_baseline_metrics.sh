#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

: "${EDGE_BASELINE_OUTPUT_DIR:=${REPO_ROOT}/data/edge_device/baseline}"
: "${EDGE_BASELINE_DURATION_SEC:=1800}"
: "${EDGE_BASELINE_INTERVAL_SEC:=5}"
: "${EDGE_BASELINE_DRY_RUN:=0}"

usage() {
  cat <<'EOF'
Usage:
  scripts/edge_baseline_metrics.sh [options]

Options:
  --output-dir <dir>        Output directory (default: data/edge_device/baseline)
  --duration-sec <int>      Capture duration in seconds (default: 1800)
  --interval-sec <int>      Sampling interval in seconds (default: 5)
  --dry-run                 Capture one sample and exit
  -h, --help                Show help

Environment overrides:
  EDGE_BASELINE_OUTPUT_DIR
  EDGE_BASELINE_DURATION_SEC
  EDGE_BASELINE_INTERVAL_SEC
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
    --duration-sec)
      EDGE_BASELINE_DURATION_SEC="${2:-}"
      shift 2
      ;;
    --interval-sec)
      EDGE_BASELINE_INTERVAL_SEC="${2:-}"
      shift 2
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

require_positive_int "duration-sec" "${EDGE_BASELINE_DURATION_SEC}"
require_positive_int "interval-sec" "${EDGE_BASELINE_INTERVAL_SEC}"

mkdir -p "${EDGE_BASELINE_OUTPUT_DIR}"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${EDGE_BASELINE_OUTPUT_DIR}/metrics_${RUN_ID}"
mkdir -p "${RUN_DIR}"

METRICS_CSV="${RUN_DIR}/metrics.csv"
SYSTEM_INFO_FILE="${RUN_DIR}/system_info.txt"
SUMMARY_FILE="${RUN_DIR}/metrics_summary.txt"

NPU_FREQ_FILE=""
NPU_LOAD_FILE=""

find_npu_metric_files() {
  local candidate
  for candidate in \
    /sys/class/devfreq/*npu*/cur_freq \
    /sys/class/devfreq/*rknpu*/cur_freq \
    /sys/class/devfreq/*fdab*/cur_freq \
    /sys/class/devfreq/*npu*/load \
    /sys/class/devfreq/*rknpu*/load \
    /sys/kernel/debug/rknpu/load; do
    if [[ "${candidate}" == *"/cur_freq" ]] && [[ -z "${NPU_FREQ_FILE}" ]] && [[ -r "${candidate}" ]]; then
      NPU_FREQ_FILE="${candidate}"
    fi
    if [[ "${candidate}" == *"/load" ]] && [[ -z "${NPU_LOAD_FILE}" ]] && [[ -r "${candidate}" ]]; then
      NPU_LOAD_FILE="${candidate}"
    fi
  done
}

cpu_temp_celsius() {
  local temp_raw
  for temp_raw in \
    /sys/class/thermal/thermal_zone0/temp \
    /sys/class/thermal/thermal_zone1/temp; do
    if [[ -r "${temp_raw}" ]]; then
      awk '{ printf "%.1f", $1 / 1000.0 }' "${temp_raw}"
      return
    fi
  done
  echo "NA"
}

memory_usage_pct() {
  awk '
    /^MemTotal:/ { total=$2 }
    /^MemAvailable:/ { avail=$2 }
    END {
      if (total == 0) {
        print "0.00"
      } else {
        used = total - avail
        printf "%.2f", used * 100 / total
      }
    }
  ' /proc/meminfo
}

cpu_usage_pct() {
  local prev curr
  prev="$(awk '/^cpu / {print $2,$3,$4,$5,$6,$7,$8,$9}' /proc/stat)"
  sleep 1
  curr="$(awk '/^cpu / {print $2,$3,$4,$5,$6,$7,$8,$9}' /proc/stat)"
  awk -v p="${prev}" -v c="${curr}" '
    BEGIN {
      split(p, P, " ");
      split(c, C, " ");
      ptotal=0; ctotal=0;
      for (i=1; i<=8; i++) {
        ptotal += P[i];
        ctotal += C[i];
      }
      pidle = P[4] + P[5];
      cidle = C[4] + C[5];
      totald = ctotal - ptotal;
      idled = cidle - pidle;
      if (totald <= 0) {
        printf "0.00";
      } else {
        printf "%.2f", (totald - idled) * 100 / totald;
      }
    }
  '
}

loadavg_values() {
  awk '{ print $1 "," $2 "," $3 }' /proc/loadavg
}

npu_freq_value() {
  if [[ -n "${NPU_FREQ_FILE}" ]] && [[ -r "${NPU_FREQ_FILE}" ]]; then
    cat "${NPU_FREQ_FILE}"
  else
    echo "NA"
  fi
}

npu_load_value() {
  if [[ -n "${NPU_LOAD_FILE}" ]] && [[ -r "${NPU_LOAD_FILE}" ]]; then
    awk '
      {
        if ($0 ~ /^[0-9]+$/) {
          print $0;
        } else if (match($0, /[0-9]+/)) {
          print substr($0, RSTART, RLENGTH);
        } else {
          print "NA";
        }
      }
    ' "${NPU_LOAD_FILE}"
  else
    echo "NA"
  fi
}

write_system_info() {
  {
    echo "run_id=${RUN_ID}"
    echo "started_at=$(date -Iseconds)"
    echo "hostname=$(hostname)"
    echo "kernel=$(uname -a)"
    echo "uptime=$(uptime -p 2>/dev/null || uptime)"
    echo ""
    echo "[cpuinfo]"
    sed -n '1,20p' /proc/cpuinfo 2>/dev/null || true
    echo ""
    echo "[meminfo]"
    sed -n '1,20p' /proc/meminfo 2>/dev/null || true
    echo ""
    echo "[npu_probe]"
    echo "npu_freq_file=${NPU_FREQ_FILE:-NA}"
    echo "npu_load_file=${NPU_LOAD_FILE:-NA}"
  } > "${SYSTEM_INFO_FILE}"
}

find_npu_metric_files
write_system_info

echo "timestamp,cpu_usage_pct,mem_usage_pct,load1,load5,load15,cpu_temp_c,npu_freq_hz,npu_load_pct" > "${METRICS_CSV}"

start_epoch="$(date +%s)"
end_epoch="$((start_epoch + EDGE_BASELINE_DURATION_SEC))"

while true; do
  timestamp="$(date -Iseconds)"
  cpu_pct="$(cpu_usage_pct)"
  mem_pct="$(memory_usage_pct)"
  load_values="$(loadavg_values)"
  temp_c="$(cpu_temp_celsius)"
  npu_freq="$(npu_freq_value)"
  npu_load="$(npu_load_value)"

  echo "${timestamp},${cpu_pct},${mem_pct},${load_values},${temp_c},${npu_freq},${npu_load}" >> "${METRICS_CSV}"

  if [[ "${EDGE_BASELINE_DRY_RUN}" == "1" ]]; then
    break
  fi

  now_epoch="$(date +%s)"
  if (( now_epoch >= end_epoch )); then
    break
  fi
  sleep "${EDGE_BASELINE_INTERVAL_SEC}"
done

{
  echo "run_id=${RUN_ID}"
  echo "finished_at=$(date -Iseconds)"
  echo "metrics_csv=${METRICS_CSV}"
  echo "system_info=${SYSTEM_INFO_FILE}"
  awk -F, '
    NR == 1 { next }
    {
      cpu += $2;
      mem += $3;
      n++;
    }
    END {
      if (n == 0) {
        print "sample_count=0";
        print "avg_cpu_pct=NA";
        print "avg_mem_pct=NA";
      } else {
        printf "sample_count=%d\n", n;
        printf "avg_cpu_pct=%.2f\n", cpu / n;
        printf "avg_mem_pct=%.2f\n", mem / n;
      }
    }
  ' "${METRICS_CSV}"
} > "${SUMMARY_FILE}"

echo "[OK] Baseline metrics artifacts saved under: ${RUN_DIR}"
