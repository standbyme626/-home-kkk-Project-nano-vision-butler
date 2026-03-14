"""Entrypoint and runtime orchestration for RK3566 edge frontend."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from edge_device.api.backend_client import BackendApiClient
from edge_device.cache.ring_buffer import ClipItem, MediaRingBuffer, SnapshotItem
from edge_device.capture.camera import (
    CameraProtocol,
    CapturedFrame,
    LatestFramePrefetchCamera,
    StubCamera,
    compact_now_for_filename,
    create_camera,
    utc_now_iso8601,
)
from edge_device.compression.event_compressor import EventCompressor
from edge_device.health.heartbeat import HeartbeatBuilder
from edge_device.inference.detector import DetectorProtocol, create_detector_from_env
from edge_device.tracking.tracker import LightweightTracker

COMMAND_RESPONSE_SCHEMA_VERSION = "edge.command_response.v1"
LOGGER = logging.getLogger(__name__)


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
    capture_source: str | None = None
    capture_width: int = 1280
    capture_height: int = 720
    capture_fps: int = 25
    capture_pixel_format: str = "MJPG"
    capture_backend: str = "auto"
    capture_retry_count: int = 3
    capture_retry_delay_sec: float = 1.0
    capture_parallel: bool = True
    capture_parallel_wait_sec: float = 0.4
    snapshot_dir: Path = field(default_factory=lambda: Path("./data/edge_device/snapshots"))
    clip_dir: Path = field(default_factory=lambda: Path("./data/edge_device/clips"))
    snapshot_buffer_size: int = 32
    clip_buffer_size: int = 16
    pending_event_dir: Path = field(default_factory=lambda: Path("./data/edge_device/pending_events"))
    pending_event_max: int = 256
    pending_flush_batch: int = 32


class EdgeDeviceRuntime:
    """Single-process edge runtime: capture -> detect -> track -> compress -> report."""

    def __init__(
        self,
        *,
        config: EdgeDeviceConfig,
        backend_client: BackendClientProtocol | None = None,
        camera: CameraProtocol | None = None,
        detector: DetectorProtocol | None = None,
        tracker: LightweightTracker | None = None,
        compressor: EventCompressor | None = None,
        cache: MediaRingBuffer | None = None,
        heartbeat_builder: HeartbeatBuilder | None = None,
    ) -> None:
        self.config = config
        self.backend_client = backend_client or BackendApiClient(base_url=config.backend_base_url)
        created_camera = camera or create_camera(
            source=config.capture_source,
            width=config.capture_width,
            height=config.capture_height,
            fps=config.capture_fps,
            pixel_format=config.capture_pixel_format,
            backend=config.capture_backend,
            retry_count=config.capture_retry_count,
            retry_delay_sec=config.capture_retry_delay_sec,
        )
        self.camera: CameraProtocol = created_camera
        if (
            camera is None
            and config.capture_parallel
            and not isinstance(created_camera, StubCamera)
        ):
            self.camera = LatestFramePrefetchCamera(
                camera=created_camera,
                target_fps=config.capture_fps,
                wait_timeout_sec=config.capture_parallel_wait_sec,
            )
            LOGGER.info(
                "capture prefetch enabled: source=%s fps=%s wait_timeout=%.2fs",
                config.capture_source or "<auto>",
                config.capture_fps,
                config.capture_parallel_wait_sec,
            )
        self.detector = detector or create_detector_from_env()
        self.tracker = tracker or LightweightTracker()
        self.compressor = compressor or EventCompressor()
        self.cache = cache or MediaRingBuffer(
            snapshot_capacity=config.snapshot_buffer_size,
            clip_capacity=config.clip_buffer_size,
        )
        self.heartbeat_builder = heartbeat_builder or HeartbeatBuilder(model_version=self.detector.model_version)
        self._event_seq_no = 0
        self.config.pending_event_dir.mkdir(parents=True, exist_ok=True)

    def __del__(self) -> None:  # pragma: no cover - defensive cleanup path
        try:
            if isinstance(self.camera, LatestFramePrefetchCamera):
                self.camera.stop()
        except Exception:
            return

    def run_once(self, *, trace_id: str | None = None) -> dict[str, Any]:
        frame = self.camera.capture_latest_frame()
        detections = self.tracker.assign_tracks(self.detector.detect(frame))
        detector_error = self._as_optional_text(getattr(self.detector, "last_error", None))
        if detector_error:
            LOGGER.warning("Detector degraded for %s/%s: %s", self.config.device_id, self.config.camera_id, detector_error)
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
            detector_error=detector_error,
        )
        backend_response = self.backend_client.post_event(envelope["payload"])
        event_queued = False
        if not self._is_backend_ack(backend_response):
            self._enqueue_pending_event(envelope["payload"])
            event_queued = True
        return {
            "ok": True,
            "type": "edge_run_once",
            "data": {
                "frame_id": frame.frame_id,
                "detections": len(detections),
                "model_version": self.detector.model_version,
                "detector_error": detector_error,
                "snapshot_uri": snapshot.uri,
                "event_envelope": envelope,
                "backend_response": backend_response,
                "event_queued": event_queued,
                "pending_event_count": self._pending_event_count(),
            },
        }

    def send_heartbeat(self, *, trace_id: str | None = None) -> dict[str, Any]:
        flush_report = self._flush_pending_events()
        payload = self.heartbeat_builder.build(
            device_id=self.config.device_id,
            camera_id=self.config.camera_id,
            trace_id=trace_id,
        )
        payload["last_upload_ok"] = bool(flush_report.get("ok"))
        backend_response = self.backend_client.post_heartbeat(payload)
        payload["last_upload_ok"] = bool(flush_report.get("ok")) and self._is_backend_ack(backend_response)
        return {
            "ok": True,
            "type": "heartbeat_response",
            "data": {
                "payload": payload,
                "backend_response": backend_response,
                "flush_report": flush_report,
                "pending_event_count": self._pending_event_count(),
            },
        }

    def take_snapshot(self, *, trace_id: str | None = None, command_id: str | None = None) -> dict[str, Any]:
        frame = self.camera.capture_latest_frame()
        snapshot = self._store_snapshot(frame)
        self.cache.add_snapshot(snapshot)
        effective_command_id = command_id or f"cmd-snapshot-{uuid4().hex[:12]}"
        return {
            "ok": True,
            "type": "command_response",
            "schema_version": COMMAND_RESPONSE_SCHEMA_VERSION,
            "summary": "Snapshot command completed",
            "data": {
                "command": "take_snapshot",
                "command_id": effective_command_id,
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

    @staticmethod
    def _as_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def get_recent_clip(
        self,
        *,
        duration_sec: int = 6,
        trace_id: str | None = None,
        command_id: str | None = None,
    ) -> dict[str, Any]:
        clip = self.cache.get_recent_clip(duration_sec)
        if clip is None:
            clip = self._assemble_clip(duration_sec)
            self.cache.add_clip(clip)

        effective_command_id = command_id or f"cmd-clip-{uuid4().hex[:12]}"
        return {
            "ok": True,
            "type": "command_response",
            "schema_version": COMMAND_RESPONSE_SCHEMA_VERSION,
            "summary": "Recent clip command completed",
            "data": {
                "command": "get_recent_clip",
                "command_id": effective_command_id,
                "device_id": self.config.device_id,
                "camera_id": self.config.camera_id,
                "duration_sec": clip.duration_sec,
                "clip_uri": clip.uri,
                "clip_path": clip.path,
                "cache_metrics": self.cache.cache_metrics(),
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
        try:
            self._write_snapshot_jpeg(output=output, frame=frame)
        finally:
            self._cleanup_frame_artifacts(frame)
        return SnapshotItem(
            snapshot_id=f"snap-{uuid4().hex[:12]}",
            captured_at=frame.captured_at,
            path=str(output),
            uri=f"file://{output.resolve()}",
            width=frame.width,
            height=frame.height,
        )

    def _write_snapshot_jpeg(self, *, output: Path, frame: CapturedFrame) -> None:
        width = max(int(frame.width), 1)
        height = max(int(frame.height), 1)
        overlay_title = f"{self.config.camera_id} {frame.frame_id}"
        overlay_meta = f"{frame.captured_at} {frame.pixel_format}"

        if self._try_write_snapshot_from_frame(
            output=output,
            frame=frame,
            width=width,
            height=height,
        ):
            return

        try:
            from PIL import Image, ImageDraw

            image = Image.new("RGB", (width, height), color=(16, 18, 22))
            draw = ImageDraw.Draw(image)
            band_h = max(height // 14, 20)
            draw.rectangle([(0, 0), (width, band_h)], fill=(42, 108, 198))
            draw.text((10, 6), overlay_title, fill=(255, 255, 255))
            draw.text((10, band_h + 8), overlay_meta, fill=(230, 230, 230))
            draw.rectangle([(0, height - 6), (width, height)], fill=(42, 108, 198))
            image.save(output, format="JPEG", quality=90, optimize=True)
            return
        except Exception as pil_exc:
            pil_error = pil_exc

        try:
            import cv2
            import numpy as np

            canvas = np.zeros((height, width, 3), dtype=np.uint8)
            canvas[:, :] = (22, 18, 16)
            band_h = max(height // 14, 20)
            cv2.rectangle(canvas, (0, 0), (width - 1, band_h), (198, 108, 42), thickness=-1)
            cv2.putText(
                canvas,
                overlay_title[:80],
                (10, min(20, band_h - 2)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                canvas,
                overlay_meta[:110],
                (10, min(height - 10, band_h + 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (230, 230, 230),
                1,
                cv2.LINE_AA,
            )
            ok = cv2.imwrite(str(output), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if not ok:
                raise RuntimeError("cv2.imwrite returned False")
            return
        except Exception as cv_exc:
            raise RuntimeError(
                "Failed to encode snapshot JPEG "
                f"(pillow={pil_error!r}, opencv={cv_exc!r})"
            ) from cv_exc

    @staticmethod
    def _cleanup_frame_artifacts(frame: CapturedFrame) -> None:
        if not frame.image_path:
            return
        path = Path(frame.image_path)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            LOGGER.warning("Failed to cleanup captured frame artifact %s: %s", path, exc)

    @staticmethod
    def _try_write_snapshot_from_frame(
        *,
        output: Path,
        frame: CapturedFrame,
        width: int,
        height: int,
    ) -> bool:
        if not frame.image_path:
            return False
        source = Path(frame.image_path)
        if not source.is_file():
            return False

        try:
            shutil.copyfile(source, output)
            if output.exists() and output.stat().st_size > 0:
                return True
        except OSError as copy_exc:
            LOGGER.warning("Direct snapshot copy from captured frame failed: %s", copy_exc)

        try:
            from PIL import Image

            with Image.open(source) as image:
                rgb = image.convert("RGB")
                if rgb.size != (width, height):
                    rgb = rgb.resize((width, height))
                rgb.save(output, format="JPEG", quality=92, optimize=True)
            return True
        except Exception as pil_exc:
            LOGGER.warning("Pillow snapshot write from captured frame failed: %s", pil_exc)

        try:
            import cv2

            data = cv2.imread(str(source), cv2.IMREAD_COLOR)
            if data is None:
                return False
            if data.shape[1] != width or data.shape[0] != height:
                data = cv2.resize(data, (width, height))
            ok = cv2.imwrite(str(output), data, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            return bool(ok)
        except Exception as cv_exc:
            LOGGER.warning("OpenCV snapshot write from captured frame failed: %s", cv_exc)
            return False

    def _assemble_clip(self, duration_sec: int) -> ClipItem:
        duration = max(int(duration_sec), 1)
        latest_snapshot = self.cache.latest_snapshot()
        if latest_snapshot is None:
            latest_snapshot = self._store_snapshot(self.camera.capture_latest_frame())
            self.cache.add_snapshot(latest_snapshot)

        self.config.clip_dir.mkdir(parents=True, exist_ok=True)
        timestamp = compact_now_for_filename()
        file_name = f"{self.config.camera_id}_clip_{duration}s_{timestamp}.mp4"
        output = self.config.clip_dir / file_name

        clip_fps = min(max(int(self.config.capture_fps), 2), 12)
        frame_count = max(duration * clip_fps, 1)
        source_snapshots = self.cache.recent_snapshots(limit=max(frame_count, 1))
        if not source_snapshots:
            source_snapshots = [latest_snapshot]

        self._write_clip_mp4(
            output=output,
            snapshots=source_snapshots,
            frame_count=frame_count,
            fps=clip_fps,
        )
        start_at = source_snapshots[0].captured_at
        end_at = source_snapshots[-1].captured_at if source_snapshots else utc_now_iso8601()
        return ClipItem(
            clip_id=f"clip-{uuid4().hex[:12]}",
            start_at=start_at,
            end_at=end_at,
            duration_sec=duration,
            path=str(output),
            uri=f"file://{output.resolve()}",
            source_snapshot_id=source_snapshots[-1].snapshot_id if source_snapshots else None,
        )

    def _write_clip_mp4(
        self,
        *,
        output: Path,
        snapshots: list[SnapshotItem],
        frame_count: int,
        fps: int,
    ) -> None:
        frames_bgr = self._load_clip_frames(snapshots=snapshots)
        if not frames_bgr:
            raise RuntimeError("No frame available for clip encoding")

        first = frames_bgr[0]
        target_h, target_w = first.shape[0], first.shape[1]
        render_frames: list[Any] = []
        source_total = len(frames_bgr)
        for idx in range(max(frame_count, 1)):
            source_idx = min((idx * source_total) // max(frame_count, 1), source_total - 1)
            frame = frames_bgr[source_idx]
            if frame.shape[0] != target_h or frame.shape[1] != target_w:
                import cv2

                frame = cv2.resize(frame, (target_w, target_h))
            render_frames.append(frame)

        opencv_error: Exception | None = None
        try:
            import cv2

            writer = cv2.VideoWriter(
                str(output),
                cv2.VideoWriter_fourcc(*"mp4v"),
                float(fps),
                (target_w, target_h),
            )
            if not writer.isOpened():
                raise RuntimeError("cv2.VideoWriter failed to open mp4 output")
            try:
                for frame in render_frames:
                    writer.write(frame)
            finally:
                writer.release()
            if output.exists() and output.stat().st_size > 0:
                return
            raise RuntimeError("OpenCV produced empty mp4 file")
        except Exception as exc:
            opencv_error = exc

        try:
            import imageio.v3 as iio

            rgb_frames = [frame[:, :, ::-1] for frame in render_frames]
            iio.imwrite(output, rgb_frames, fps=float(fps), codec="libx264")
            if output.exists() and output.stat().st_size > 0:
                return
            raise RuntimeError("imageio produced empty mp4 file")
        except Exception as imageio_exc:
            raise RuntimeError(
                "Failed to encode clip mp4 "
                f"(opencv={opencv_error!r}, imageio={imageio_exc!r})"
            ) from imageio_exc

    def _load_clip_frames(self, *, snapshots: list[SnapshotItem]) -> list[Any]:
        frames: list[Any] = []
        for snapshot in snapshots:
            frame = self._read_snapshot_as_bgr(Path(snapshot.path))
            if frame is not None:
                frames.append(frame)

        if frames:
            return frames

        fallback = self._store_snapshot(self.camera.capture_latest_frame())
        self.cache.add_snapshot(fallback)
        fallback_frame = self._read_snapshot_as_bgr(Path(fallback.path))
        if fallback_frame is not None:
            frames.append(fallback_frame)
        return frames

    @staticmethod
    def _read_snapshot_as_bgr(path: Path) -> Any | None:
        if not path.exists():
            return None
        try:
            import cv2

            frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if frame is not None:
                return frame
        except Exception:
            pass

        try:
            import numpy as np
            from PIL import Image

            with Image.open(path) as image:
                rgb = image.convert("RGB")
                array = np.asarray(rgb)
            return array[:, :, ::-1].copy()
        except Exception:
            return None

    def _next_event_seq_no(self) -> int:
        self._event_seq_no += 1
        return self._event_seq_no

    def _pending_event_count(self) -> int:
        return len(list(self.config.pending_event_dir.glob("*.json")))

    def _pending_event_files(self) -> list[Path]:
        files = [path for path in self.config.pending_event_dir.glob("*.json") if path.is_file()]
        return sorted(files, key=lambda item: item.name)

    @staticmethod
    def _pending_priority(payload: dict[str, Any]) -> int:
        event_type = str(payload.get("event_type") or "").strip().lower()
        try:
            importance = int(payload.get("importance") or 0)
        except (TypeError, ValueError):
            importance = 0
        if event_type == "security_alert" or importance >= 4:
            return 0
        if event_type == "object_detected":
            return 1
        return 5

    def _enqueue_pending_event(self, payload: dict[str, Any]) -> None:
        priority = self._pending_priority(payload)
        now = compact_now_for_filename()
        file_name = f"{priority:02d}_{now}_{uuid4().hex[:8]}.json"
        output = self.config.pending_event_dir / file_name
        output.write_text(
            json.dumps(
                {
                    "queued_at": utc_now_iso8601(),
                    "priority": priority,
                    "payload": payload,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        self._enforce_pending_limit()

    def _enforce_pending_limit(self) -> None:
        files = self._pending_event_files()
        overflow = len(files) - max(int(self.config.pending_event_max), 1)
        if overflow <= 0:
            return

        def drop_order(path: Path) -> tuple[int, str]:
            priority = self._priority_from_file_name(path.name)
            # Drop low-priority files first (higher numeric value), then oldest by file name.
            return (-priority, path.name)

        for target in sorted(files, key=drop_order)[:overflow]:
            try:
                target.unlink(missing_ok=True)
                LOGGER.warning("Dropped pending event due to backpressure: %s", target.name)
            except OSError as exc:  # pragma: no cover - filesystem boundary
                LOGGER.warning("Failed to remove pending event file %s: %s", target, exc)

    def _flush_pending_events(self) -> dict[str, Any]:
        files = self._pending_event_files()
        if not files:
            return {
                "ok": True,
                "attempted": 0,
                "flushed": 0,
                "failed": 0,
            }

        attempted = 0
        flushed = 0
        failed = 0
        last_error: str | None = None
        batch = max(int(self.config.pending_flush_batch), 1)
        for event_file in files[:batch]:
            attempted += 1
            try:
                raw = json.loads(event_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                failed += 1
                last_error = f"read_pending_event_failed:{exc}"
                LOGGER.warning("Pending event file unreadable, dropping: %s", event_file)
                event_file.unlink(missing_ok=True)
                continue

            payload = raw.get("payload") if isinstance(raw, dict) else None
            if not isinstance(payload, dict):
                failed += 1
                last_error = "pending_event_missing_payload"
                event_file.unlink(missing_ok=True)
                continue

            backend_response = self.backend_client.post_event(payload)
            if self._is_backend_ack(backend_response):
                flushed += 1
                event_file.unlink(missing_ok=True)
                continue

            failed += 1
            last_error = self._as_optional_text(backend_response.get("error")) or "pending_event_upload_failed"
            break

        return {
            "ok": failed == 0,
            "attempted": attempted,
            "flushed": flushed,
            "failed": failed,
            "last_error": last_error,
        }

    @staticmethod
    def _priority_from_file_name(name: str) -> int:
        head, _, _ = name.partition("_")
        try:
            return int(head)
        except ValueError:
            return 99

    @staticmethod
    def _is_backend_ack(response: dict[str, Any]) -> bool:
        if not isinstance(response, dict):
            return False
        if not bool(response.get("ok")):
            return False
        data = response.get("data")
        if isinstance(data, dict) and "accepted" in data and not bool(data.get("accepted")):
            return False
        return True

    def pending_event_snapshot(self) -> list[dict[str, Any]]:
        snapshot: list[dict[str, Any]] = []
        for event_file in self._pending_event_files():
            try:
                raw = json.loads(event_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            payload = raw.get("payload") if isinstance(raw, dict) else {}
            if not isinstance(payload, dict):
                payload = {}
            snapshot.append(
                {
                    "file": event_file.name,
                    "priority": self._priority_from_file_name(event_file.name),
                    "event_id": self._as_optional_text(payload.get("event_id")),
                    "event_type": self._as_optional_text(payload.get("event_type")),
                    "importance": payload.get("importance"),
                }
            )
        return snapshot


def load_config_from_env() -> EdgeDeviceConfig:
    capture_resolution = os.getenv("EDGE_CAPTURE_RESOLUTION", "1280x720")
    capture_width, capture_height = _parse_resolution(capture_resolution)
    return EdgeDeviceConfig(
        device_id=os.getenv("EDGE_DEVICE_ID", "rk3566-dev-01"),
        camera_id=os.getenv("EDGE_CAMERA_ID", "cam-entry-01"),
        backend_base_url=os.getenv("EDGE_BACKEND_BASE_URL", "http://100.92.134.46:8000"),
        capture_source=(os.getenv("EDGE_CAPTURE_SOURCE", "") or None),
        capture_width=int(os.getenv("EDGE_CAPTURE_WIDTH", str(capture_width))),
        capture_height=int(os.getenv("EDGE_CAPTURE_HEIGHT", str(capture_height))),
        capture_fps=int(os.getenv("EDGE_CAPTURE_FPS", "30")),
        capture_pixel_format=os.getenv("EDGE_CAPTURE_PIXEL_FORMAT", "MJPG"),
        capture_backend=os.getenv("EDGE_CAPTURE_BACKEND", "auto"),
        capture_retry_count=int(os.getenv("EDGE_CAPTURE_RETRY_COUNT", "3")),
        capture_retry_delay_sec=float(os.getenv("EDGE_CAPTURE_RETRY_DELAY_SEC", "1.0")),
        capture_parallel=_parse_bool_env(os.getenv("EDGE_CAPTURE_PARALLEL"), fallback=True),
        capture_parallel_wait_sec=float(os.getenv("EDGE_CAPTURE_PARALLEL_WAIT_SEC", "0.4")),
        snapshot_dir=Path(os.getenv("EDGE_SNAPSHOT_DIR", "./data/edge_device/snapshots")),
        clip_dir=Path(os.getenv("EDGE_CLIP_DIR", "./data/edge_device/clips")),
        snapshot_buffer_size=int(os.getenv("EDGE_SNAPSHOT_BUFFER_SIZE", "32")),
        clip_buffer_size=int(os.getenv("EDGE_CLIP_BUFFER_SIZE", "16")),
        pending_event_dir=Path(os.getenv("EDGE_PENDING_EVENT_DIR", "./data/edge_device/pending_events")),
        pending_event_max=int(os.getenv("EDGE_PENDING_EVENT_MAX", "256")),
        pending_flush_batch=int(os.getenv("EDGE_PENDING_FLUSH_BATCH", "32")),
    )


def _parse_resolution(value: str) -> tuple[int, int]:
    normalized = (value or "").strip().lower()
    if "x" not in normalized:
        return 1280, 720
    left, right = normalized.split("x", 1)
    try:
        width = max(int(left), 1)
        height = max(int(right), 1)
        return width, height
    except ValueError:
        return 1280, 720


def _parse_bool_env(raw: str | None, *, fallback: bool) -> bool:
    if raw is None:
        return fallback
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return fallback


def main() -> None:
    parser = argparse.ArgumentParser(description="RK3566 edge frontend runtime")
    parser.add_argument(
        "action",
        choices=["run-once", "heartbeat", "take-snapshot", "get-recent-clip"],
        help="Runtime action",
    )
    parser.add_argument("--duration-sec", type=int, default=6, help="Clip duration for get-recent-clip")
    parser.add_argument("--trace-id", type=str, default=None, help="Optional trace ID")
    parser.add_argument("--command-id", type=str, default=None, help="Optional command ID")
    args = parser.parse_args()

    runtime = EdgeDeviceRuntime(config=load_config_from_env())
    if args.action == "run-once":
        result = runtime.run_once(trace_id=args.trace_id)
    elif args.action == "heartbeat":
        result = runtime.send_heartbeat(trace_id=args.trace_id)
    elif args.action == "take-snapshot":
        result = runtime.take_snapshot(trace_id=args.trace_id, command_id=args.command_id)
    else:
        result = runtime.get_recent_clip(
            duration_sec=args.duration_sec,
            trace_id=args.trace_id,
            command_id=args.command_id,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
