#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

: "${SOAK_SNAPSHOT_LOOPS:=120}"
: "${SOAK_CLIP_LOOPS:=60}"
: "${SOAK_EVENT_LOOPS:=120}"
: "${SOAK_HEARTBEAT_LOOPS:=240}"
: "${SOAK_SNAPSHOT_SUCCESS_TARGET:=0.99}"
: "${SOAK_CLIP_SUCCESS_TARGET:=0.98}"
: "${SOAK_SNAPSHOT_P95_TARGET_SEC:=0.80}"
: "${SOAK_CLIP_P95_TARGET_SEC:=1.50}"
: "${SOAK_EVENT_P95_TARGET_SEC:=2.00}"
: "${SOAK_REPORT_PATH:=${REPO_ROOT}/docs/edge/soak_test_report.md}"

echo "[SOAK] running edge reliability soak test"
echo "[SOAK] snapshot_loops=${SOAK_SNAPSHOT_LOOPS} clip_loops=${SOAK_CLIP_LOOPS} event_loops=${SOAK_EVENT_LOOPS} heartbeat_loops=${SOAK_HEARTBEAT_LOOPS}"

python3 - "$REPO_ROOT" \
  "$SOAK_SNAPSHOT_LOOPS" "$SOAK_CLIP_LOOPS" "$SOAK_EVENT_LOOPS" "$SOAK_HEARTBEAT_LOOPS" \
  "$SOAK_SNAPSHOT_SUCCESS_TARGET" "$SOAK_CLIP_SUCCESS_TARGET" \
  "$SOAK_SNAPSHOT_P95_TARGET_SEC" "$SOAK_CLIP_P95_TARGET_SEC" "$SOAK_EVENT_P95_TARGET_SEC" \
  "$SOAK_REPORT_PATH" <<'PY'
from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from edge_device.api.server import EdgeDeviceConfig, EdgeDeviceRuntime


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(int(round(0.95 * len(ordered))) - 1, 0)
    return ordered[min(idx, len(ordered) - 1)]


def parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class StableBackend:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.heartbeats: list[dict[str, Any]] = []
        self.event_latencies_sec: list[float] = []

    def post_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.events.append(payload)
        captured = str(payload.get("captured_at") or payload.get("observed_at") or "")
        if captured:
            delta = (datetime.now(tz=timezone.utc) - parse_iso8601(captured)).total_seconds()
            self.event_latencies_sec.append(max(delta, 0.0))
        return {"ok": True, "data": {"accepted": True, "type": "device_ingest_event"}}

    def post_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.heartbeats.append(payload)
        return {"ok": True, "data": {"accepted": True, "type": "device_heartbeat"}}


class ToggleBackend:
    def __init__(self) -> None:
        self.allow_event = False
        self.events: list[dict[str, Any]] = []
        self.heartbeats: list[dict[str, Any]] = []

    def post_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.allow_event:
            return {"ok": False, "error": "network_error", "detail": "simulated offline"}
        self.events.append(payload)
        return {"ok": True, "data": {"accepted": True, "type": "device_ingest_event"}}

    def post_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.heartbeats.append(payload)
        return {"ok": True, "data": {"accepted": True, "type": "device_heartbeat"}}


repo_root = Path(os.sys.argv[1])
snapshot_loops = int(os.sys.argv[2])
clip_loops = int(os.sys.argv[3])
event_loops = int(os.sys.argv[4])
heartbeat_loops = int(os.sys.argv[5])
snapshot_success_target = float(os.sys.argv[6])
clip_success_target = float(os.sys.argv[7])
snapshot_p95_target = float(os.sys.argv[8])
clip_p95_target = float(os.sys.argv[9])
event_p95_target = float(os.sys.argv[10])
report_path = Path(os.sys.argv[11])

tmp_dir = tempfile.TemporaryDirectory(prefix="vision_butler_t13i_soak_")
media_root = Path(tmp_dir.name) / "edge_media"

backend = StableBackend()
runtime = EdgeDeviceRuntime(
    config=EdgeDeviceConfig(
        device_id="rk3566-dev-01",
        camera_id="cam-entry-01",
        backend_base_url="http://127.0.0.1:8000",
        capture_source="stub://camera",
        capture_width=640,
        capture_height=360,
        capture_fps=10,
        snapshot_dir=media_root / "snapshots",
        clip_dir=media_root / "clips",
        pending_event_dir=media_root / "pending_events",
        pending_event_max=64,
        pending_flush_batch=32,
    ),
    backend_client=backend,
)

snapshot_latencies: list[float] = []
snapshot_ok = 0
for _ in range(snapshot_loops):
    start = time.perf_counter()
    result = runtime.take_snapshot(trace_id="trace-soak-snapshot")
    snapshot_latencies.append(time.perf_counter() - start)
    snapshot_ok += int(bool(result.get("ok")))
