"""Entrypoint and runtime orchestration for RK3566 edge frontend."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from edge_device.api.backend_client import BackendApiClient
from edge_device.cache.ring_buffer import ClipItem, MediaRingBuffer, SnapshotItem
from edge_device.capture.camera import CapturedFrame, StubCamera, utc_now_iso8601
from edge_device.compression.event_compressor import EventCompressor
from edge_device.health.heartbeat import HeartbeatBuilder
from edge_device.inference.detector import LightweightDetector
from edge_device.tracking.tracker import LightweightTracker

COMMAND_RESPONSE_SCHEMA_VERSION = "edge.command_response.v1"


class BackendClientProtocol(Protocol):
    def post_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    def post_heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class EdgeDeviceConfig:
    device_id: str
    camera_id: str
    backend_base_url: str
    snapshot_dir: Path = field(default_factory=lambda: Path("./data/edge_device/snapshots"))
    clip_dir: Path = field(default_factory=lambda: Path("./data/edge_device/clips"))
    snapshot_buffer_size: int = 32
    clip_buffer_size: int = 16


class EdgeDeviceRuntime:
    """Single-process edge runtime: capture -> detect -> track -> compress -> report."""

    def __init__(
        self,
        *,
        config: EdgeDeviceConfig,
        backend_client: BackendClientProtocol | None = None,
        camera: StubCamera | None = None,
        detector: LightweightDetector | None = None,
        tracker: LightweightTracker | None = None,
        compressor: EventCompressor | None = None,
        cache: MediaRingBuffer | None = None,
        heartbeat_builder: HeartbeatBuilder | None = None,
    ) -> None:
        self.config = config
        self.backend_client = backend_client or BackendApiClient(base_url=config.backend_base_url)
        self.camera = camera or StubCamera(source=config.camera_id)
        self.detector = detector or LightweightDetector()
        self.tracker = tracker or LightweightTracker()
        self.compressor = compressor or EventCompressor()
        self.cache = cache or MediaRingBuffer(
            snapshot_capacity=config.snapshot_buffer_size,
            clip_capacity=config.clip_buffer_size,
        )
        self.heartbeat_builder = heartbeat_builder or HeartbeatBuilder(model_version=self.detector.model_version)
        self._event_seq_no = 0

    def run_once(self, *, trace_id: str | None = None) -> dict[str, Any]:
        frame = self.camera.capture_latest_frame()
        detections = self.tracker.assign_tracks(self.detector.detect(frame))
        snapshot = self._store_snapshot(frame)
        self.cache.add_snapshot(snapshot)

        envelope = self.compressor.build_envelope(
            device_id=self.config.device_id,
            camera_id=self.config.camera_id,
            seq_no=self._next_event_seq_no(),
            frame=frame,
            detections=detections,
            snapshot_uri=snapshot.uri,
            model_version=self.detector.model_version,
            trace_id=trace_id,
        )
        backend_response = self.backend_client.post_event(envelope["payload"])
        return {
            "ok": True,
            "type": "edge_run_once",
            "data": {
                "frame_id": frame.frame_id,
                "detections": len(detections),
                "snapshot_uri": snapshot.uri,
                "event_envelope": envelope,
                "backend_response": backend_response,
            },
        }

    def send_heartbeat(self, *, trace_id: str | None = None) -> dict[str, Any]:
        payload = self.heartbeat_builder.build(
            device_id=self.config.device_id,
            camera_id=self.config.camera_id,
            trace_id=trace_id,
        )
        backend_response = self.backend_client.post_heartbeat(payload)
        return {
            "ok": True,
            "type": "heartbeat_response",
            "data": {
                "payload": payload,
                "backend_response": backend_response,
            },
        }

    def take_snapshot(self, *, trace_id: str | None = None) -> dict[str, Any]:
        frame = self.camera.capture_latest_frame()
        snapshot = self._store_snapshot(frame)
        self.cache.add_snapshot(snapshot)
        command_id = f"cmd-snapshot-{uuid4().hex[:12]}"
        return {
            "ok": True,
            "type": "command_response",
            "schema_version": COMMAND_RESPONSE_SCHEMA_VERSION,
            "summary": "Snapshot command completed",
            "data": {
                "command": "take_snapshot",
                "command_id": command_id,
                "device_id": self.config.device_id,
                "camera_id": self.config.camera_id,
                "snapshot_uri": snapshot.uri,
                "snapshot_path": snapshot.path,
                "captured_at": snapshot.captured_at,
            },
            "meta": {
                "trace_id": trace_id,
                "received_at": utc_now_iso8601(),
            },
        }

    def get_recent_clip(self, *, duration_sec: int = 6, trace_id: str | None = None) -> dict[str, Any]:
        clip = self.cache.get_recent_clip(duration_sec)
        if clip is None:
            clip = self._assemble_clip(duration_sec)
            self.cache.add_clip(clip)

        command_id = f"cmd-clip-{uuid4().hex[:12]}"
        return {
            "ok": True,
            "type": "command_response",
            "schema_version": COMMAND_RESPONSE_SCHEMA_VERSION,
            "summary": "Recent clip command completed",
            "data": {
                "command": "get_recent_clip",
                "command_id": command_id,
                "device_id": self.config.device_id,
                "camera_id": self.config.camera_id,
                "duration_sec": clip.duration_sec,
                "clip_uri": clip.uri,
                "clip_path": clip.path,
            },
            "meta": {
                "trace_id": trace_id,
                "received_at": utc_now_iso8601(),
            },
        }

    def _store_snapshot(self, frame: CapturedFrame) -> SnapshotItem:
        self.config.snapshot_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{self.config.camera_id}_{frame.frame_id}.jpg"
        output = self.config.snapshot_dir / file_name
        output.write_text(
            f"stub snapshot for {frame.frame_id} captured at {frame.captured_at}\n",
            encoding="utf-8",
        )
        return SnapshotItem(
            snapshot_id=f"snap-{uuid4().hex[:12]}",
            captured_at=frame.captured_at,
            path=str(output),
            uri=f"file://{output.resolve()}",
            width=frame.width,
            height=frame.height,
        )

    def _assemble_clip(self, duration_sec: int) -> ClipItem:
        duration = max(int(duration_sec), 1)
        latest_snapshot = self.cache.latest_snapshot()
        if latest_snapshot is None:
            latest_snapshot = self._store_snapshot(self.camera.capture_latest_frame())
            self.cache.add_snapshot(latest_snapshot)

        self.config.clip_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        file_name = f"{self.config.camera_id}_clip_{duration}s_{timestamp}.mp4"
        output = self.config.clip_dir / file_name
        output.write_text(
            (
                "stub clip placeholder\n"
                f"source_snapshot={latest_snapshot.snapshot_id}\n"
                f"duration_sec={duration}\n"
            ),
            encoding="utf-8",
        )

        return ClipItem(
            clip_id=f"clip-{uuid4().hex[:12]}",
            start_at=latest_snapshot.captured_at,
            end_at=utc_now_iso8601(),
            duration_sec=duration,
            path=str(output),
            uri=f"file://{output.resolve()}",
            source_snapshot_id=latest_snapshot.snapshot_id,
        )

    def _next_event_seq_no(self) -> int:
        self._event_seq_no += 1
        return self._event_seq_no


def load_config_from_env() -> EdgeDeviceConfig:
    return EdgeDeviceConfig(
        device_id=os.getenv("EDGE_DEVICE_ID", "rk3566-dev-01"),
        camera_id=os.getenv("EDGE_CAMERA_ID", "cam-entry-01"),
        backend_base_url=os.getenv("EDGE_BACKEND_BASE_URL", "http://127.0.0.1:8000"),
        snapshot_dir=Path(os.getenv("EDGE_SNAPSHOT_DIR", "./data/edge_device/snapshots")),
        clip_dir=Path(os.getenv("EDGE_CLIP_DIR", "./data/edge_device/clips")),
        snapshot_buffer_size=int(os.getenv("EDGE_SNAPSHOT_BUFFER_SIZE", "32")),
        clip_buffer_size=int(os.getenv("EDGE_CLIP_BUFFER_SIZE", "16")),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="RK3566 edge frontend runtime")
    parser.add_argument(
        "action",
        choices=["run-once", "heartbeat", "take-snapshot", "get-recent-clip"],
        help="Runtime action",
    )
    parser.add_argument("--duration-sec", type=int, default=6, help="Clip duration for get-recent-clip")
    parser.add_argument("--trace-id", type=str, default=None, help="Optional trace ID")
    args = parser.parse_args()

    runtime = EdgeDeviceRuntime(config=load_config_from_env())
    if args.action == "run-once":
        result = runtime.run_once(trace_id=args.trace_id)
    elif args.action == "heartbeat":
        result = runtime.send_heartbeat(trace_id=args.trace_id)
    elif args.action == "take-snapshot":
        result = runtime.take_snapshot(trace_id=args.trace_id)
    else:
        result = runtime.get_recent_clip(duration_sec=args.duration_sec, trace_id=args.trace_id)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
