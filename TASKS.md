# TASKS.md

本文件用于驱动 Codex 按阶段完成 Vision Butler v5。

规则：
- 按顺序执行，除非明确标注可并行
- 每个任务完成后必须更新状态
- 每个任务必须通过本任务的验收标准
- 不允许跳过“数据库 / 配置 / 测试”直接堆业务代码

任务状态：
- TODO
- DOING
- DONE
- BLOCKED

---

## T0 仓库初始化与约束固化
状态：DONE
优先级：P0
依赖：无

### 目标
建立正式仓库骨架，并把项目约束固化到仓库。

### 输出
- AGENTS.md
- README.md
- docs/PRODUCT_PLAN.md
- docs/ARCHITECTURE.md
- docs/TEST_PLAN.md
- docs/DEPLOYMENT.md
- config/ 空模板
- scripts/ 空模板
- 顶层目录结构

### 验收
- 仓库目录存在
- 文档可读
- AGENTS.md 已写明硬边界
- README 能说明项目定位与启动方式

---

## T1 数据库与迁移系统
状态：DONE
优先级：P0
依赖：T0

### 目标
建立 SQLite + FTS5 的正式数据层和迁移目录。

### 输出
- schema.sql
- migrations/README.md
- migrations/sql/001_init_core.sql
- migrations/sql/002_aux_tables.sql
- migrations/sql/003_indexes.sql
- migrations/sql/004_fts.sql
- migrations/sql/005_fts_triggers.sql
- migrations/sql/006_views.sql
- migrations/sql/007_backfill_fts.sql
- scripts/init_db.sh

### 验收
- 能初始化空库
- 表、索引、FTS、视图存在
- smoke queries 可执行
- telegram_updates 去重表存在
- world_state_view 存在

---

## T2 配置系统
状态：DONE
优先级：P0
依赖：T0

### 目标
建立统一配置加载机制，管理 settings / policies / access / devices / cameras。

### 输出
- config/settings.yaml
- config/policies.yaml
- config/access.yaml
- config/devices.yaml
- config/cameras.yaml
- config/aliases.yaml
- src/settings.py 或等价模块

### 验收
- 程序可加载所有配置文件
- 缺失关键配置时报清晰错误
- 配置对象可被 services 和 app 注入

---

## T3 Schema 与 Repository
状态：DONE
优先级：P0
依赖：T1, T2

### 目标
完成数据模型与 repository 查询封装。

