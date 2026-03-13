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
- T13

### 收尾线：测试与验收
- T15
- T16
