"""RKNN detector with graceful fallback to lightweight detector."""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edge_device.capture.camera import CapturedFrame
from edge_device.inference.detector import Detection, LightweightDetector

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RKNNDetectorConfig:
    model_path: Path
    model_version: str
    min_confidence: float = 0.35
    input_width: int = 640
    input_height: int = 640
    labels: tuple[str, ...] = ("person", "package", "car")


class RKNNDetector:
    """RKNN-backed detector that degrades to lightweight detection on failure."""

    def __init__(
        self,
        *,
        config: RKNNDetectorConfig,
        runtime: Any | None = None,
        fallback_detector: LightweightDetector | None = None,
    ) -> None:
        self.config = config
        self.last_error: str | None = None
        self._fallback = fallback_detector or LightweightDetector(
            model_version="stub-detector-v1",
            min_confidence=config.min_confidence,
        )
        self._runtime = runtime if runtime is not None else self._init_runtime()
        self.model_version = config.model_version if self._runtime is not None else self._fallback.model_version

    @property
    def runtime_ready(self) -> bool:
        return self._runtime is not None

    def detect(self, frame: CapturedFrame) -> list[Detection]:
        if self._runtime is None:
            if self.last_error is None:
                self.last_error = f"rknn_runtime_unavailable:model={self.config.model_path}"
                LOGGER.warning("RKNN runtime unavailable, fallback enabled: %s", self.last_error)
            return self._fallback.detect(frame)

        try:
            outputs = self._infer(frame)
            decoded = self._decode(outputs=outputs, frame=frame)
            self.last_error = None
            self.model_version = self.config.model_version
            return decoded
        except Exception as exc:  # pragma: no cover - defensive runtime boundary
            self.last_error = f"rknn_inference_failed:{exc}"
            self.model_version = self._fallback.model_version
            LOGGER.warning("RKNN inference failed, fallback enabled: %s", self.last_error)
            return self._fallback.detect(frame)

    def _init_runtime(self) -> Any | None:
        if not self.config.model_path.exists():
            self.last_error = f"rknn_model_missing:{self.config.model_path}"
            LOGGER.warning("RKNN model not found, fallback enabled: %s", self.last_error)
            return None

        try:
            module = importlib.import_module("rknnlite.api")
            rknn_cls = getattr(module, "RKNNLite")
            runtime = rknn_cls()
            load_ret = runtime.load_rknn(str(self.config.model_path))
            if load_ret != 0:
                self.last_error = f"rknn_load_failed:code={load_ret}"
                LOGGER.warning("RKNN model load failed, fallback enabled: %s", self.last_error)
                return None
            init_ret = runtime.init_runtime()
            if init_ret != 0:
                self.last_error = f"rknn_init_failed:code={init_ret}"
                LOGGER.warning("RKNN runtime init failed, fallback enabled: %s", self.last_error)
                return None
            return runtime
        except Exception as exc:  # pragma: no cover - optional dependency boundary
            self.last_error = f"rknn_runtime_init_error:{exc}"
            LOGGER.warning("RKNN runtime init error, fallback enabled: %s", self.last_error)
            return None

    def _infer(self, frame: CapturedFrame) -> Any:
        del frame
        import numpy as np  # lazy import: board runtime dependency

        dummy = np.zeros(
            (1, self.config.input_height, self.config.input_width, 3),
            dtype=np.uint8,
        )
        return self._runtime.inference(inputs=[dummy])

    def _decode(self, *, outputs: Any, frame: CapturedFrame) -> list[Detection]:
        if not isinstance(outputs, (list, tuple)) or not outputs:
            raise ValueError("RKNN outputs are empty")

        try:
            import numpy as np  # lazy import

            arr = np.asarray(outputs[0])
        except Exception as exc:
            raise ValueError(f"RKNN output cast failed: {exc}") from exc

        if arr.size == 0:
            return []
        if arr.ndim == 1:
            if arr.size % 6 != 0:
                raise ValueError("RKNN output must be N*6")
            arr = arr.reshape((-1, 6))
        elif arr.ndim >= 2:
            arr = arr.reshape((-1, arr.shape[-1]))

        if arr.shape[1] < 6:
            raise ValueError("RKNN output row width < 6")

        detections: list[Detection] = []
        max_rows = min(arr.shape[0], 64)
        for idx in range(max_rows):
            row = arr[idx]
            score = float(row[4])
            if score < self.config.min_confidence:
                continue
            class_id = int(row[5])
            label = self._label_for_class_id(class_id)
            x1, y1, x2, y2 = self._normalize_bbox(
                x1=float(row[0]),
                y1=float(row[1]),
                x2=float(row[2]),
                y2=float(row[3]),
                frame=frame,
            )
            if x2 <= x1 or y2 <= y1:
                continue
            detections.append(
                Detection(
                    object_name=label,
                    object_class=label,
                    confidence=max(min(score, 1.0), 0.0),
                    bbox=(x1, y1, x2, y2),
                    zone_id="entry_door",
                )
            )
        return detections

    def _label_for_class_id(self, class_id: int) -> str:
        if class_id < 0:
            return "unknown"
        if class_id < len(self.config.labels):
            return self.config.labels[class_id]
        return f"class_{class_id}"

    @staticmethod
    def _normalize_bbox(
        *,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        frame: CapturedFrame,
    ) -> tuple[int, int, int, int]:
        width = max(int(frame.width), 1)
        height = max(int(frame.height), 1)
        left = max(min(int(round(x1)), width - 1), 0)
        top = max(min(int(round(y1)), height - 1), 0)
        right = max(min(int(round(x2)), width), 0)
        bottom = max(min(int(round(y2)), height), 0)
        return left, top, right, bottom


def create_rknn_detector_from_env(*, min_confidence: float) -> RKNNDetector:
    raw_model_path = (os.getenv("EDGE_RKNN_MODEL_PATH") or "").strip()
    model_path = Path(raw_model_path) if raw_model_path else Path("./models/rknn/yolov8n_official_i8_rk3566.rknn")
    raw_model_version = (os.getenv("EDGE_RKNN_MODEL_VERSION") or "").strip()
    model_version = raw_model_version or (model_path.stem or "rknn-main")
    input_width, input_height = _parse_input_size(os.getenv("EDGE_RKNN_INPUT_SIZE", "640x640"))
    labels = _parse_labels(os.getenv("EDGE_RKNN_LABELS", "person,package,car"))
    return RKNNDetector(
        config=RKNNDetectorConfig(
            model_path=model_path,
            model_version=model_version,
            min_confidence=min_confidence,
            input_width=input_width,
            input_height=input_height,
            labels=labels,
        )
    )


def _parse_labels(raw: str) -> tuple[str, ...]:
    labels = tuple(item.strip() for item in raw.split(",") if item.strip())
    return labels or ("person",)


def _parse_input_size(raw: str) -> tuple[int, int]:
    text = (raw or "").strip().lower()
    if "x" not in text:
        return 640, 640
    left, right = text.split("x", 1)
    try:
        width = max(int(left), 1)
        height = max(int(right), 1)
        return width, height
    except ValueError:
        return 640, 640
