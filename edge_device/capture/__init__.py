"""Camera capture interfaces for edge runtime."""

from .camera import CaptureError, CapturedFrame, CameraProtocol, StubCamera, create_camera
from .v4l2_camera import V4L2Camera, V4L2CaptureConfig

__all__ = [
    "CameraProtocol",
    "CaptureError",
    "CapturedFrame",
    "StubCamera",
    "create_camera",
    "V4L2Camera",
    "V4L2CaptureConfig",
]
