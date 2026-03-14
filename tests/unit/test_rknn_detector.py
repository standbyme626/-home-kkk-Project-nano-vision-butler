from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from edge_device.capture.camera import StubCamera
from edge_device.inference.detector import LightweightDetector, create_detector_from_env
from edge_device.inference.rknn_detector import (
    RKNNDetector,
    RKNNDetectorConfig,
    create_rknn_detector_from_env,
)


class _FakeRuntime:
    def __init__(self, outputs):
        self._outputs = outputs

    def inference(self, inputs):  # noqa: ANN001
        del inputs
        return self._outputs


class _FailRuntime:
    def inference(self, inputs):  # noqa: ANN001
        del inputs
        raise RuntimeError("infer failed")


class RKNNDetectorTests(unittest.TestCase):
    def test_factory_rknn_backend_degrades_when_model_missing(self) -> None:
        old_backend = os.environ.get("EDGE_DETECTOR_BACKEND")
        old_path = os.environ.get("EDGE_RKNN_MODEL_PATH")
        try:
            os.environ["EDGE_DETECTOR_BACKEND"] = "rknn"
            os.environ["EDGE_RKNN_MODEL_PATH"] = "/tmp/not_found_model_for_test.rknn"
            detector = create_detector_from_env()
        finally:
            if old_backend is None:
                os.environ.pop("EDGE_DETECTOR_BACKEND", None)
            else:
                os.environ["EDGE_DETECTOR_BACKEND"] = old_backend
            if old_path is None:
                os.environ.pop("EDGE_RKNN_MODEL_PATH", None)
            else:
                os.environ["EDGE_RKNN_MODEL_PATH"] = old_path

        frame = StubCamera(width=640, height=360).capture_latest_frame()
        detections = detector.detect(frame)
        self.assertTrue(detections)
        self.assertEqual(detector.model_version, "stub-detector-v1")
        self.assertIsNotNone(detector.last_error)

    def test_decode_fake_runtime_output_to_detection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vision_butler_rknn_unit_") as tmp:
            model_path = Path(tmp) / "main_detector.rknn"
            model_path.write_text("dummy", encoding="utf-8")
            detector = RKNNDetector(
                config=RKNNDetectorConfig(
                    model_path=model_path,
                    model_version="rknn-main-v1",
                    min_confidence=0.3,
                    labels=("person", "package"),
                ),
                runtime=_FakeRuntime(outputs=[[[120, 100, 420, 300, 0.92, 0]]]),
            )

            frame = StubCamera(width=640, height=360).capture_latest_frame()
            detections = detector.detect(frame)
            self.assertEqual(len(detections), 1)
            self.assertEqual(detections[0].object_class, "person")
            self.assertGreater(detections[0].confidence, 0.9)
            self.assertEqual(detector.model_version, "rknn-main-v1")
            self.assertIsNone(detector.last_error)

    def test_inference_failure_falls_back_and_records_error(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vision_butler_rknn_unit_") as tmp:
            model_path = Path(tmp) / "main_detector.rknn"
            model_path.write_text("dummy", encoding="utf-8")
            fallback = LightweightDetector(model_version="fallback-detector-v1")
            detector = RKNNDetector(
                config=RKNNDetectorConfig(model_path=model_path, model_version="rknn-main-v1"),
                runtime=_FailRuntime(),
                fallback_detector=fallback,
            )

            frame = StubCamera(width=640, height=360).capture_latest_frame()
            detections = detector.detect(frame)
            self.assertTrue(detections)
            self.assertEqual(detector.model_version, "fallback-detector-v1")
            self.assertIn("rknn_inference_failed", detector.last_error or "")

    def test_empty_model_path_env_falls_back_to_default_path(self) -> None:
        old_backend = os.environ.get("EDGE_DETECTOR_BACKEND")
        old_model_path = os.environ.get("EDGE_RKNN_MODEL_PATH")
        try:
            os.environ["EDGE_DETECTOR_BACKEND"] = "rknn"
            os.environ["EDGE_RKNN_MODEL_PATH"] = ""
            detector = create_rknn_detector_from_env(min_confidence=0.35)
        finally:
            if old_backend is None:
                os.environ.pop("EDGE_DETECTOR_BACKEND", None)
            else:
                os.environ["EDGE_DETECTOR_BACKEND"] = old_backend
            if old_model_path is None:
                os.environ.pop("EDGE_RKNN_MODEL_PATH", None)
            else:
                os.environ["EDGE_RKNN_MODEL_PATH"] = old_model_path

        self.assertEqual(detector.config.model_path, Path("./models/rknn/main_detector_n_int8.rknn"))

    def test_empty_model_version_env_falls_back_to_model_stem(self) -> None:
        old_model_path = os.environ.get("EDGE_RKNN_MODEL_PATH")
        old_model_version = os.environ.get("EDGE_RKNN_MODEL_VERSION")
        try:
            os.environ["EDGE_RKNN_MODEL_PATH"] = "./models/rknn/main_detector_n_int8.rknn"
            os.environ["EDGE_RKNN_MODEL_VERSION"] = ""
            detector = create_rknn_detector_from_env(min_confidence=0.35)
        finally:
            if old_model_path is None:
                os.environ.pop("EDGE_RKNN_MODEL_PATH", None)
            else:
                os.environ["EDGE_RKNN_MODEL_PATH"] = old_model_path
            if old_model_version is None:
                os.environ.pop("EDGE_RKNN_MODEL_VERSION", None)
            else:
                os.environ["EDGE_RKNN_MODEL_VERSION"] = old_model_version

        self.assertEqual(detector.config.model_version, "main_detector_n_int8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
