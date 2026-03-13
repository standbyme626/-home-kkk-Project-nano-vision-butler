"""Compresses detections into backend-consumable event envelopes."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from edge_device.capture.camera import CapturedFrame
from edge_device.inference.detector import Detection

EVENT_SCHEMA_VERSION = "edge.event.v1"


def utc_now_iso8601() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class EventCompressor:
    """Normalize edge detections into a single event envelope."""

    def build_envelope(
        self,
        *,
        device_id: str,
        camera_id: str,
        seq_no: int,
        frame: CapturedFrame,
        detections: list[Detection],
        snapshot_uri: str | None,
        clip_uri: str | None = None,
        model_version: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, object]:
        primary = max(detections, key=lambda item: item.confidence) if detections else None
        emitted_at = utc_now_iso8601()
        event_id = f"evt-{uuid4().hex[:12]}"
        serialized_objects = [self._serialize_detection(item) for item in detections]
        payload = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_id": event_id,
            "device_id": device_id,
            "camera_id": camera_id,
            "seq_no": seq_no,
            "captured_at": frame.captured_at,
            "sent_at": emitted_at,
            "event_type": "object_detected" if detections else "scene_observed",
            "zone_id": primary.zone_id if primary else None,
            "objects": serialized_objects,
            "snapshot_uri": snapshot_uri,
            "clip_uri": clip_uri,
            "model_version": model_version,
            "compress_reason": "event_compressor_v1",
            "signature": None,
            # Backward-compatible fields consumed by current backend code.
            "observed_at": frame.captured_at,
            "category": "event",
            "importance": self._importance(detections),
            "summary": self._summary(primary, len(detections), camera_id),
            "object_name": primary.object_name if primary else "scene",
            "object_class": primary.object_class if primary else "scene",
            "track_id": primary.track_id if primary else None,
            "confidence": round(primary.confidence, 3) if primary else None,
            "raw_detections": serialized_objects,
        }
        if trace_id:
            payload["trace_id"] = trace_id

        return {
            "schema": "vision_butler.edge.event_envelope.v1",
            "envelope_id": f"env-{uuid4().hex[:12]}",
            "emitted_at": emitted_at,
            "device_id": device_id,
            "camera_id": camera_id,
            "trace_id": trace_id,
            "payload": payload,
        }

    @staticmethod
    def _serialize_detection(item: Detection) -> dict[str, object]:
        return {
            "object_name": item.object_name,
            "object_class": item.object_class,
            "confidence": round(item.confidence, 3),
            "bbox": list(item.bbox),
            "zone_id": item.zone_id,
            "track_id": item.track_id,
        }

    @staticmethod
    def _importance(detections: list[Detection]) -> int:
        if not detections:
            return 2
        max_conf = max(item.confidence for item in detections)
        if max_conf >= 0.9:
            return 5
        if max_conf >= 0.75:
            return 4
        if max_conf >= 0.5:
            return 3
        return 2

    @staticmethod
    def _summary(primary: Detection | None, detection_count: int, camera_id: str) -> str:
        if primary is None:
            return f"scene_observed on {camera_id}"
        return (
            f"object_detected: {primary.object_name} "
            f"(track={primary.track_id or 'n/a'}, confidence={primary.confidence:.2f}, count={detection_count})"
        )
