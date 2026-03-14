# Edge 轻前端重后端改造方案（第一阶段）

## 1. 目标

在保持现有协议兼容的前提下，把 RK3566 从“重推理执行端”收敛成“实时感知前哨”，把 OCR 等重分析任务迁移到后端执行。

第一阶段只做三件事：

1. Edge 事件上报增加 `analysis_requests` 提示字段。
2. Backend 在 `ingest_event` 路径按提示触发 OCR（可开关）。
3. 保持原有 `edge.event.v1` 兼容，不破坏已有命令链路和状态链路。

## 2. 分层职责

`RK3566（Edge）`：

1. 采集、轻量检测、轻量跟踪、事件压缩。
2. 在满足条件时仅发出“后端分析请求提示”（例如 OCR）。
3. 不承担长期状态真相层和重分析执行。

`Backend`：

1. 接收事件并落 observation/event。
2. 根据 `analysis_requests` 执行 OCR。
3. 写入 `ocr_results`、更新 observation OCR 文本、记录审计日志。

## 3. 模型部署建议

1. 轻模型部署在 RK3566（RKNN）：目标是稳定实时感知与低延迟上报。
2. 重模型部署在后端主机：OCR 与多模态理解在后端执行，便于扩容与迭代。

## 4. 压力迁移预期

1. Edge 压力下降：避免每帧重分析，优先保障实时性与稳定性。
2. Backend 压力上升：OCR 请求转移到后端，但可以通过并发与资源扩展处理。
3. 网络压力可控：按事件触发分析，不是每帧上传全量重任务。

## 5. 第一阶段改造点

1. `edge_device/compression/event_compressor.py`
   - 增加 `analysis_profile`、`analysis_required`、`analysis_requests`。
   - 默认仅对高置信度、高重要度的 `package/document/label/screen` 发起 OCR 请求提示。
2. `src/services/perception_service.py`
   - 在 `ingest_event` 后增加后端分析触发。
   - 支持 `ocr_quick_read`、`ocr_extract_fields` 两类请求。
   - 分析结果写入审计日志 `perception_backend_analysis`。
3. `src/dependencies.py`
   - 在 Device 服务依赖中注入 `OCRService` 给 `PerceptionService`。
4. `schemas/edge_event_envelope.schema.json` 与 `docs/edge/protocol.md`
   - 扩展协议文档与 schema，确保字段合法。
5. `config/policies.yaml`
   - 新增 `edge_analysis.enable_backend_analysis` 开关。

## 6. 关键配置

`Edge` 环境变量（`scripts/start_edge.sh` 已接入）：

1. `EDGE_ANALYSIS_ENABLE`
2. `EDGE_ANALYSIS_OCR_ENABLE`
3. `EDGE_ANALYSIS_MIN_IMPORTANCE_OCR`
4. `EDGE_ANALYSIS_PROFILE`

`Backend` 配置：

1. `config/policies.yaml -> edge_analysis.enable_backend_analysis`

## 7. 验收标准（第一阶段）

1. Edge 事件可携带 `analysis_requests`，并通过 schema 校验。
2. Backend 接收带请求的事件后可自动触发 OCR。
3. `ocr_results` 有落库记录。
4. 审计日志包含 `perception_backend_analysis`。
5. 现有事件/心跳/命令回归测试不退化。

## 8. 风险与回退

1. 风险：后端 OCR 负载升高导致峰值波动。
2. 控制：先按高重要度触发，避免全量事件触发。
3. 回退：关闭 `edge_analysis.enable_backend_analysis` 即可停止后端自动分析。
