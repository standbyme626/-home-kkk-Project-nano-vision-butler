# Progress Checklist

说明：每项完成后打勾，并在备注中记录验收证据（命令输出、截图、测试名）。

## A. Prompt 执行清单（主序列 1-15 + 补充 02B/11B/12A-12I）
- [x] Prompt01 初始化仓库与文档骨架
- [x] Prompt02 实现数据库与迁移系统
- [x] Prompt02B 实现配置系统（补充）
- [x] Prompt03 实现 Schema 与 Repository 层
- [x] Prompt04 实现 FastAPI 后端骨架
- [x] Prompt05 实现 memory/perception 服务
- [x] Prompt06 实现 state/policy 服务
- [x] Prompt07 实现 device 服务与媒体链路
- [x] Prompt07-Hotfix 摄像头可用性修复（SQLite 线程 + runtime 流地址 + edge 默认后端，2026-03-14 本地复验通过）
- [x] Prompt08 实现 OCR 双通道
- [x] Prompt09 实现 MCP Server 层
- [x] Prompt10 实现 Skill 层
- [x] Prompt11 nanobot 集成与正式宿主配置
- [x] Prompt11-Hotfix 模型切换至 qwen3.5-35b-a3b 并补充模型/密钥更换说明
- [x] Prompt11B Telegram 正式交互链路（补充）
- [x] Prompt11B-Hotfix Telegram 重复消费防护（单 token 单实例）
- [x] Prompt11B-Hotfix MCP kwargs 参数兼容（避免 camera_id/device_id 丢失）
- [x] Prompt12 RK3566 前端最小正式实现
- [x] Prompt12A RK3566 板级 bring-up 与基线测量（新增 baseline 脚本与报告模板，2026-03-14 自检通过）
- [x] Prompt12B 前端协议冻结（event/heartbeat/command）（新增 protocol 文档、三份 schema、入站 schema_version 校验，2026-03-14 测试通过）
- [x] Prompt12C 真实采集层替换（V4L2/GStreamer）（新增真实采集实现与重试机制，2026-03-14 单测通过）
- [x] Prompt12D 真实 Snapshot 落地（JPEG）（_store_snapshot 真实 JPEG + 回传落库测试，2026-03-14 通过）
- [x] Prompt12D-Hotfix 快照黑屏修复（`CapturedFrame.image_path` + V4L2 MJPG 直出 + 实机 `take-snapshot/run-once` 复测，2026-03-14）
- [x] Prompt12E 命令闭环最小打通（替换后端 StubEdgeDeviceAdapter）（新增 edge_command_client + 命令桥接集成测试，2026-03-14 通过）
- [x] Prompt12F RKNN 检测模型部署（主检测）（新增 rknn_detector + 部署脚本/文档 + 降级单测，2026-03-14 通过）
- [x] Prompt12F-Hotfix 默认模型切换为 `main_detector_n_int8.rknn`（更新 RKNN 默认路径/脚本/文档与单测，RK3566 实机升频后复测，2026-03-14）
- [x] Prompt12G 跟踪/Zone/事件压缩质量提升（IoU 跟踪 + zone 映射 + 阈值/去重/节流压缩策略 + 集成测试，2026-03-14 通过）
- [x] Prompt12H Recent Clip 真实化（MP4 + ring buffer）（_assemble_clip 真实 MP4 编码 + ring buffer 策略增强 + 集成测试，2026-03-14 通过）
- [x] Prompt12I 可靠性/安全/压测验收（新增可靠性计划/压测报告/soak脚本/集成测试，断网补传与回压策略已验证，2026-03-14 通过）
- [x] Prompt12-Hotfix 边缘地址与设备信息修正（默认 EDGE_BACKEND_BASE_URL 更新为 `http://100.92.134.46:8000`，相机源更新为 `rtsp://100.103.105.108/live`，2026-03-14）
- [x] Prompt13 安全与访问控制落地
- [x] Prompt14 测试矩阵落地
- [x] Prompt14-Hotfix 测试文档拆分与必要性分析（保留测试.md 原文，新增 docs/edge/testing_index.md + model_selection_strategy.md + model_ab_test_matrix.md + test_necessity_analysis.md；2026-03-14 运行 edge 相关回归通过）
- [x] Prompt15 最终联调收尾与交付
- [x] Prompt16 轻前端重后端改造第一阶段（新增 docs/edge/light_edge_heavy_backend_refactor.md，edge analysis_requests 协议扩展与后端 OCR 自动触发链路，2026-03-14）
- [x] Prompt16-Hotfix 日志时间统一为本地时区（新增 `VISION_BUTLER_TIME_MODE`，启动脚本默认 `local + Asia/Shanghai`，2026-03-14）
- [x] Prompt16-Hotfix 摄像头 capture 限制解除（RK3566 实机确认 `YUYV@720p` 平均采集约 200ms、`MJPG@720p` 约 33ms；`start_edge.sh` 增加 v4l2 自动调优并文档同步，2026-03-15）
- [x] Prompt16-Hotfix 默认模型切换 YOLOv8n INT8 + 并行流水线（`yolov8n_official_i8_rk3566.rknn` 作为默认模型，新增 `LatestFramePrefetchCamera` 并行采集，2026-03-15）

