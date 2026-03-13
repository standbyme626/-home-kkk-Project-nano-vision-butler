from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from edge_device.api.server import EdgeDeviceConfig, EdgeDeviceRuntime


class FakeBackendClient:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.heartbeats: list[dict[str, Any]] = []

    def post_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.events.append(payload)
        return {"ok": True, "data": {"accepted": True, "type": "device_ingest_event"}}

    def post_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.heartbeats.append(payload)
        return {"ok": True, "data": {"accepted": True, "type": "device_heartbeat"}}


class EdgeRuntimeUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="vision_butler_edge_t13_")
        root = Path(self.tmp_dir.name)
        self.backend = FakeBackendClient()
        self.runtime = EdgeDeviceRuntime(
            config=EdgeDeviceConfig(
                device_id="rk3566-dev-01",
                camera_id="cam-entry-01",
                backend_base_url="http://127.0.0.1:8000",
                snapshot_dir=root / "snapshots",
                clip_dir=root / "clips",
                snapshot_buffer_size=4,
                clip_buffer_size=3,
            ),
            backend_client=self.backend,
        )

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_run_once_posts_backend_event_with_envelope_payload(self) -> None:
        result = self.runtime.run_once(trace_id="trace-edge-run-1")

        self.assertTrue(result["ok"])
        self.assertEqual(result["type"], "edge_run_once")
        self.assertEqual(len(self.backend.events), 1)
        posted = self.backend.events[0]
        self.assertEqual(posted["schema_version"], "edge.event.v1")
        self.assertEqual(posted["device_id"], "rk3566-dev-01")
        self.assertEqual(posted["camera_id"], "cam-entry-01")
        self.assertIn("event_id", posted)
        self.assertIn("objects", posted)
        self.assertIn("object_name", posted)
        self.assertIn("raw_detections", posted)

        envelope = result["data"]["event_envelope"]
        self.assertEqual(envelope["schema"], "vision_butler.edge.event_envelope.v1")
        self.assertEqual(envelope["payload"]["trace_id"], "trace-edge-run-1")

    def test_heartbeat_payload_is_built_and_sent(self) -> None:
        result = self.runtime.send_heartbeat(trace_id="trace-edge-hb-1")

        self.assertTrue(result["ok"])
        self.assertEqual(len(self.backend.heartbeats), 1)
        payload = self.backend.heartbeats[0]
        self.assertEqual(payload["schema_version"], "edge.heartbeat.v1")
        self.assertEqual(payload["device_id"], "rk3566-dev-01")
        self.assertEqual(payload["camera_id"], "cam-entry-01")
        self.assertEqual(payload["trace_id"], "trace-edge-hb-1")
        self.assertTrue(payload["online"])
        self.assertIn("last_capture_ok", payload)
        self.assertIn("last_upload_ok", payload)
        self.assertIn("last_seen", payload)

    def test_snapshot_and_clip_commands_return_stable_contract(self) -> None:
        snapshot = self.runtime.take_snapshot(trace_id="trace-edge-snapshot-1")
        clip = self.runtime.get_recent_clip(duration_sec=6, trace_id="trace-edge-clip-1")

        self.assertTrue(snapshot["ok"])
        self.assertEqual(snapshot["type"], "command_response")
        self.assertEqual(snapshot["schema_version"], "edge.command_response.v1")
        self.assertEqual(snapshot["data"]["command"], "take_snapshot")
        self.assertTrue(snapshot["data"]["snapshot_uri"].startswith("file://"))

        self.assertTrue(clip["ok"])
        self.assertEqual(clip["type"], "command_response")
        self.assertEqual(clip["schema_version"], "edge.command_response.v1")
        self.assertEqual(clip["data"]["command"], "get_recent_clip")
        self.assertEqual(clip["data"]["duration_sec"], 6)
        self.assertTrue(clip["data"]["clip_uri"].startswith("file://"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
