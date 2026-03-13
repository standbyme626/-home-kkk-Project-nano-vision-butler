"""Capture layer for RK3566 edge runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from typing import Protocol


def utc_now_iso8601() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class CapturedFrame:
    frame_id: str
    captured_at: str
    width: int
    height: int
    source: str
    pixel_format: str = "rgb24"


class CaptureError(RuntimeError):
    """Raised when real camera capture fails after retries."""


class CameraProtocol(Protocol):
    def capture_latest_frame(self) -> CapturedFrame:
        ...


class StubCamera:
    """Fallback camera adapter used when hardware capture is not configured."""

    def __init__(
        self,
        *,
        source: str = "stub://rk3566-camera-0",
        width: int = 1280,
        height: int = 720,
        pixel_format: str = "rgb24",
    ) -> None:
        self._source = source
        self._width = width
        self._height = height
        self._pixel_format = pixel_format
        self._counter = count(1)

    def capture_latest_frame(self) -> CapturedFrame:
        seq = next(self._counter)
        return CapturedFrame(
            frame_id=f"frame-{seq:06d}",
            captured_at=utc_now_iso8601(),
            width=self._width,
            height=self._height,
            source=self._source,
            pixel_format=self._pixel_format,
        )


def create_camera(
    *,
    source: str | None,
    width: int,
    height: int,
    fps: int,
    pixel_format: str,
    backend: str = "auto",
    retry_count: int = 3,
    retry_delay_sec: float = 1.0,
) -> CameraProtocol:
    normalized_source = (source or "").strip()
    normalized_backend = (backend or "auto").strip().lower()

    if normalized_backend == "stub":
        return StubCamera(
            source=normalized_source or "stub://camera",
            width=width,
            height=height,
            pixel_format=pixel_format,
        )
    if not normalized_source:
        return StubCamera(
            source="stub://camera",
            width=width,
            height=height,
            pixel_format=pixel_format,
        )
    if normalized_source.startswith("stub://"):
        return StubCamera(
            source=normalized_source,
            width=width,
            height=height,
            pixel_format=pixel_format,
        )

    if normalized_source.startswith("v4l2://"):
        normalized_source = normalized_source.replace("v4l2://", "", 1)

    from edge_device.capture.v4l2_camera import V4L2Camera, V4L2CaptureConfig

    return V4L2Camera(
        config=V4L2CaptureConfig(
            source=normalized_source,
            width=width,
            height=height,
            fps=max(int(fps), 1),
            pixel_format=pixel_format,
            backend=normalized_backend,
            retry_count=max(int(retry_count), 1),
            retry_delay_sec=max(float(retry_delay_sec), 0.0),
        )
    )
