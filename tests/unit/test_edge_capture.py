from __future__ import annotations

import subprocess
import unittest

from edge_device.capture.camera import CaptureError, StubCamera, create_camera
from edge_device.capture.v4l2_camera import V4L2Camera, V4L2CaptureConfig


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
        self.assertEqual(len(called), 1)
        self.assertIn("v4l2-ctl", called[0][0])
        self.assertIn("--device", called[0])
        self.assertIn("/dev/video0", called[0])

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
        self.assertEqual(attempts["count"], 2)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
