"""Compresses detections into backend-consumable event envelopes."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from edge_device.capture.camera import CapturedFrame
from edge_device.inference.detector import Detection

EVENT_SCHEMA_VERSION = "edge.event.v1"


def utc_now_iso8601() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class EventCompressor:
    """Normalize detections with configurable threshold, dedupe, and throttle policies."""

    def __init__(
        self,
        *,
        min_confidence: float | None = None,
        dedupe_window_sec: float | None = None,
        throttle_window_sec: float | None = None,
        time_provider: Callable[[], float] | None = None,
    ) -> None:
        self.min_confidence = _clamp_float(
            _resolve_float(value=min_confidence, env_key="EDGE_EVENT_MIN_CONFIDENCE", fallback=0.35),
            lower=0.0,
            upper=1.0,
        )
        self.dedupe_window_sec = max(
            _resolve_float(value=dedupe_window_sec, env_key="EDGE_EVENT_DEDUPE_WINDOW_SEC", fallback=1.0),
            0.0,
        )
        self.throttle_window_sec = max(
            _resolve_float(value=throttle_window_sec, env_key="EDGE_EVENT_THROTTLE_WINDOW_SEC", fallback=0.0),
            0.0,
        )
        self.analysis_enable = _resolve_bool(env_key="EDGE_ANALYSIS_ENABLE", fallback=True)
        self.analysis_ocr_enable = _resolve_bool(env_key="EDGE_ANALYSIS_OCR_ENABLE", fallback=True)
        self.analysis_min_importance_ocr = _resolve_int(
            env_key="EDGE_ANALYSIS_MIN_IMPORTANCE_OCR",
            fallback=4,
            minimum=1,
            maximum=5,
        )
        self.analysis_profile = (os.getenv("EDGE_ANALYSIS_PROFILE", "backend_heavy_v1") or "").strip() or "backend_heavy_v1"
        self._time_provider = time_provider or time.monotonic
        self._last_meaningful_emit_at_by_camera: dict[str, float] = {}
        self._last_signature_at: dict[str, float] = {}

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
        detector_error: str | None = None,
    ) -> dict[str, object]:
        now_monotonic = self._time_provider()
        filtered_detections = self._filter_by_confidence(detections)
        suppress_reason = self._suppress_reason(
            camera_id=camera_id,
            detections=filtered_detections,
            now_monotonic=now_monotonic,
        )
        if suppress_reason is not None:
            filtered_detections = []

        primary = max(filtered_detections, key=lambda item: item.confidence) if filtered_detections else None
        importance = self._importance(filtered_detections)
        analysis_requests = self._build_analysis_requests(
            primary=primary,
            importance=importance,
            snapshot_uri=snapshot_uri,
        )
        emitted_at = utc_now_iso8601()
        event_id = f"evt-{uuid4().hex[:12]}"
        serialized_objects = [self._serialize_detection(item) for item in filtered_detections]
        reason_parts = [
            "event_compressor_v2",
            f"conf>={self.min_confidence:.2f}",
        ]
        if self.dedupe_window_sec > 0:
            reason_parts.append(f"dedupe={self.dedupe_window_sec:.2f}s")
        if self.throttle_window_sec > 0:
            reason_parts.append(f"throttle={self.throttle_window_sec:.2f}s")
        if detections and not filtered_detections and suppress_reason is None:
            reason_parts.append("below_conf_threshold")
        if suppress_reason:
            reason_parts.append(suppress_reason)
        if detector_error:
            reason_parts.append("detector_degraded")
        compress_reason = "|".join(reason_parts)

        payload = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "event_id": event_id,
            "device_id": device_id,
            "camera_id": camera_id,
            "seq_no": seq_no,
            "captured_at": frame.captured_at,
            "sent_at": emitted_at,
            "event_type": "object_detected" if filtered_detections else "scene_observed",
            "zone_id": primary.zone_id if primary else None,
            "objects": serialized_objects,
            "snapshot_uri": snapshot_uri,
            "clip_uri": clip_uri,
            "model_version": model_version,
            "compress_reason": compress_reason,
            "signature": None,
            "analysis_profile": self.analysis_profile if self.analysis_enable else None,
            "analysis_required": bool(analysis_requests),
            "analysis_requests": analysis_requests,
            # Backward-compatible fields consumed by current backend code.
            "observed_at": frame.captured_at,
            "category": "event",
            "importance": importance,
            "summary": self._summary(primary, len(filtered_detections), camera_id),
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

    def _filter_by_confidence(self, detections: list[Detection]) -> list[Detection]:
        return [item for item in detections if item.confidence >= self.min_confidence]

    def _suppress_reason(
        self,
        *,
        camera_id: str,
        detections: list[Detection],
        now_monotonic: float,
    ) -> str | None:
        if not detections:
            return None

        if self.throttle_window_sec > 0:
            last_emit = self._last_meaningful_emit_at_by_camera.get(camera_id)
            if last_emit is not None and now_monotonic - last_emit < self.throttle_window_sec:
                return "throttled"

        signature = self._fingerprint(camera_id=camera_id, detections=detections)
        if self.dedupe_window_sec > 0:
            last_signature_at = self._last_signature_at.get(signature)
            if last_signature_at is not None and now_monotonic - last_signature_at < self.dedupe_window_sec:
                return "deduplicated"

        self._last_meaningful_emit_at_by_camera[camera_id] = now_monotonic
        self._last_signature_at[signature] = now_monotonic
        return None

    @staticmethod
    def _fingerprint(*, camera_id: str, detections: list[Detection]) -> str:
        chunks: list[str] = [camera_id]
        for item in sorted(
            detections,
            key=lambda det: (
                det.object_class,
                det.zone_id or "",
                det.track_id or "",
                round(det.confidence, 2),
            ),
        ):
            chunks.append(
                f"{item.object_class}:{item.zone_id or 'global'}:{item.track_id or 'na'}:{round(item.confidence, 2):.2f}"
            )
        return "|".join(chunks)

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

    def _build_analysis_requests(
        self,
        *,
        primary: Detection | None,
        importance: int,
        snapshot_uri: str | None,
    ) -> list[dict[str, object]]:
        if not self.analysis_enable or not self.analysis_ocr_enable:
            return []
        if primary is None or not snapshot_uri:
            return []
        if importance < self.analysis_min_importance_ocr:
            return []
        if primary.confidence < max(self.min_confidence, 0.70):
            return []
        if primary.object_class not in {"package", "document", "label", "screen"}:
            return []

        priority = "high" if importance >= 4 else "normal"
        return [
            {
                "type": "ocr_quick_read",
                "priority": priority,
                "reason": f"{primary.object_class}_detected",
                "input_uri": snapshot_uri,
                "object_class": primary.object_class,
                "track_id": primary.track_id,
            }
        ]


def _resolve_float(*, value: float | None, env_key: str, fallback: float) -> float:
    if value is not None:
        return float(value)
    raw = os.getenv(env_key)
    if raw is None:
        return fallback
    try:
        return float(raw)
    except ValueError:
        return fallback


def _clamp_float(value: float, *, lower: float, upper: float) -> float:
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value


def _resolve_bool(*, env_key: str, fallback: bool) -> bool:
    raw = os.getenv(env_key)
    if raw is None:
        return fallback
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return fallback


def _resolve_int(*, env_key: str, fallback: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(env_key)
    if raw is None:
        return fallback
    try:
        parsed = int(raw)
    except ValueError:
        parsed = fallback
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed
