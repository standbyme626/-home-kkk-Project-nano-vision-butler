from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from src.app import create_app


class DeviceEventFlowIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="vision_butler_t15_device_event_")
        self.config_dir = Path(self.tmp_dir.name) / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        repo_root = Path(__file__).resolve().parents[2]
        source_config = repo_root / "config"
        for name in [
            "settings.yaml",
            "policies.yaml",
            "access.yaml",
            "devices.yaml",
            "cameras.yaml",
            "aliases.yaml",
        ]:
            content = yaml.safe_load((source_config / name).read_text(encoding="utf-8"))
            if name == "settings.yaml":
                content["database"]["path"] = str(Path(self.tmp_dir.name) / "device_event_flow.db")
            (self.config_dir / name).write_text(
                yaml.safe_dump(content, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

        self.app = create_app(config_dir=self.config_dir)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.tmp_dir.cleanup()

    def test_ingest_event_persists_observation_event_and_audit(self) -> None:
        heartbeat = self.client.post(
            "/device/heartbeat",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "status": "online",
                "trace_id": "t15-int-heartbeat",
            },
        )
        self.assertEqual(heartbeat.status_code, 200)

        ingest = self.client.post(
            "/device/ingest/event",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
                "object_name": "package",
                "event_type": "security_alert",
                "importance": 5,
                "confidence": 0.96,
                "trace_id": "t15-int-ingest",
            },
        )
        self.assertEqual(ingest.status_code, 200)
        payload = ingest.json()["data"]
        self.assertTrue(payload["accepted"])
        self.assertTrue(payload["event_promoted"])
        self.assertIsNotNone(payload["observation_id"])
        self.assertIsNotNone(payload["event_id"])

        with self.app.state.session_factory.connect() as conn:
            observations = conn.execute("SELECT COUNT(*) AS total FROM observations").fetchone()["total"]
            events = conn.execute("SELECT COUNT(*) AS total FROM events").fetchone()["total"]
            audits = conn.execute(
                "SELECT COUNT(*) AS total FROM audit_logs WHERE action = 'device_ingest_event' AND decision = 'allow'"
            ).fetchone()["total"]
        self.assertEqual(observations, 1)
        self.assertEqual(events, 1)
        self.assertGreaterEqual(audits, 1)

    def test_ingest_event_refreshes_device_liveness(self) -> None:
        observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        heartbeat = self.client.post(
            "/device/heartbeat",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "status": "offline",
                "last_seen": "2000-01-01T00:00:00Z",
                "trace_id": "t15-int-heartbeat-offline",
            },
        )
        self.assertEqual(heartbeat.status_code, 200)

        status_before = self.client.get("/device/status", params={"device_id": "rk3566-dev-01"})
        self.assertEqual(status_before.status_code, 200)
        self.assertFalse(status_before.json()["data"]["is_online"])

        ingest = self.client.post(
            "/device/ingest/event",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
                "object_name": "person",
                "event_type": "object_detected",
                "importance": 4,
                "confidence": 0.88,
                "observed_at": observed_at,
                "trace_id": "t15-int-ingest-refresh",
            },
        )
        self.assertEqual(ingest.status_code, 200)
        self.assertTrue(ingest.json()["data"]["accepted"])

        status_after = self.client.get("/device/status", params={"device_id": "rk3566-dev-01"})
        self.assertEqual(status_after.status_code, 200)
        payload = status_after.json()["data"]
        self.assertTrue(payload["is_online"])
        self.assertEqual(payload["effective_status"], "online")
        self.assertEqual(payload["status"], "online")

    def test_ingest_event_triggers_backend_ocr_when_analysis_requests_present(self) -> None:
        heartbeat = self.client.post(
            "/device/heartbeat",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "status": "online",
                "trace_id": "t15-int-heartbeat-analysis",
            },
        )
        self.assertEqual(heartbeat.status_code, 200)

        ingest = self.client.post(
            "/device/ingest/event",
            json={
                "schema_version": "edge.event.v1",
                "event_id": "evt-analysis-001",
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "seq_no": 100,
                "captured_at": "2026-03-14T08:00:00Z",
                "sent_at": "2026-03-14T08:00:01Z",
                "event_type": "object_detected",
                "zone_id": "entry_door",
                "snapshot_uri": "file:///tmp/mock_receipt.jpg",
                "objects": [
                    {
                        "object_name": "package",
                        "object_class": "package",
                        "confidence": 0.95,
                        "bbox": [120, 120, 420, 420],
                        "zone_id": "entry_door",
                        "track_id": "trk-00042",
                    }
                ],
                "analysis_profile": "backend_heavy_v1",
                "analysis_required": True,
                "analysis_requests": [
                    {
                        "type": "ocr_quick_read",
                        "reason": "package_detected",
                        "priority": "high",
                        "input_uri": "file:///tmp/mock_receipt.jpg",
                    }
                ],
                "trace_id": "t15-int-ingest-analysis",
            },
        )
        self.assertEqual(ingest.status_code, 200)
        payload = ingest.json()["data"]
        self.assertTrue(payload["accepted"])
        self.assertIsNotNone(payload.get("analysis"))
        self.assertEqual(payload["analysis"]["requested"], 1)
        self.assertEqual(payload["analysis"]["executed"], 1)
        self.assertEqual(payload["analysis"]["failed"], 0)

        with self.app.state.session_factory.connect() as conn:
            ocr_count = conn.execute("SELECT COUNT(*) AS total FROM ocr_results").fetchone()["total"]
            analysis_audits = conn.execute(
                "SELECT COUNT(*) AS total FROM audit_logs WHERE action = 'perception_backend_analysis'"
            ).fetchone()["total"]
        self.assertEqual(ocr_count, 1)
        self.assertGreaterEqual(analysis_audits, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
