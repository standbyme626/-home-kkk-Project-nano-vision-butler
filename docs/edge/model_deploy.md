# RKNN Model Deploy (T13F)

## 目标
- 在 RK3566 板端接入 RKNN 主检测模型。
- 让 runtime 输出真实 `bbox/class/confidence`。
- 推理失败时自动降级到轻量检测器并记录错误。

## 代码入口
- 检测工厂：`edge_device/inference/detector.py`
- RKNN 检测器：`edge_device/inference/rknn_detector.py`
- Runtime 注入点：`edge_device/api/server.py`

## 环境变量
- `EDGE_DETECTOR_BACKEND`：`auto | rknn | lightweight`（默认 `auto`）。
- `EDGE_DETECT_MIN_CONFIDENCE`：最小置信度阈值（默认 `0.35`）。
- `EDGE_RKNN_MODEL_PATH`：RKNN 模型路径（默认 `./models/rknn/main_detector_n_int8.rknn`）。
- `EDGE_RKNN_MODEL_VERSION`：模型版本号（默认取模型文件名 stem）。
- `EDGE_RKNN_INPUT_SIZE`：推理输入大小（例如 `640x640`）。
- `EDGE_RKNN_LABELS`：类别列表（逗号分隔，默认 `person,package,car`）。

## 导出流程
1. 准备 ONNX 模型。
2. 在 PC 端执行：
```bash
./scripts/rknn/export_to_rknn.sh ./models/onnx/main_detector_n.onnx ./models/rknn/main_detector_n_int8.rknn rk3566
```
3. 将 `.rknn` 文件同步到板端 `EDGE_RKNN_MODEL_PATH`。

## 板端基准
```bash
EDGE_DETECTOR_BACKEND=rknn \
./scripts/rknn/run_infer_benchmark.sh ./models/rknn/main_detector_n_int8.rknn 30
```

输出包含：
- `avg_latency_ms`
- `approx_fps`
- 每轮 `model_version` 和 `detector_error`

## 降级策略
- RKNN 模型缺失、运行时初始化失败、推理解码失败时：
  - 自动降级到 `LightweightDetector`
  - `run_once` 返回 `data.detector_error`
  - event payload 的 `compress_reason` 标记为 `event_compressor_v1|detector_degraded`

## 验证清单
- `run-once` 返回包含 `model_version`。
- `event payload` 中包含合法 `objects[].bbox/object_class/confidence`。
- 在故障场景中 `detector_error` 可观测且 pipeline 不中断。