snapshot_success = snapshot_ok / max(snapshot_loops, 1)
snapshot_p95 = p95(snapshot_latencies)

clip_latencies: list[float] = []
clip_ok = 0
for idx in range(clip_loops):
    start = time.perf_counter()
    result = runtime.get_recent_clip(duration_sec=(2 + idx), trace_id="trace-soak-clip")
    clip_latencies.append(time.perf_counter() - start)
    clip_ok += int(bool(result.get("ok")))
clip_success = clip_ok / max(clip_loops, 1)
clip_p95 = p95(clip_latencies)

for _ in range(event_loops):
    runtime.run_once(trace_id="trace-soak-event")
event_p95 = p95(backend.event_latencies_sec)

heartbeat_online = 0
for _ in range(heartbeat_loops):
    hb = runtime.send_heartbeat(trace_id="trace-soak-heartbeat")
    heartbeat_online += int(bool(hb["data"]["payload"].get("online")))
heartbeat_online_ratio = heartbeat_online / max(heartbeat_loops, 1)

toggle_backend = ToggleBackend()
recovery_runtime = EdgeDeviceRuntime(
    config=EdgeDeviceConfig(
        device_id="rk3566-dev-01",
        camera_id="cam-entry-01",
        backend_base_url="http://127.0.0.1:8000",
        capture_source="stub://camera",
        capture_width=640,
        capture_height=360,
        capture_fps=10,
        snapshot_dir=media_root / "snapshots_recovery",
        clip_dir=media_root / "clips_recovery",
        pending_event_dir=media_root / "pending_events_recovery",
        pending_event_max=3,
        pending_flush_batch=8,
    ),
    backend_client=toggle_backend,
)
for _ in range(4):
    recovery_runtime.run_once(trace_id="trace-soak-offline")
queued_before = len(recovery_runtime.pending_event_snapshot())
hb_offline = recovery_runtime.send_heartbeat(trace_id="trace-soak-hb-offline")
toggle_backend.allow_event = True
hb_online = recovery_runtime.send_heartbeat(trace_id="trace-soak-hb-online")
queued_after = len(recovery_runtime.pending_event_snapshot())

network_recovery_ok = (
    queued_before >= 1
    and len(toggle_backend.heartbeats) >= 2
    and bool(hb_offline["ok"])
    and bool(hb_online["ok"])
    and queued_after == 0
)

result = {
    "snapshot_success_rate": round(snapshot_success, 4),
    "snapshot_p95_sec": round(snapshot_p95, 4),
    "clip_success_rate": round(clip_success, 4),
    "clip_p95_sec": round(clip_p95, 4),
    "event_ingest_p95_sec": round(event_p95, 4),
    "heartbeat_online_ratio": round(heartbeat_online_ratio, 4),
    "network_recovery_ok": network_recovery_ok,
    "backpressure_queue_before_recovery": queued_before,
    "backpressure_queue_after_recovery": queued_after,
    "thresholds": {
        "snapshot_success_rate": snapshot_success_target,
        "clip_success_rate": clip_success_target,
        "snapshot_p95_sec": snapshot_p95_target,
        "clip_p95_sec": clip_p95_target,
        "event_ingest_p95_sec": event_p95_target,
    },
}

passed = (
    snapshot_success >= snapshot_success_target
    and clip_success >= clip_success_target
    and snapshot_p95 <= snapshot_p95_target
    and clip_p95 <= clip_p95_target
    and event_p95 <= event_p95_target
    and heartbeat_online_ratio == 1.0
    and network_recovery_ok
)
result["passed"] = passed

report_path.parent.mkdir(parents=True, exist_ok=True)
report_lines = [
    "# Edge Soak Test Report",
    "",
    f"- generated_at: {datetime.now(tz=timezone.utc).isoformat()}",
    f"- snapshot_success_rate: {result['snapshot_success_rate']}",
    f"- snapshot_p95_sec: {result['snapshot_p95_sec']}",
    f"- clip_success_rate: {result['clip_success_rate']}",
    f"- clip_p95_sec: {result['clip_p95_sec']}",
    f"- event_ingest_p95_sec: {result['event_ingest_p95_sec']}",
    f"- heartbeat_online_ratio: {result['heartbeat_online_ratio']}",
    f"- network_recovery_ok: {result['network_recovery_ok']}",
    f"- backpressure_queue_before_recovery: {result['backpressure_queue_before_recovery']}",
    f"- backpressure_queue_after_recovery: {result['backpressure_queue_after_recovery']}",
    f"- passed: {result['passed']}",
]
report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))

tmp_dir.cleanup()
if not passed:
    raise SystemExit(2)
PY

echo "[SOAK] report written to ${SOAK_REPORT_PATH}"
echo "[SOAK] OK"
