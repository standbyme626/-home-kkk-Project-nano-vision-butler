# EDGE_DEVICE

## 模块职责划分
- `edge_device/capture/camera.py`：相机采集接口、工厂与 `StubCamera` 回退策略。
- `edge_device/capture/v4l2_camera.py`：V4L2/GStreamer/FFmpeg 真实采集实现（带重试与错误可观测）。
- `edge_device/inference/detector.py`：轻量检测接口 `LightweightDetector`，后续接入 RKNN。
- `edge_device/tracking/tracker.py`：`track_id` 分配与轻量跟踪占位。
- `edge_device/compression/event_compressor.py`：把检测结果压缩为统一 event envelope，并输出后端可消费 payload。
- `edge_device/cache/ring_buffer.py`：快照和短视频片段 ring buffer。
- `edge_device/health/heartbeat.py`：heartbeat payload 组装。
- `edge_device/api/backend_client.py`：上报 `/device/ingest/event` 与 `/device/heartbeat`。
- `edge_device/api/server.py`：运行时入口（run-once/heartbeat/take-snapshot/get-recent-clip）。

## 运行方式
```bash
python3 -m edge_device.api.server run-once
python3 -m edge_device.api.server heartbeat
python3 -m edge_device.api.server take-snapshot
python3 -m edge_device.api.server get-recent-clip --duration-sec 6
```

环境变量（关键）：
- `EDGE_DEVICE_ID`：默认 `rk3566-dev-01`
- `EDGE_CAMERA_ID`：默认 `cam-entry-01`
- `EDGE_BACKEND_BASE_URL`：后端地址（例如 `http://192.168.1.5:8000`）
- `EDGE_CAPTURE_SOURCE`：采集源（例如 `/dev/video0`；空值则回退 stub）
- `EDGE_CAPTURE_RESOLUTION`：采集分辨率（例如 `1280x720`）
- `EDGE_CAPTURE_FPS`：采集帧率
- `EDGE_CAPTURE_PIXEL_FORMAT`：像素格式（例如 `MJPG` / `YUYV` / `NV12`）
- `EDGE_CAPTURE_BACKEND`：`auto | v4l2 | gstreamer | ffmpeg | stub`
- `EDGE_CAPTURE_RETRY_COUNT` / `EDGE_CAPTURE_RETRY_DELAY_SEC`：失败重试参数
- `EDGE_SNAPSHOT_DIR` / `EDGE_CLIP_DIR`：本地缓存目录

## Event Envelope 示例
```json
{
  "schema": "vision_butler.edge.event_envelope.v1",
  "envelope_id": "env-3a6c4d70d5f8",
  "emitted_at": "2026-03-13T11:20:21.345Z",
  "device_id": "rk3566-dev-01",
  "camera_id": "cam-entry-01",
  "trace_id": "trace-edge-run-1",
  "payload": {
    "device_id": "rk3566-dev-01",
    "camera_id": "cam-entry-01",
    "observed_at": "2026-03-13T11:20:21.312Z",
    "event_type": "object_detected",
    "category": "event",
    "importance": 4,
    "summary": "object_detected: person (track=trk-00001, confidence=0.82, count=1)",
    "object_name": "person",
    "object_class": "person",
    "track_id": "trk-00001",
    "confidence": 0.82,
    "zone_id": "entry_door",
    "snapshot_uri": "file:///.../cam-entry-01_frame-000001.jpg",
    "clip_uri": null,
    "raw_detections": [
      {
        "object_name": "person",
        "object_class": "person",
        "confidence": 0.82,
        "bbox": [120, 90, 680, 710],
        "zone_id": "entry_door",
        "track_id": "trk-00001"
      }
    ],
    "trace_id": "trace-edge-run-1"
  }
}
```

## Heartbeat Payload 示例
```json
{
  "device_id": "rk3566-dev-01",
  "camera_id": "cam-entry-01",
  "status": "online",
  "last_seen": "2026-03-13T11:20:30.120Z",
  "firmware_version": "rk3566-stub-fw-0.1.0",
  "model_version": "stub-detector-v1",
  "ip_addr": null,
  "temperature": null,
  "cpu_load": 0.24,
  "npu_load": 0.0,
  "free_mem_mb": 812,
  "camera_fps": 10,
  "trace_id": "trace-edge-hb-1"
}
```

## 后续替换点（真实硬件接入）
- 采集层已支持 `V4L2/GStreamer/FFmpeg`；通过 `EDGE_CAPTURE_*` 参数切换与调优。
- `LightweightDetector.detect`：替换为 RKNN 推理调用。
- `LightweightTracker.assign_tracks`：替换为真实多目标跟踪器（如 ByteTrack 简化版）。
- `_store_snapshot/_assemble_clip`：替换为真实 JPEG 编码和短视频封装流程。
