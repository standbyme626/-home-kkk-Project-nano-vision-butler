from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


class EdgeProtocolSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parent.parent.parent
        self.schemas_dir = self.repo_root / "schemas"
        self.examples_dir = self.repo_root / "docs" / "examples"

    def _load_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _validate(self, *, schema_name: str, payload: dict) -> None:
        schema_path = self.schemas_dir / schema_name
        schema = self._load_json(schema_path)
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda err: err.path)
        self.assertEqual(
            errors,
            [],
            msg="\n".join(error.message for error in errors),
        )

    def test_event_example_matches_schema(self) -> None:
        payload = self._load_json(self.examples_dir / "device_ingest_event_min.json")
        self._validate(schema_name="edge_event_envelope.schema.json", payload=payload)

    def test_heartbeat_example_matches_schema(self) -> None:
        payload = self._load_json(self.examples_dir / "device_heartbeat_min.json")
        self._validate(schema_name="edge_heartbeat.schema.json", payload=payload)

    def test_command_response_payload_matches_schema(self) -> None:
        payload = {
            "schema_version": "edge.command_response.v1",
            "type": "command_response",
            "ok": True,
            "summary": "Snapshot command completed",
            "data": {
                "command": "take_snapshot",
                "command_id": "cmd-snapshot-123",
                "device_id": "rk3566-dev-01",
                "camera_id": "cam-entry-01",
                "snapshot_uri": "file:///tmp/snapshot.jpg"
            },
            "meta": {
                "trace_id": "trace-cmd-schema-1",
                "received_at": "2026-03-14T04:00:00Z"
            }
        }
        self._validate(schema_name="edge_command_response.schema.json", payload=payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
