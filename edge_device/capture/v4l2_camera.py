"""Real camera capture adapter for V4L2/GStreamer/FFmpeg pipelines."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from itertools import count
from typing import Callable

from edge_device.capture.camera import CaptureError, CapturedFrame, utc_now_iso8601

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class V4L2CaptureConfig:
    source: str
    width: int = 1280
    height: int = 720
    fps: int = 25
    pixel_format: str = "MJPG"
    backend: str = "auto"
    retry_count: int = 3
    retry_delay_sec: float = 1.0
    command_timeout_sec: float = 8.0


class V4L2Camera:
    """Capture adapter that probes and pulls a frame via system video tools."""

    def __init__(
        self,
        *,
        config: V4L2CaptureConfig,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        command_exists: Callable[[str], bool] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._config = config
        self._counter = count(1)
        self._run = runner or subprocess.run
        self._command_exists = command_exists or (lambda command: shutil.which(command) is not None)
        self._sleep = sleep_fn or time.sleep

    def capture_latest_frame(self) -> CapturedFrame:
        errors: list[str] = []
        for attempt in range(1, self._config.retry_count + 1):
            try:
                backend_name = self._capture_once()
                seq = next(self._counter)
                return CapturedFrame(
                    frame_id=f"frame-{seq:06d}",
                    captured_at=utc_now_iso8601(),
                    width=self._config.width,
                    height=self._config.height,
                    source=self._config.source,
                    pixel_format=self._config.pixel_format,
                )
            except CaptureError as exc:
                detail = f"attempt={attempt}/{self._config.retry_count} backend={self._config.backend} error={exc}"
                errors.append(detail)
                _LOG.warning("camera capture failed: %s", detail)
                if attempt < self._config.retry_count and self._config.retry_delay_sec > 0:
                    self._sleep(self._config.retry_delay_sec)

        joined = "; ".join(errors) if errors else "unknown capture error"
        raise CaptureError(f"capture failed after retries: {joined}")

    def _capture_once(self) -> str:
        backends = self._resolve_backends()
        last_error: str | None = None
        for backend in backends:
            try:
                if backend == "v4l2":
                    self._capture_via_v4l2ctl()
                elif backend == "gstreamer":
                    self._capture_via_gstreamer()
                elif backend == "ffmpeg":
                    self._capture_via_ffmpeg()
                else:
                    raise CaptureError(f"unsupported backend: {backend}")
                _LOG.info(
                    "camera capture ok: backend=%s source=%s resolution=%sx%s fps=%s pixel_format=%s",
                    backend,
                    self._config.source,
                    self._config.width,
                    self._config.height,
                    self._config.fps,
                    self._config.pixel_format,
                )
                return backend
            except CaptureError as exc:
                last_error = f"{backend}: {exc}"
                _LOG.warning("backend capture failed: %s", last_error)
        raise CaptureError(last_error or "no backend available")

    def _resolve_backends(self) -> list[str]:
        requested = (self._config.backend or "auto").strip().lower()
        if requested and requested != "auto":
            return [self._normalize_backend_name(requested)]
        return ["v4l2", "gstreamer", "ffmpeg"]

    @staticmethod
    def _normalize_backend_name(value: str) -> str:
        aliases = {
            "v4l2-ctl": "v4l2",
            "v4l2ctl": "v4l2",
            "gst": "gstreamer",
            "gst-launch": "gstreamer",
            "gst-launch-1.0": "gstreamer",
        }
        return aliases.get(value, value)

    def _capture_via_v4l2ctl(self) -> None:
        if not self._command_exists("v4l2-ctl"):
            raise CaptureError("v4l2-ctl not found")
        fmt = (
            f"width={self._config.width},height={self._config.height},"
            f"pixelformat={self._config.pixel_format}"
        )
        cmd = [
            "v4l2-ctl",
            "--device",
            self._config.source,
            f"--set-fmt-video={fmt}",
            "--stream-mmap=3",
            "--stream-count=1",
            "--stream-to=/dev/null",
        ]
        self._run_command(cmd)

    def _capture_via_gstreamer(self) -> None:
        if not self._command_exists("gst-launch-1.0"):
            raise CaptureError("gst-launch-1.0 not found")
        caps = (
            "video/x-raw,"
            f"width={self._config.width},height={self._config.height},"
            f"framerate={self._config.fps}/1,format={self._config.pixel_format}"
        )
        cmd = [
            "gst-launch-1.0",
            "-q",
            "-e",
            "v4l2src",
            f"device={self._config.source}",
            "num-buffers=1",
            "!",
            caps,
            "!",
            "fakesink",
            "sync=false",
        ]
        self._run_command(cmd)

    def _capture_via_ffmpeg(self) -> None:
        if not self._command_exists("ffmpeg"):
            raise CaptureError("ffmpeg not found")
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-framerate",
            str(self._config.fps),
            "-video_size",
            f"{self._config.width}x{self._config.height}",
            "-input_format",
            self._config.pixel_format,
            "-i",
            self._config.source,
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ]
        self._run_command(cmd)

    def _run_command(self, command: list[str]) -> None:
        try:
            proc = self._run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._config.command_timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            raise CaptureError(f"timeout after {self._config.command_timeout_sec}s: {' '.join(command)}") from exc
        except OSError as exc:
            raise CaptureError(f"os error: {exc}") from exc

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            detail = stderr or stdout or f"exit_code={proc.returncode}"
            raise CaptureError(detail)
