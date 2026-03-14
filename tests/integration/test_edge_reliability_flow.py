from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from edge_device.api.server import EdgeDeviceConfig, EdgeDeviceRuntime


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(int(round(0.95 * len(ordered))) - 1, 0)
    return ordered[min(idx, len(ordered) - 1)]


def _parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class _AlwaysOkBackend:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.event_latencies_sec: list[float] = []
        self.heartbeats: list[dict[str, Any]] = []

    def post_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.events.append(payload)
        captured_at = str(payload.get("captured_at") or payload.get("observed_at") or "")
        if captured_at:
            captured_ts = _parse_iso8601(captured_at)
            latency = (datetime.now(tz=timezone.utc) - captured_ts).total_seconds()
            self.event_latencies_sec.append(max(latency, 0.0))
        return {"ok": True, "data": {"accepted": True, "type": "device_ingest_event"}}

    def post_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.heartbeats.append(payload)
        return {"ok": True, "data": {"accepted": True, "type": "device_heartbeat"}}


class _ToggleBackend:
    def __init__(self) -> None:
        self.allow_events = False
        self.events: list[dict[str, Any]] = []
        self.heartbeats: list[dict[str, Any]] = []

    def post_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.allow_events:
            return {"ok": False, "error": "network_error", "detail": "simulated offline"}
        self.events.append(payload)
        return {"ok": True, "data": {"accepted": True, "type": "device_ingest_event"}}

    def post_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.heartbeats.append(payload)
        return {"ok": True, "data": {"accepted": True, "type": "device_heartbeat"}}


class EdgeReliabilityFlowIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="vision_butler_t13i_")
        self.media_root = Path(self.tmp_dir.name) / "edge_media"

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _runtime(self, backend: Any, *, pending_event_max: int = 32, pending_flush_batch: int = 16) -> EdgeDeviceRuntime:
        return EdgeDeviceRuntime(
            config=EdgeDeviceConfig(
                device_id="rk3566-dev-01",
                camera_id="cam-entry-01",
                backend_base_url="http://127.0.0.1:8000",
                capture_source="stub://camera",
                capture_width=640,
                capture_height=360,
                capture_fps=10,
                snapshot_dir=self.media_root / "snapshots",
                clip_dir=self.media_root / "clips",
                pending_event_dir=self.media_root / "pending_events",
                pending_event_max=pending_event_max,
                pending_flush_batch=pending_flush_batch,
                snapshot_buffer_size=32,
                clip_buffer_size=8,
            ),
            backend_client=backend,
        )

    def test_snapshot_clip_success_rate_and_latency_thresholds(self) -> None:
        backend = _AlwaysOkBackend()
        runtime = self._runtime(backend)

        snapshot_latencies: list[float] = []
        snapshot_ok = 0
        for _ in range(30):
            start = time.perf_counter()
            result = runtime.take_snapshot(trace_id="trace-t13i-snapshot")
            snapshot_latencies.append(time.perf_counter() - start)
            snapshot_ok += int(bool(result.get("ok")))
        snapshot_success = snapshot_ok / 30.0
        snapshot_p95 = _p95(snapshot_latencies)

        clip_latencies: list[float] = []
        clip_ok = 0
        for idx in range(15):
            start = time.perf_counter()
            duration = 2 + idx
            result = runtime.get_recent_clip(duration_sec=duration, trace_id="trace-t13i-clip")
            clip_latencies.append(time.perf_counter() - start)
            clip_ok += int(bool(result.get("ok")))
        clip_success = clip_ok / 15.0
        clip_p95 = _p95(clip_latencies)

        self.assertGreaterEqual(snapshot_success, 0.99)
        self.assertLessEqual(snapshot_p95, 0.8)
        self.assertGreaterEqual(clip_success, 0.98)
        self.assertLessEqual(clip_p95, 1.5)

    def test_event_ingest_latency_and_heartbeat_stability(self) -> None:
        backend = _AlwaysOkBackend()
        runtime = self._runtime(backend)

        for _ in range(20):
            runtime.run_once(trace_id="trace-t13i-event")
        self.assertEqual(len(backend.events), 20)
        self.assertTrue(backend.event_latencies_sec)
        event_p95 = _p95(backend.event_latencies_sec)
        self.assertLessEqual(event_p95, 2.0)

        online_values: list[bool] = []
        for _ in range(40):
            heartbeat = runtime.send_heartbeat(trace_id="trace-t13i-hb")
            payload = heartbeat["data"]["payload"]
            online_values.append(bool(payload["online"]))
            self.assertTrue(payload["last_upload_ok"])
        self.assertEqual(set(online_values), {True})

    def test_offline_recovery_and_backpressure_policy(self) -> None:
        backend = _ToggleBackend()
        runtime = self._runtime(backend, pending_event_max=3, pending_flush_batch=8)

        # Offline phase: events are queued and heartbeat still sent.
        for _ in range(4):
            run_once = runtime.run_once(trace_id="trace-t13i-offline")
            self.assertTrue(run_once["ok"])
            self.assertTrue(run_once["data"]["event_queued"])
        queued = runtime.pending_event_snapshot()
        self.assertEqual(len(queued), 3, msg="queue should enforce pending_event_max")

        hb_offline = runtime.send_heartbeat(trace_id="trace-t13i-hb-offline")
        self.assertTrue(hb_offline["ok"])
        self.assertEqual(len(backend.heartbeats), 1, msg="heartbeat should still be posted under backpressure")
        self.assertFalse(hb_offline["data"]["payload"]["last_upload_ok"])

        # Add mixed-priority payloads, then ensure critical event is preserved when queue overflows.
        runtime._enqueue_pending_event(  # noqa: SLF001
            {
                "event_id": "evt-low-scene",
                "event_type": "scene_observed",
                "importance": 2,
                "captured_at": "2026-03-14T00:00:00Z",
            }
        )
        runtime._enqueue_pending_event(  # noqa: SLF001
            {
                "event_id": "evt-critical-security",
                "event_type": "security_alert",
                "importance": 5,
                "captured_at": "2026-03-14T00:00:01Z",
            }
        )
        snapshot = runtime.pending_event_snapshot()
        self.assertEqual(len(snapshot), 3)
        self.assertTrue(any(item["event_id"] == "evt-critical-security" for item in snapshot))

        # Recovery phase: queued events are flushed and removed.
        backend.allow_events = True
        hb_online = runtime.send_heartbeat(trace_id="trace-t13i-hb-online")
        self.assertTrue(hb_online["ok"])
        self.assertTrue(hb_online["data"]["payload"]["last_upload_ok"])
        flush_report = hb_online["data"]["flush_report"]
        self.assertGreaterEqual(flush_report["flushed"], 1)
        self.assertEqual(runtime.pending_event_snapshot(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