### 输出
- src/schemas/memory.py
- src/schemas/state.py
- src/schemas/policy.py
- src/schemas/security.py
- src/schemas/device.py
- src/schemas/telegram.py
- src/db/session.py
- src/db/repositories/*.py

### 验收
- 支持 observation/event/state/device/audit 的基本读写
- 至少实现：
  - last_seen
  - get_object_state
  - get_zone_state
  - query_recent_events
  - device_status
  - save_telegram_update
- 单元测试可运行

---

## T4 FastAPI 后端骨架
状态：DONE
优先级：P0
依赖：T2, T3

### 目标
建立可运行的后端服务入口、路由注册和依赖注入。

### 输出
- src/app.py
- src/dependencies.py
- src/routes_memory.py
- src/routes_state.py
- src/routes_policy.py
- src/routes_device.py
- src/routes_ocr.py

### 验收
- 应用可启动
- /healthz 可访问
- 路由与 service 分层清晰
- 统一异常处理存在

---

## T5 memory_service 与 perception_service
状态：DONE
优先级：P1
依赖：T3, T4

### 目标
打通 observation / event / heartbeat 写入链路。

### 输出
- src/services/memory_service.py
- src/services/perception_service.py
- /device/ingest/event
- /device/heartbeat

### 验收
- 前端事件可写 observations
- 可根据规则升级为 events
- heartbeat 可刷新 devices.last_seen 和 status
- 关键动作写 audit_logs

---

## T6 state_service 与 policy_service
状态：DONE
优先级：P1
依赖：T5

### 目标
实现 object_state / zone_state / world_state / stale / fallback。

### 输出
- src/services/state_service.py
- src/services/policy_service.py
- /memory/object-state
- /memory/zone-state
- /memory/world-state
- /policy/evaluate-staleness

### 验收
- object_state 可查询
- zone_state 可查询
- stale 正常计算
- fallback_required 正常输出
- reason_code 有值

---

## T7 device_service 与媒体链路
状态：DONE
优先级：P1
依赖：T5

### 目标
打通拍照、视频片段、设备状态查询。

### 输出
- src/services/device_service.py
- /device/status
- /device/command/take-snapshot
- /device/command/get-recent-clip

### 验收
- snapshot 返回 media URI
- clip 返回 media URI
- 设备离线时有明确错误
- media_items 正常入库

---

## T7-Hotfix 摄像头可用性修复（SQLite 线程 + runtime 配置）
状态：DONE
优先级：P1
依赖：T7

### 目标
修复摄像头“看起来在线但命令不可用”的关键问题，恢复心跳与命令链路可用性。

### 输出
- src/db/session.py（SQLite 线程切换兼容）
- src/services/perception_service.py（ingest_event 刷新设备在线状态）
- config/runtime/cameras.yaml（修复 RTSP 地址）
- scripts/start_edge.sh（修复默认后端地址并支持位置参数 action）
- tests/unit/test_db_session.py（线程回归测试）
- tests/integration/test_device_event_flow.py（事件刷新在线状态回归测试）

### 验收
- /device/status 返回 `effective_status=online`（心跳后）
- /device/command/take-snapshot 可成功
- /device/command/get-recent-clip 可成功
- pytest 全量通过

---

## T8 OCR 双通道
状态：DONE
优先级：P1
依赖：T4, T5

### 目标
实现模型 OCR + 工具 OCR 双通道。

### 输出
- src/services/ocr_service.py
- /ocr/quick-read
- /ocr/extract-fields
- ocr_results 写入逻辑

### 验收
- 简单 OCR 可返回文本
- 结构化 OCR 可返回 fields_json
- OCR 结果可与 observation/event 关联

---

## T9 MCP Server 层
状态：DONE
优先级：P1
依赖：T6, T7, T8

### 目标
把正式能力暴露成标准 MCP tools/resources/prompts。

### 输出
- src/mcp_server/tools/*.py
- src/mcp_server/resources/*.py
- src/mcp_server/prompts/*.py
- MCP 启动入口

### 验收
- tools 可列出
- tools 可调用
- resources 可读取
- prompts 可读取
- 至少实现核心工具清单

---

## T10 Skill 层
状态：DONE
优先级：P1
依赖：T9

### 目标
建立正式 Skills，并与 MCP 工具对齐。

### 输出
- skills/scene_query/SKILL.md
- skills/history_query/SKILL.md
- skills/last_seen/SKILL.md
- skills/object_state/SKILL.md
- skills/zone_state/SKILL.md
- skills/ocr_query/SKILL.md
- skills/device_status/SKILL.md
- 可选 skill_registry.py

### 验收
- 每个 Skill 都有明确字段
- 与工具清单一致
- freshness / fallback 有定义

---

## T11 nanobot 集成
状态：DONE
优先级：P1
依赖：T9, T10

### 目标
将 nanobot 作为正式宿主接入 Telegram、Qwen3.5、MCP 和 Skills。

### 输出
- config/nanobot.config.json
- gateway/nanobot_workspace/
- scripts/start_gateway.sh

### 验收
- nanobot 能启动
- Telegram channel 可用
- MCP servers 可被发现
- workspace 可创建
- allowFrom 生效

---

## T11-Hotfix 模型与密钥切换指引 + 默认模型更新
状态：DONE
优先级：P1
依赖：T11

### 目标
将运行默认模型切换到 `qwen3.5-35b-a3b`，并在 README 明确说明模型与密钥的修改位置和步骤。

### 输出
- `config/runtime/nanobot.config.json`（prod 模型更新）
- `config/runtime/nanobot.dev.config.json`（dev 模型更新）
- `scripts/switch_ollama_ctx.sh`（dashscope 档位默认模型更新）
- `scripts/apply_runtime_config.sh`（runtime 渲染默认模型更新）
- `README.md`（新增模型/密钥更换说明）

### 验收
- prod/dev runtime 默认模型均为 `qwen3.5-35b-a3b`
- README 可直接指引用户定位并替换 `model/apiBase/apiKey`
- 相关脚本切换/渲染默认值不再回落到旧模型

---

## T12 Telegram 正式交互链路
状态：DONE
优先级：P1
依赖：T11

### 目标
把 Telegram 当正式入口完整打通。

### 输出
- reply_service / reply_builder
- update 去重处理
- 长消息分片
- sendChatAction
- 基础命令入口

### 验收
- 文本问答可用
- 图片问答可用
- 拍照命令可用
- 长消息自动分片
- 长任务有 processing 提示

---

## T12-Hotfix Telegram 重复消费防护
状态：DONE
优先级：P1
依赖：T12

### 目标
避免同一个 Telegram bot token 被多 gateway 进程同时消费，导致会话重复执行与重复回复。

### 输出
- `scripts/start_gateway.sh` 增加“同 token 单实例”启动前检查
- `scripts/apply_runtime_config.sh` 的 dev token 回退逻辑改为独立默认值
- `README.md` 增加重复回复排查说明

### 验收
- 当已有 gateway 使用同 token 运行时，第二个 gateway 启动会被拒绝
- `TELEGRAM_BOT_TOKEN_DEV` 缺省时不再自动复用 `TELEGRAM_BOT_TOKEN`
- 相关集成测试不回归

---

## T12-Hotfix MCP kwargs 参数兼容
状态：DONE
优先级：P1
依赖：T12

### 目标
兼容 nanobot 通过 `kwargs`（对象或 JSON 字符串）封装的 MCP 工具入参，避免 `camera_id/device_id` 丢失导致工具误报必填缺失。

### 输出
- `src/mcp_server/http_server.py` 增加 `kwargs` 解包与合并逻辑
- `tests/unit/test_mcp_http_server.py` 新增 `kwargs` 字符串/对象兼容用例

### 验收
- `kwargs='{\"camera_id\":\"...\"}'` 能被正确传入工具
- `kwargs={...}` 能被正确传入工具
- MCP 相关单测与集成测试通过

---

## T13 RK3566 前端最小正式实现
状态：DONE
优先级：P2
依赖：T5, T7

### 目标
实现可接入的边缘设备最小正式版本。

### 输出
- edge_device/capture/
- edge_device/inference/
- edge_device/tracking/
- edge_device/compression/
- edge_device/cache/
- edge_device/health/
- edge_device/api/

### 验收
- 能采图
- 能检测
- 能上报 heartbeat
- 能响应 snapshot / clip 请求

---

## T13A 板级 bring-up 与基线测量
状态：DONE（2026-03-14）
优先级：P1
依赖：T13

### 目标
在真实 RK3566 板端建立可复现的采集与负载基线，作为后续模型与媒体链路的前置条件。

### 输出
- docs/edge/baseline_report.md
- scripts/edge_baseline_capture.sh
- scripts/edge_baseline_metrics.sh

### 验收
- 摄像头节点可稳定枚举
- 分辨率/FPS/像素格式基线可复现
- 连续 30-60 分钟采集无崩溃/无持续掉流
- CPU/内存/NPU（若可读）指标有基线记录

---

## T13B 前端协议冻结（event/heartbeat/command）
状态：DONE（2026-03-14）
优先级：P1
依赖：T13A

### 目标
冻结 edge -> backend 协议，避免后续实现阶段反复改字段。

### 输出
- docs/edge/protocol.md
- schemas/edge_event_envelope.schema.json
- schemas/edge_heartbeat.schema.json
- schemas/edge_command_response.schema.json

### 验收
- event/heartbeat/command response 字段与计划书一致
- 示例 payload 可通过 schema 校验
- 后端入站校验可识别 schema_version 与关键必填字段

---

## T13C 真实采集层替换（V4L2/GStreamer）
状态：TODO
优先级：P1
依赖：T13B

### 目标
以真实采集管线替换 StubCamera，实现可恢复的板端采图能力。

### 输出
- edge_device/capture/camera.py（真实实现）
- edge_device/capture/v4l2_camera.py（或 gstreamer_camera.py）
- tests/unit/test_edge_capture.py

### 验收
- 支持 source/fps/resolution/pixel_format 配置
- 采集失败可重试并输出可观测错误
- 连续采集稳定运行

---

## T13D 真实 Snapshot 落地（JPEG）
状态：TODO
优先级：P1
依赖：T13C

### 目标
把占位 snapshot 文件替换为真实 JPEG，先打通“可验图”的最短路径。

### 输出
- edge_device/api/server.py（_store_snapshot 真实编码）
- tests/integration/test_edge_snapshot_real_media.py
- docs/edge/snapshot_contract.md

### 验收
- snapshot 文件为真实 JPEG，可被标准图像工具读取
- 宽高与实际帧一致
- snapshot URI 回传后端并可落库索引

---

## T13E 命令闭环最小打通（替换后端 StubEdgeDeviceAdapter）
状态：TODO
优先级：P1
依赖：T13D

### 目标
让 /device/command/take-snapshot 与 /device/command/get-recent-clip 触发真实 edge 执行器，而非后端 stub。

### 输出
- src/services/device_service.py（接入真实 edge command client）
- src/services/edge_command_client.py
- tests/integration/test_device_command_edge_bridge.py

### 验收
- 后端命令可远程触发 edge 执行
- command_id/trace_id 可全链路追踪
- 不再依赖 StubEdgeDeviceAdapter 生成媒体结果

---

## T13F RKNN 检测模型部署（主检测）
状态：TODO
优先级：P1
依赖：T13E

### 目标
接入 RKNN 主检测模型，替换 LightweightDetector stub。

### 输出
- edge_device/inference/rknn_detector.py
- scripts/rknn/export_to_rknn.sh
- scripts/rknn/run_infer_benchmark.sh
- docs/edge/model_deploy.md

### 验收
- 板端可输出真实 bbox/class/confidence
- model_version 与实际模型一致
- 推理失败可降级并记录错误

---

## T13G 跟踪/Zone/事件压缩质量提升
状态：TODO
优先级：P1
依赖：T13F

### 目标
提升 event 质量与稳定性，减少抖动和无效上报。

### 输出
- edge_device/tracking/tracker.py（真实策略）
- edge_device/compression/event_compressor.py（策略增强）
- tests/integration/test_edge_event_quality.py

### 验收
- track_id 在连续帧下稳定
- zone_id 映射正确
- event 压缩策略可配置（阈值/去重/节流）

---

## T13H Recent Clip 真实化（MP4 + ring buffer）
状态：TODO
优先级：P1
依赖：T13G

### 目标
产出真实可播放 clip，并与 ring buffer 策略协同。

### 输出
- edge_device/api/server.py（_assemble_clip 真实编码）
- edge_device/cache/ring_buffer.py（策略增强）
- tests/integration/test_edge_recent_clip_real_media.py

### 验收
- clip 为真实 MP4，可播放
- 片段长度与请求时长匹配
- 缓存淘汰策略可观测、可复现

---

## T13I 可靠性/安全/压测验收
状态：TODO
优先级：P1
依赖：T13H

### 目标
固化回压与退化策略，完成可交付级稳定性与安全验收。

### 输出
- docs/edge/reliability_plan.md
- docs/edge/soak_test_report.md
- tests/integration/test_edge_reliability_flow.py
- scripts/edge_soak_test.sh

### 验收
- take_snapshot 成功率 >= 99%，P95 响应时间有明确阈值
- get_recent_clip 成功率 >= 98%，P95 生成时长有明确阈值
- event captured_at 到后端入库 P95 延迟有明确阈值
- heartbeat 连续 24h 无误报抖动
- 至少一次断网恢复演练通过并可补传关键事件
- 回压/退化策略生效：优先保 heartbeat 与关键事件

---

## T14 安全与访问控制落地
状态：DONE
优先级：P1
依赖：T9, T10, T11, T12

### 目标
实现统一的 security_guard / access_policy，使用户、设备、tools、resources、media 访问都受控并可审计。

### 输出
- src/security/security_guard.py
- src/security/access_policy.py
- src/schemas/security.py
- tests/unit/test_security_guard.py
- tests/integration/test_access_control_flow.py

### 验收
- 非 allowlist 用户会被拒绝
- 非 allowlist 设备会被拒绝
- Skill 调未授权 tool 会被拒绝
- 读取未授权 resource/media 会被拒绝
- 所有拒绝行为有 audit 记录

---

## T15 测试矩阵落地
状态：DONE
优先级：P1
依赖：T6, T7, T8, T9, T11, T12, T14

### 目标
把项目书中的测试矩阵变成真实测试。

### 输出
- tests/unit/*.py
- tests/integration/*.py
- tests/e2e/*.py
- scripts/smoke_test.sh

### 验收
- unit / integration / e2e 三层测试存在
- 核心路径有覆盖
- pytest -q 可执行

---

## T16 最终联调收尾与交付
状态：DONE
优先级：P1
依赖：T15

### 目标
在不重构核心边界的前提下完成最终交付检查，确保仓库可运行、可验收、可交接。

### 输出
- 交付检查清单（目录/文档/脚本/测试）
- 运行与启动说明补齐
- 当前可运行范围与 stub 范围说明

### 验收
- 仓库结构完整
- 启动脚本存在并可说明启动顺序
- smoke test 可运行
- 文档可指导首次启动
- 未完成部分有诚实标注

---

## 推荐并行方式

### A 线：数据与事实层
- T1
- T2
- T3
- T5
- T6

### B 线：接口与能力层
- T4
- T7
- T8
- T9

### C 线：宿主与入口层
- T10
- T11
- T12
- T14

### D 线：边缘层
- T13A
- T13B
- T13C
- T13D
- T13E
- T13F
- T13G
- T13H
- T13I

### 收尾线：测试与验收
- T15
- T16
