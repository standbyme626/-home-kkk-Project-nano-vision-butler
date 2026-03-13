# Edge Protocol Freeze (T13B)

本文件冻结 RK3566 edge 与 backend 的协议字段，作为 T13B 的正式基线。

## 1) 版本约定

- event ingest: `schema_version = edge.event.v1`
- heartbeat: `schema_version = edge.heartbeat.v1`
- command response: `schema_version = edge.command_response.v1`

## 2) Event (`POST /device/ingest/event`)

关键字段（v1）：

- `schema_version`
- `event_id`
- `device_id`
- `camera_id`
- `seq_no`
- `captured_at`
- `sent_at`
- `event_type`
- `objects[]`
- `snapshot_uri` (optional)
- `clip_uri` (optional)
- `model_version` (optional)
- `compress_reason` (optional)
- `signature` (optional)

兼容字段（当前后端仍消费）：

- `observed_at`
- `summary`
- `importance`
- `object_name`
- `object_class`
- `track_id`
- `confidence`
- `zone_id`
- `raw_detections`
- `trace_id`

## 3) Heartbeat (`POST /device/heartbeat`)

关键字段（v1）：

- `schema_version`
- `device_id`
- `online`
- `sent_at`
- `last_capture_ok`
- `last_upload_ok`

兼容字段：

- `camera_id`
- `status`
- `last_seen`
- `temperature`
- `cpu_load`
- `npu_load`
- `free_mem_mb`
- `camera_fps`
- `firmware_version`
- `model_version`
- `ip_addr`
- `trace_id`

## 4) Command Response (`edge runtime local contract`)

关键字段（v1）：

- `schema_version`
- `type` (`command_response`)
- `ok`
- `summary`
- `data.command`
- `data.command_id`
- `data.device_id`
- `data.camera_id`
- `meta.received_at`

命令类型：

- `take_snapshot`
- `get_recent_clip`

## 5) 兼容性与校验规则

- 后端继续兼容无 `schema_version` 的旧 payload（便于平滑迁移）。
- 当 payload 带 `schema_version` 时，后端执行版本与关键字段校验，不通过则返回 `400`.
- 冻结期内字段只增不删；变更必须新开版本号（`*.v2`）。