## B. TASKS 任务清单（T0-T16 + T13A-T13I）
- [x] T0 仓库初始化与约束固化
- [x] T1 数据库与迁移系统
- [x] T2 配置系统
- [x] T3 Schema 与 Repository
- [x] T4 FastAPI 后端骨架
- [x] T5 memory_service 与 perception_service
- [x] T6 state_service 与 policy_service
- [x] T7 device_service 与媒体链路
- [x] T7-Hotfix 摄像头可用性修复（SQLite 线程 + runtime 流地址 + edge 默认后端，2026-03-14 本地复验通过）
- [x] T8 OCR 双通道
- [x] T9 MCP Server 层
- [x] T10 Skill 层
- [x] T11 nanobot 集成
- [x] T11-Hotfix 模型切换至 qwen3.5-35b-a3b 并补充模型/密钥更换说明
- [x] T12 Telegram 正式交互链路
- [x] T12-Hotfix Telegram 重复消费防护（单 token 单实例）
- [x] T12-Hotfix MCP kwargs 参数兼容（避免 camera_id/device_id 丢失）
- [x] T13 RK3566 前端最小正式实现
- [x] T13A 板级 bring-up 与基线测量（新增 baseline 脚本与报告模板，2026-03-14 自检通过）
- [x] T13B 前端协议冻结（event/heartbeat/command）（新增 protocol 文档、三份 schema、入站 schema_version 校验，2026-03-14 测试通过）
- [x] T13C 真实采集层替换（V4L2/GStreamer）（新增真实采集实现与重试机制，2026-03-14 单测通过）
- [x] T13D 真实 Snapshot 落地（JPEG）（_store_snapshot 真实 JPEG + 回传落库测试，2026-03-14 通过）
- [x] T13D-Hotfix 快照黑屏修复（实机 RK3566 验证 `take-snapshot/run-once`，抓拍恢复真实画面，2026-03-14）
- [x] T13E 命令闭环最小打通（替换后端 StubEdgeDeviceAdapter）（新增 edge_command_client + 命令桥接集成测试，2026-03-14 通过）
- [x] T13F RKNN 检测模型部署（主检测）（新增 rknn_detector + 部署脚本/文档 + 降级单测，2026-03-14 通过）
- [x] T13F-Hotfix 默认模型切换为 `main_detector_n_int8.rknn`（更新默认模型入口与文档示例，实机 RK3566 复测，2026-03-14）
- [x] T13G 跟踪/Zone/事件压缩质量提升（新增 test_edge_event_quality + edge 相关测试 13 项通过，2026-03-14）
- [x] T13H Recent Clip 真实化（MP4 + ring buffer）（新增 test_edge_recent_clip_real_media + 相关回归测试 9 项通过，2026-03-14）
- [x] T13I 可靠性/安全/压测验收（新增 test_edge_reliability_flow + edge_soak_test.sh，可靠性相关回归 10 项通过，2026-03-14）
- [x] T13-Hotfix 边缘地址与设备信息修正（默认后端地址/RTSP 地址/设备备忘已同步到 AGENTS.md，2026-03-14）
- [x] T14 安全与访问控制落地
- [x] T15 测试矩阵落地
- [x] T15-Hotfix 测试文档拆分与必要性分析（新增 edge 测试文档拆分与索引，2026-03-14 执行 pytest tests/unit/test_rknn_detector.py tests/unit/test_edge_runtime.py tests/integration/test_edge_event_quality.py 通过）
- [x] T16 最终联调收尾与交付
- [x] T17 轻前端重后端改造第一阶段（edge analysis_requests + backend OCR hook + 协议/schema/测试同步，2026-03-14）
- [x] T17-Hotfix 日志时间统一为本地时区（`src/db/session.py` + edge 时间函数支持 local/utc，`start_backend.sh`/`start_edge.sh` 默认本地时区，2026-03-14）
- [x] T17-Hotfix 摄像头 capture 限制解除（`scripts/start_edge.sh` 增加 `EDGE_CAPTURE_APPLY_V4L2_TUNING` 与实机参数固化，`docs/EDGE_DEVICE.md` 与 `docs/edge/model_ab_test_matrix.md` 同步，2026-03-15）
- [x] T17-Hotfix 默认模型切换 YOLOv8n INT8 + 并行流水线（`edge_device/capture/camera.py` 并行预取，`edge_device/api/server.py` 注入并行配置，`scripts/start_edge.sh` 默认模型切换，2026-03-15）

## C. 验收打勾规则
- [ ] 目标文件已创建或修改正确
- [ ] 对应命令可运行
- [ ] 对应测试通过
- [ ] 无越权改动（遵守 AGENTS 边界）
- [ ] 关键行为可追踪（日志/审计）
