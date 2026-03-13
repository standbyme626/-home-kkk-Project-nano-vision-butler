# Nano Vision Butler v5

基于 Telegram 的视觉管家系统正式仓库（骨架阶段）。

## 项目定位
- 正式唯一用户入口：Telegram
- 唯一主控宿主：nanobot（负责会话、模型与工具编排）
- 正式能力层：MCP / Skills
- RK3566 单目前端：仅负责边缘感知与设备上报，不承载长期记忆与权限治理

## 核心组成
- `gateway/`：nanobot 相关接入与宿主配置
- `src/`：后端 sidecar 服务（memory / perception / state / policy / security / device）
- `src/mcp_server/`（后续创建）：向 nanobot 暴露 tools/resources/prompts
- `skills/`：Skill 定义与执行模板
- `edge_device/`：RK3566 边缘采集与事件压缩
- `config/`：统一配置（settings/policies/access/devices/cameras 等）
- `tests/`：unit / integration / e2e 测试
- `docs/`：产品、架构、测试、部署文档

## 启动顺序（正式运行时）
1. 启动后端 sidecar 服务与数据库（事实层）
2. 启动 MCP Server 并注册能力
3. 启动 nanobot 主控并挂载 MCP/Skills
4. 启动 Telegram 通道（Webhook 或 Long Polling）
5. 启动 RK3566 前端上报链路（heartbeat/event/media）

## 当前状态
- 已完成 Prompt01 / T0：仓库骨架与约束文档初始化
- 已完成 Prompt01~Prompt15 / T0~T16（含测试矩阵与交付收尾）

## 本地最小启动
1. 初始化数据库：`./scripts/init_db.sh`
2. 启动后端：`./scripts/start_backend.sh`
3. 启动 MCP HTTP 服务：`./scripts/start_mcp.sh`
4. 预检查网关命令：`NANOBOT_DRY_RUN=1 NANOBOT_INSTANCE=dev ./scripts/start_gateway.sh`
5. 启动边缘运行一次：`EDGE_ACTION=run-once ./scripts/start_edge.sh`
6. 执行 smoke：`./scripts/smoke_test.sh`

## 后台常驻启动
- 一键后台启动：`NANOBOT_INSTANCE=prod NANOBOT_AUTO_DISABLE_MCP=0 ./scripts/stack_ctl.sh start`
- 查看状态：`./scripts/stack_ctl.sh status`
- 查看日志：`./scripts/stack_ctl.sh logs gateway`
- 停止全部：`./scripts/stack_ctl.sh stop`

## Ollama 上下文档位
- 默认模型：`qwen3.5:4b-32k`（远端 Ollama）
- 切回阿里百炼：`./scripts/switch_ollama_ctx.sh dashscope --restart`
- 切到 64k：`./scripts/switch_ollama_ctx.sh 64k --restart`
- 切回 32k：`./scripts/switch_ollama_ctx.sh 32k --restart`
- 查看当前档位：`./scripts/switch_ollama_ctx.sh status`

## 当前可运行范围
- FastAPI sidecar、SQLite、MCP Server、Telegram update 处理链路、edge runtime CLI 均可本地运行。
- 单测/集成/E2E 测试与 smoke 脚本可直接执行。

## 当前仍为适配器范围
- 真实 Telegram bot token/网络通道、nanobot 真实进程挂载、边缘设备级进程托管为环境适配项，不在仓库内强绑定。

更多交付明细见：`docs/DELIVERY_CHECKLIST.md` 与 `docs/DEPLOYMENT.md`。
# -home-kkk-Project-nano-vision-butler
