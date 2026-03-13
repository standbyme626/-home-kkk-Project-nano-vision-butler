"""Heartbeat payload builder for edge runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

HEARTBEAT_SCHEMA_VERSION = "edge.heartbeat.v1"


def utc_now_iso8601() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class RuntimeMetrics:
    status: str = "online"
    ip_addr: str | None = None
    temperature: float | None = None
    cpu_load: float | None = None
    npu_load: float | None = None
    free_mem_mb: int | None = None
    camera_fps: int | None = None
    last_capture_ok: bool = True
    last_upload_ok: bool = True


class HeartbeatBuilder:
    """Builds /device/heartbeat payloads from runtime metrics."""

    def __init__(
        self,
        *,
        firmware_version: str = "rk3566-stub-fw-0.1.0",
        model_version: str = "stub-detector-v1",
        metrics_provider: Callable[[], RuntimeMetrics] | None = None,
    ) -> None:
        self._firmware_version = firmware_version
        self._model_version = model_version
        self._metrics_provider = metrics_provider or default_metrics_provider

    def build(
        self,
        *,
        device_id: str,
        camera_id: str,
        trace_id: str | None = None,
        last_seen: str | None = None,
    ) -> dict[str, object]:
        metrics = self._metrics_provider()
        payload: dict[str, object] = {
            "schema_version": HEARTBEAT_SCHEMA_VERSION,
            "device_id": device_id,
            "camera_id": camera_id,
            "status": metrics.status,
            "online": metrics.status != "offline",
            "sent_at": utc_now_iso8601(),
            "last_seen": last_seen or utc_now_iso8601(),
            "firmware_version": self._firmware_version,
            "model_version": self._model_version,
            "ip_addr": metrics.ip_addr,
            "temperature": metrics.temperature,
            "cpu_load": metrics.cpu_load,
            "npu_load": metrics.npu_load,
            "free_mem_mb": metrics.free_mem_mb,
            "camera_fps": metrics.camera_fps,
            "last_capture_ok": bool(metrics.last_capture_ok),
            "last_upload_ok": bool(metrics.last_upload_ok),
        }
        if trace_id:
            payload["trace_id"] = trace_id
        return payload


def _read_mem_available_mb() -> int | None:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return None
    for line in meminfo.read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    kb = int(parts[1])
                    return max(kb // 1024, 0)
                except ValueError:
                    return None
    return None


def default_metrics_provider() -> RuntimeMetrics:
    cpu_load: float | None = None
    try:
        load1, _, _ = os.getloadavg()
        cpu_load = round(max(min(load1 / 4.0, 1.0), 0.0), 3)
    except OSError:
        cpu_load = None

    return RuntimeMetrics(
        status="online",
        cpu_load=cpu_load,
        npu_load=0.0,
        free_mem_mb=_read_mem_available_mb(),
        camera_fps=10,
    )
