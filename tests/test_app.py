from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from src.app import create_app


class AppSkeletonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="vision_butler_t4_")
        self.config_dir = Path(self.tmp_dir.name) / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        repo_root = Path(__file__).resolve().parent.parent
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
                content["database"]["path"] = str(Path(self.tmp_dir.name) / "app_test.db")
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

    def test_healthz(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "ok")

    def test_memory_recent_events_route(self) -> None:
        response = self.client.get("/memory/recent-events")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"], [])

    def test_device_status_not_found(self) -> None:
        response = self.client.get("/device/status", params={"device_id": "unknown"})
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertFalse(payload["ok"])

    def test_ingest_event_persists_observation_and_promoted_event(self) -> None:
        response = self.client.post(
            "/device/ingest/event",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "event_type": "security_alert",
                "object_name": "person",
                "zone_id": "entry_door",
                "confidence": 0.98,
                "importance": 5,
                "summary": "person detected",
                "trace_id": "trace-test-ingest-1",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIsNotNone(payload["data"]["observation_id"])
        self.assertTrue(payload["data"]["event_promoted"])
        self.assertIsNotNone(payload["data"]["event_id"])

        with self.app.state.session_factory.connect() as conn:
            obs_count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            evt_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            audit_count = conn.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action IN ('device_ingest_event', 'perception_promote_event')"
            ).fetchone()[0]
        self.assertEqual(obs_count, 1)
        self.assertEqual(evt_count, 1)
        self.assertEqual(audit_count, 2)

    def test_heartbeat_updates_device_status_and_audit(self) -> None:
        response = self.client.post(
            "/device/heartbeat",
            json={
                "device_id": "rk3566-dev-01",
                "status": "online",
                "temperature": 44.5,
                "cpu_load": 0.41,
                "npu_load": 0.29,
                "free_mem_mb": 900,
                "camera_fps": 11,
                "trace_id": "trace-test-heartbeat-1",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "online")

        with self.app.state.session_factory.connect() as conn:
            device_row = conn.execute(
                "SELECT status, last_seen, temperature, cpu_load, npu_load FROM devices WHERE device_id = ?",
                ("rk3566-dev-01",),
            ).fetchone()
            audit_row = conn.execute(
                "SELECT action, decision FROM audit_logs WHERE action = 'device_heartbeat' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(device_row)
        self.assertEqual(device_row["status"], "online")
        self.assertIsNotNone(device_row["last_seen"])
        self.assertAlmostEqual(device_row["temperature"], 44.5)
        self.assertAlmostEqual(device_row["cpu_load"], 0.41)
        self.assertAlmostEqual(device_row["npu_load"], 0.29)
        self.assertIsNotNone(audit_row)
        self.assertEqual(audit_row["decision"], "allow")

    def test_ingest_event_accepts_schema_version_v1(self) -> None:
        response = self.client.post(
            "/device/ingest/event",
            json={
                "schema_version": "edge.event.v1",
                "event_id": "evt-test-v1-001",
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "seq_no": 1,
                "captured_at": "2026-03-14T04:00:00Z",
                "sent_at": "2026-03-14T04:00:00Z",
                "event_type": "security_alert",
                "objects": [
                    {
                        "object_name": "person",
                        "object_class": "person",
                        "confidence": 0.97,
                        "bbox": [10, 20, 200, 300],
                        "zone_id": "entry_door",
                        "track_id": "trk-001",
                    }
                ],
                "trace_id": "trace-test-ingest-v1",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["accepted"])

    def test_ingest_event_rejects_unknown_schema_version(self) -> None:
        response = self.client.post(
            "/device/ingest/event",
            json={
                "schema_version": "edge.event.v9",
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "event_type": "security_alert",
                "objects": [],
            },
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("Unsupported event schema_version", payload["error"]["message"])

    def test_heartbeat_accepts_schema_version_v1(self) -> None:
        response = self.client.post(
            "/device/heartbeat",
            json={
                "schema_version": "edge.heartbeat.v1",
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "online": True,
                "sent_at": "2026-03-14T04:00:00Z",
                "last_capture_ok": True,
                "last_upload_ok": True,
                "temperature": 44.5,
                "trace_id": "trace-test-heartbeat-v1",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "online")

    def test_heartbeat_rejects_unknown_schema_version(self) -> None:
        response = self.client.post(
            "/device/heartbeat",
            json={
                "schema_version": "edge.heartbeat.v9",
                "device_id": "rk3566-dev-01",
                "online": True,
                "sent_at": "2026-03-14T04:00:00Z",
                "last_capture_ok": True,
                "last_upload_ok": True,
            },
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("Unsupported heartbeat schema_version", payload["error"]["message"])

    def test_ingest_event_rejects_unknown_device(self) -> None:
        response = self.client.post(
            "/device/ingest/event",
            json={
                "device_id": "unknown-dev",
                "camera_id": "cam-entry-01",
                "event_type": "security_alert",
                "object_name": "person",
                "importance": 5,
            },
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("DEVICE_NOT_ALLOWED", payload["error"]["message"])

    def test_object_state_supports_present_absent_unknown(self) -> None:
        self.client.post(
            "/device/ingest/event",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
                "object_name": "package_present",
                "confidence": 0.92,
                "trace_id": "trace-state-present",
            },
        )
        self.client.post(
            "/device/ingest/event",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
                "object_name": "package_absent",
                "state_hint": "absent",
                "confidence": 0.02,
                "trace_id": "trace-state-absent",
            },
        )

        present = self.client.get(
            "/memory/object-state",
            params={
                "object_name": "package_present",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
            },
        )
        absent = self.client.get(
            "/memory/object-state",
            params={
                "object_name": "package_absent",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
            },
        )
        unknown = self.client.get(
            "/memory/object-state",
            params={
                "object_name": "never_seen_object",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
            },
        )

        self.assertEqual(present.status_code, 200)
        self.assertEqual(absent.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(present.json()["data"]["state_value"], "present")
        self.assertEqual(absent.json()["data"]["state_value"], "absent")
        self.assertEqual(unknown.json()["data"]["state_value"], "unknown")
        self.assertTrue(present.json()["data"]["reason_code"])
        self.assertTrue(absent.json()["data"]["reason_code"])
        self.assertTrue(unknown.json()["data"]["reason_code"])

    def test_zone_world_state_queries_and_reason_code(self) -> None:
        self.client.post(
            "/device/ingest/event",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
                "object_name": "person_a",
                "confidence": 0.95,
            },
        )
        self.client.post(
            "/device/ingest/event",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
                "object_name": "person_b",
                "confidence": 0.88,
            },
        )

        zone_state = self.client.get(
            "/memory/zone-state",
            params={"camera_id": "cam-entry-01", "zone_id": "entry_door"},
        )
        world_state = self.client.get("/memory/world-state", params={"camera_id": "cam-entry-01"})

        self.assertEqual(zone_state.status_code, 200)
        self.assertEqual(world_state.status_code, 200)
        self.assertIn(zone_state.json()["data"]["state_value"], {"occupied", "likely_occupied"})
        self.assertTrue(zone_state.json()["data"]["reason_code"])
        self.assertIn("summary", world_state.json()["data"])
        self.assertIn("items", world_state.json()["data"])

    def test_policy_evaluate_staleness_stale_and_non_stale(self) -> None:
        self.client.post(
            "/device/ingest/event",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
                "object_name": "stale_object",
                "fresh_until": "2000-01-01T00:00:00Z",
                "confidence": 0.90,
            },
        )
        self.client.post(
            "/device/ingest/event",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
                "object_name": "fresh_object",
                "fresh_until": "2999-01-01T00:00:00Z",
                "confidence": 0.90,
            },
        )

        stale_resp = self.client.get(
            "/policy/evaluate-staleness",
            params={
                "object_name": "stale_object",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
                "query_type": "realtime",
            },
        )
        fresh_resp = self.client.get(
            "/policy/evaluate-staleness",
            params={
                "object_name": "fresh_object",
                "camera_id": "cam-entry-01",
                "zone_id": "entry_door",
                "query_type": "recent",
            },
        )

        self.assertEqual(stale_resp.status_code, 200)
        self.assertEqual(fresh_resp.status_code, 200)
        self.assertTrue(stale_resp.json()["data"]["is_stale"])
        self.assertFalse(fresh_resp.json()["data"]["is_stale"])
        self.assertTrue(stale_resp.json()["data"]["reason_code"])
        self.assertTrue(fresh_resp.json()["data"]["reason_code"])
        self.assertIn(stale_resp.json()["data"]["recency_class"], {"realtime", "recent", "historical"})

    def test_take_snapshot_persists_media_and_audit(self) -> None:
        self.client.post(
            "/device/heartbeat",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "status": "online",
            },
        )
        response = self.client.post(
            "/device/command/take-snapshot",
            json={"device_id": "rk3566-dev-01", "trace_id": "trace-snapshot-1"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["ok"])
        self.assertEqual(payload["data"]["data"]["media_type"], "image")
        self.assertTrue(payload["data"]["data"]["uri"].startswith("file://"))

        with self.app.state.session_factory.connect() as conn:
            media_row = conn.execute(
                "SELECT media_type, owner_type FROM media_items ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            audit_row = conn.execute(
                "SELECT action, decision FROM audit_logs WHERE action = 'device_take_snapshot' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(media_row)
        self.assertEqual(media_row["media_type"], "image")
        self.assertEqual(media_row["owner_type"], "manual")
        self.assertIsNotNone(audit_row)
        self.assertEqual(audit_row["decision"], "allow")

    def test_get_recent_clip_persists_media_and_audit(self) -> None:
        self.client.post(
            "/device/heartbeat",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "status": "online",
            },
        )
        response = self.client.post(
            "/device/command/get-recent-clip",
            json={"device_id": "rk3566-dev-01", "duration_sec": 8, "trace_id": "trace-clip-1"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["data"]["ok"])
        self.assertEqual(payload["data"]["data"]["media_type"], "video")
        self.assertEqual(payload["data"]["data"]["duration_sec"], 8)

        with self.app.state.session_factory.connect() as conn:
            media_row = conn.execute(
                "SELECT media_type, duration_sec FROM media_items ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            audit_row = conn.execute(
                "SELECT action, decision FROM audit_logs WHERE action = 'device_get_recent_clip' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(media_row)
        self.assertEqual(media_row["media_type"], "video")
        self.assertEqual(media_row["duration_sec"], 8)
        self.assertIsNotNone(audit_row)
        self.assertEqual(audit_row["decision"], "allow")

    def test_take_snapshot_returns_explicit_offline_error(self) -> None:
        self.client.post(
            "/device/heartbeat",
            json={
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "status": "offline",
            },
        )
        response = self.client.post(
            "/device/command/take-snapshot",
            json={"device_id": "rk3566-dev-01", "trace_id": "trace-snapshot-offline"},
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertIn("DEVICE_OFFLINE", payload["error"]["message"])

        with self.app.state.session_factory.connect() as conn:
            audit_row = conn.execute(
                "SELECT action, decision, reason FROM audit_logs WHERE action = 'device_take_snapshot' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(audit_row)
        self.assertEqual(audit_row["decision"], "deny")
        self.assertEqual(audit_row["reason"], "DEVICE_OFFLINE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
