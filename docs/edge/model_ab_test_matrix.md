# Edge Model A/B Test Matrix (RK3566)

## 目标
- 在同一硬件、同一场景下对主检测候选做可复现对比。
- 给上线决策提供可量化证据，而不是只看单次 FPS。

## 先决条件（必须先满足）
- 已接入真实相机帧，不是 dummy 输入。
- 当前模型对应的后处理已对齐输出格式。
- 测试组统一使用同一摄像头、同一光照、同一采样窗口。

## 公共环境配置

```bash
export EDGE_ACTION=run-once
export EDGE_LOOP=0
export EDGE_INTERVAL_SEC=5
export EDGE_DEVICE_ID=rk3566-dev-01
export EDGE_CAMERA_ID=cam-entry-01
export EDGE_BACKEND_BASE_URL=http://100.92.134.46:8000

export EDGE_CAPTURE_SOURCE=/dev/video0
export EDGE_CAPTURE_BACKEND=v4l2
export EDGE_CAPTURE_RESOLUTION=1280x720
export EDGE_CAPTURE_FPS=30
export EDGE_CAPTURE_PIXEL_FORMAT=MJPG
export EDGE_CAPTURE_APPLY_V4L2_TUNING=1
export EDGE_CAPTURE_PARALLEL=1
export EDGE_CAPTURE_PARALLEL_WAIT_SEC=0.4
export EDGE_CAPTURE_RETRY_COUNT=3
export EDGE_CAPTURE_RETRY_DELAY_SEC=1.0

export EDGE_DETECTOR_BACKEND=rknn
export EDGE_DETECT_MIN_CONFIDENCE=0.35
export EDGE_RKNN_LABELS=person,package,car

export EDGE_SNAPSHOT_DIR=./data/edge_device/snapshots
export EDGE_CLIP_DIR=./data/edge_device/clips
export EDGE_SNAPSHOT_BUFFER_SIZE=32
export EDGE_CLIP_BUFFER_SIZE=16
export EDGE_PENDING_EVENT_DIR=./data/edge_device/pending_events
export EDGE_PENDING_EVENT_MAX=256
export EDGE_PENDING_FLUSH_BATCH=32
```

## 测试分组（第一轮）

| 组别 | 模型 | 输入 | 量化 | 角色 |
| --- | --- | --- | --- | --- |
| A1 | YOLOv5n | 416x416 | INT8 | 基线组 |
| A2 | YOLOv5n | 512x512 | INT8 | 小目标质量组 |
| B1 | YOLOv6n | 416x416 | INT8 | 轻量竞品组 |
| C1 | YOLOv8n | 416x416 | INT8 | 现代架构竞品组 |
| C2 | YOLOv8n | 512x512 | INT8 | 质量上限组 |

## 单组执行模板

```bash
# 以 A1 为例
export EDGE_DETECT_MODEL_VERSION=yolov5n-i8-416
export EDGE_RKNN_MODEL_VERSION=yolov5n-i8-416
export EDGE_RKNN_MODEL_PATH=./models/rknn/yolov5n_i8_416.rknn
export EDGE_RKNN_INPUT_SIZE=416x416

bash scripts/start_edge.sh run-once
```

## 循环测试模板（每组 30 次）

```bash
mkdir -p logs/abtest
for i in $(seq 1 30); do
  echo "===== RUN $i =====" | tee -a logs/abtest/${EDGE_RKNN_MODEL_VERSION}.log
  bash scripts/start_edge.sh run-once 2>&1 | tee -a logs/abtest/${EDGE_RKNN_MODEL_VERSION}.log
  sleep 1
done
```

## 指标与建议门槛

| 指标 | 建议门槛 | 用途 |
| --- | --- | --- |
| `infer_ms` | 越低越好 | 模型本体性能对比 |
| 端到端 FPS | >= 4（可用），>= 6（体验较好） | 实时体验判断 |
| CPU 平均占用 | < 180% | 留系统余量 |
| 内存峰值 | < 1.4GB | 2G 板卡安全边界 |
| 小目标召回 | >= 85% | 门口场景关键质量 |
| 误报率 | 越低越好 | 降低告警噪声 |
| 2 小时稳定性 | 无崩溃/无持续掉帧 | 常驻可行性 |

## 结果记录模板

| 组别 | infer_ms | e2e_fps | cpu_avg_pct | mem_peak_mb | recall_small | false_alarm | stability_2h | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 |  |  |  |  |  |  |  |  |
| A2 |  |  |  |  |  |  |  |  |
| B1 |  |  |  |  |  |  |  |  |
| C1 |  |  |  |  |  |  |  |  |
| C2 |  |  |  |  |  |  |  |  |
