from __future__ import annotations

import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from edge_device.capture.camera import CaptureError, CapturedFrame, LatestFramePrefetchCamera, StubCamera, create_camera
from edge_device.capture.v4l2_camera import V4L2Camera, V4L2CaptureConfig


class _FastFakeCamera:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._seq = 0

    def capture_latest_frame(self) -> CapturedFrame:
        self._seq += 1
        path = self._root / f"fake_{self._seq:06d}.jpg"
        path.write_bytes(b"\xff\xd8\xff\xd9")
        return CapturedFrame(
            frame_id=f"frame-{self._seq:06d}",
            captured_at="2026-03-15T00:00:00+08:00",
            width=1280,
            height=720,
            source="/dev/video0",
            pixel_format="MJPG",
            image_path=str(path),
        )


class EdgeCaptureTests(unittest.TestCase):
    def test_create_camera_without_source_returns_stub(self) -> None:
        camera = create_camera(
            source=None,
            width=640,
            height=480,
            fps=15,
            pixel_format="MJPG",
        )
        self.assertIsInstance(camera, StubCamera)
        frame = camera.capture_latest_frame()
        self.assertEqual(frame.width, 640)
        self.assertEqual(frame.height, 480)
        self.assertEqual(frame.pixel_format, "MJPG")

    def test_create_camera_with_stub_backend_forces_stub(self) -> None:
        camera = create_camera(
            source="/dev/video0",
            width=1280,
            height=720,
            fps=25,
            pixel_format="YUYV",
            backend="stub",
        )
        self.assertIsInstance(camera, StubCamera)

    def test_v4l2_camera_uses_configured_backend(self) -> None:
        called: list[list[str]] = []

        def fake_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            called.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        camera = V4L2Camera(
            config=V4L2CaptureConfig(
                source="/dev/video0",
                width=800,
                height=600,
                fps=20,
                pixel_format="MJPG",
                backend="v4l2",
                retry_count=1,
            ),
            runner=fake_runner,
            command_exists=lambda name: name == "v4l2-ctl",
            sleep_fn=lambda _: None,
        )
        frame = camera.capture_latest_frame()
        self.assertEqual(frame.source, "/dev/video0")
        self.assertEqual(frame.width, 800)
        self.assertEqual(frame.height, 600)
        self.assertEqual(frame.pixel_format, "MJPG")
        self.assertEqual(len(called), 2)
        self.assertIn("v4l2-ctl", called[0][0])
        self.assertIn("--device", called[0])
        self.assertIn("/dev/video0", called[0])
        self.assertTrue(any(arg.startswith("--stream-to=") for arg in called[1]))

    def test_v4l2_camera_retries_then_recovers(self) -> None:
        attempts = {"count": 0}

        def flaky_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            attempts["count"] += 1
            if attempts["count"] < 2:
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="temporary failure")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        camera = V4L2Camera(
            config=V4L2CaptureConfig(
                source="/dev/video0",
                backend="v4l2",
                retry_count=3,
                retry_delay_sec=0.0,
            ),
            runner=flaky_runner,
            command_exists=lambda name: name == "v4l2-ctl",
            sleep_fn=lambda _: None,
        )
        frame = camera.capture_latest_frame()
        self.assertEqual(frame.frame_id, "frame-000001")
        self.assertEqual(attempts["count"], 3)

    def test_v4l2_camera_raises_after_retry_exhausted(self) -> None:
        def always_fail(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="device unavailable")

        camera = V4L2Camera(
            config=V4L2CaptureConfig(
                source="/dev/video0",
                backend="v4l2",
                retry_count=2,
                retry_delay_sec=0.0,
            ),
            runner=always_fail,
            command_exists=lambda name: name == "v4l2-ctl",
            sleep_fn=lambda _: None,
        )
        with self.assertRaises(CaptureError) as context:
            camera.capture_latest_frame()
        self.assertIn("capture failed after retries", str(context.exception))
        self.assertIn("device unavailable", str(context.exception))

    def test_prefetch_camera_keeps_latest_frame_and_cleans_stale_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="edge_prefetch_") as tmp:
            root = Path(tmp)
            base_camera = _FastFakeCamera(root)
            prefetch = LatestFramePrefetchCamera(camera=base_camera, target_fps=120, wait_timeout_sec=0.2)
            try:
                time.sleep(0.06)
                frame = prefetch.capture_latest_frame()
                self.assertTrue(frame.frame_id.startswith("frame-"))
                self.assertTrue(Path(frame.image_path or "").exists())
                time.sleep(0.06)
            finally:
                prefetch.stop()

            # stale frame artifacts should be eagerly cleaned; only latest snapshots may remain.
            leftovers = list(root.glob("fake_*.jpg"))
            self.assertLessEqual(len(leftovers), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
