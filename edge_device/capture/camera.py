"""Capture layer for RK3566 edge runtime."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Callable, Protocol


def utc_now_iso8601() -> str:
    mode = _time_mode()
    if mode == "local":
        return datetime.now().astimezone().isoformat(timespec="milliseconds")
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def compact_now_for_filename() -> str:
    mode = _time_mode()
    if mode == "local":
        return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f")
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _time_mode() -> str:
    raw = (os.getenv("VISION_BUTLER_TIME_MODE", "utc") or "utc").strip().lower()
    if raw in {"local", "asia/shanghai", "cst"}:
        return "local"
    return "utc"


@dataclass(frozen=True)
class CapturedFrame:
    frame_id: str
    captured_at: str
    width: int
    height: int
    source: str
    pixel_format: str = "rgb24"
    image_path: str | None = None


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


class LatestFramePrefetchCamera:
    """Continuously prefetch latest frame so capture and inference can overlap."""

    def __init__(
        self,
        *,
        camera: CameraProtocol,
        target_fps: int,
        wait_timeout_sec: float = 0.4,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._camera = camera
        self._target_interval_sec = 1.0 / max(int(target_fps), 1)
        self._wait_timeout_sec = max(float(wait_timeout_sec), 0.05)
        self._sleep = sleep_fn or time.sleep

        self._capture_lock = threading.Lock()
        self._state_cond = threading.Condition()
        self._latest_frame: CapturedFrame | None = None
        self._last_error: Exception | None = None
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._prefetch_loop,
            name="edge-capture-prefetch",
            daemon=True,
        )
        self._thread.start()

    def capture_latest_frame(self) -> CapturedFrame:
        deadline = time.monotonic() + self._wait_timeout_sec
        with self._state_cond:
            while self._latest_frame is None and not self._stop_event.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._state_cond.wait(timeout=remaining)
            if self._latest_frame is not None:
                frame = self._latest_frame
                self._latest_frame = None
                return frame
            last_error = self._last_error

        if last_error is not None:
            raise CaptureError(f"prefetch capture failed: {last_error}")

        # Fallback to direct capture for startup race or temporary prefetch miss.
        with self._capture_lock:
            return self._camera.capture_latest_frame()

    def stop(self) -> None:
        self._stop_event.set()
        with self._state_cond:
            self._state_cond.notify_all()
        self._thread.join(timeout=0.5)
        with self._state_cond:
            stale = self._latest_frame
            self._latest_frame = None
        self._cleanup_frame_artifacts(stale)

    def _prefetch_loop(self) -> None:
        while not self._stop_event.is_set():
            loop_start = time.monotonic()
            try:
                with self._capture_lock:
                    frame = self._camera.capture_latest_frame()
                with self._state_cond:
                    stale = self._latest_frame
                    self._latest_frame = frame
                    self._last_error = None
                    self._state_cond.notify_all()
                self._cleanup_frame_artifacts(stale)
            except Exception as exc:  # pragma: no cover - defensive background boundary
                with self._state_cond:
                    self._last_error = exc
                    self._state_cond.notify_all()

            elapsed = time.monotonic() - loop_start
            remaining = self._target_interval_sec - elapsed
            if remaining > 0:
                self._sleep(remaining)

    @staticmethod
    def _cleanup_frame_artifacts(frame: CapturedFrame | None) -> None:
        if frame is None or not frame.image_path:
            return
        path = Path(frame.image_path)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return


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
