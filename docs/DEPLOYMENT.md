# Deployment Plan

## 部署目标
提供单机正式部署路径，保证 Telegram 入口稳定、事实层可追踪、MCP 能力可调用。

## 目标环境
- Linux 单机（优先）
- Python 运行时
- SQLite + 本地媒体存储
- nanobot + MCP sidecar + Telegram channel

## 基础部署顺序
1. 配置 `config/`（settings/policies/access/devices/cameras）。
2. 初始化数据库与迁移。
3. 启动后端 sidecar 服务。
4. 启动 MCP Server（供 nanobot 挂载 tools/resources/prompts）。
5. 启动 nanobot 并接入 Telegram。
6. 接入 RK3566 边缘设备上报。

## Nanobot 配置说明
- 主配置：`config/nanobot.config.json`（正式实例）。
- 开发配置：`config/nanobot.dev.config.json`（开发实例，建议与正式实例分离）。
- 工作目录：`gateway/nanobot_workspace/{prod|dev}`。
- 运行时目录：`gateway/runtime/{prod|dev}`。

`nanobot.config.json` 至少覆盖以下边界：
- Telegram channel：`channels.telegram.enabled/token/allowFrom`。
- 模型：`agents.defaults.provider/model` 与 `providers.*`。
- MCP：`tools.mcpServers`。
- Workspace：`agents.defaults.workspace`。
- Runtime：`runtime.dataDir/logsDir/tempDir`。

## 启动 Gateway（nanobot）
使用脚本：`scripts/start_gateway.sh`。

关键环境变量：
- `NANOBOT_INSTANCE`：`prod` 或 `dev`（默认 `prod`）。
- `NANOBOT_BIN`：nanobot 可执行命令（默认 `nanobot`）。
- `NANOBOT_CONFIG`：配置文件路径（默认按实例选择）。
- `NANOBOT_WORKSPACE`：workspace 路径。
- `NANOBOT_RUNTIME_DIR`：runtime 目录路径。
- `NANOBOT_DRY_RUN`：`1` 时仅打印命令，不实际启动。

示例：
- 正式实例：`NANOBOT_INSTANCE=prod ./scripts/start_gateway.sh`
- 开发实例：`NANOBOT_INSTANCE=dev ./scripts/start_gateway.sh`
- 预检查：`NANOBOT_DRY_RUN=1 NANOBOT_INSTANCE=prod ./scripts/start_gateway.sh`

## 启动 Backend（sidecar）
使用脚本：`scripts/start_backend.sh`。

关键环境变量：
- `BACKEND_HOST`：监听地址（默认 `0.0.0.0`）。
- `BACKEND_PORT`：监听端口（默认 `8000`）。
- `BACKEND_RELOAD`：是否启用热加载（`1` 启用，默认 `0`）。
- `PYTHON_BIN`：Python 命令（默认 `python3`）。

示例：
- `./scripts/start_backend.sh`
- `BACKEND_PORT=8100 BACKEND_RELOAD=1 ./scripts/start_backend.sh`

## 启动 MCP Server（streamable-http）
使用脚本：`scripts/start_mcp.sh`。

关键环境变量：
- `MCP_HOST`：监听地址（默认 `0.0.0.0`）。
- `MCP_PORT`：监听端口（默认 `8001`）。
- `MCP_PATH`：MCP HTTP 路径（默认 `/mcp`）。
- `MCP_CONFIG_DIR`：配置目录（默认 `./config`，读取 `settings/policies/access/devices/cameras/aliases`）。
- `PYTHON_BIN`：Python 命令（默认 `python3`）。

示例：
- `./scripts/start_mcp.sh`
- `MCP_HOST=0.0.0.0 MCP_PORT=8001 MCP_PATH=/mcp ./scripts/start_mcp.sh`

## 启动 Edge（RK3566 runtime）
使用脚本：`scripts/start_edge.sh`。

关键环境变量：
- `EDGE_ACTION`：`run-once | heartbeat | take-snapshot | get-recent-clip`（默认 `run-once`）。
- `EDGE_LOOP`：`1` 时循环执行（默认 `0`）。
- `EDGE_INTERVAL_SEC`：循环间隔秒数（默认 `5`）。
- `EDGE_DEVICE_ID` / `EDGE_CAMERA_ID`：设备与相机标识。
- `EDGE_BACKEND_BASE_URL`：后端地址（默认 `http://127.0.0.1:8000`）。
- `EDGE_SNAPSHOT_DIR` / `EDGE_CLIP_DIR`：本地媒体目录。

示例：
- `EDGE_ACTION=heartbeat ./scripts/start_edge.sh`
- `EDGE_ACTION=run-once EDGE_LOOP=1 EDGE_INTERVAL_SEC=10 ./scripts/start_edge.sh`

## 一键后台常驻（推荐）
使用脚本：`scripts/stack_ctl.sh`，统一管理 backend / mcp / gateway 三个进程。

常用命令：
- 启动：`NANOBOT_INSTANCE=prod NANOBOT_AUTO_DISABLE_MCP=0 ./scripts/stack_ctl.sh start`
- 状态：`./scripts/stack_ctl.sh status`
- 日志：`./scripts/stack_ctl.sh logs gateway`
- 重启：`./scripts/stack_ctl.sh restart`
- 停止：`./scripts/stack_ctl.sh stop`

运行产物：
- PID 目录：`gateway/runtime/stack/pids`
- 日志目录：`gateway/runtime/stack/logs`

## Ollama 32k/64k 档位切换
使用脚本：`scripts/switch_ollama_ctx.sh`。

常用命令：
- 查看当前档位：`./scripts/switch_ollama_ctx.sh status`
- 切回阿里百炼：`./scripts/switch_ollama_ctx.sh dashscope --restart`
- 切到 32k（默认）：`./scripts/switch_ollama_ctx.sh 32k --restart`
- 切到 64k（长上下文场景）：`./scripts/switch_ollama_ctx.sh 64k --restart`

说明：
- 当前实现是“默认 32k + 按需切到 64k”。
- nanobot 目前未提供按上下文长度自动切换模型的原生开关。

## 首次启动顺序（最小交付路径）
1. `./scripts/init_db.sh`
2. `./scripts/start_backend.sh`
3. `./scripts/start_mcp.sh`
4. `NANOBOT_DRY_RUN=1 NANOBOT_INSTANCE=dev ./scripts/start_gateway.sh`
5. `EDGE_ACTION=heartbeat ./scripts/start_edge.sh`
6. `./scripts/smoke_test.sh`

## 正式实例与开发实例隔离建议
- Telegram Token/allowFrom：使用不同机器人和用户白名单，禁止共享。
- Gateway 端口：正式与开发使用不同端口（示例为 `18790` / `18791`）。
- Workspace 路径：必须分离，避免上下文污染。
- Runtime/logs 路径：必须分离，避免审计和故障排查混淆。
- 模型 Provider 配置：允许不同模型和 API Base，开发实例可启用更详细工具提示。

## 运维要求
- Telegram 更新去重必须启用。
- 敏感操作必须进入审计日志。
- 失败场景需要 fallback 与可观测日志。
- 发布前必须完成测试门禁（unit/integration/e2e）。

## 当前可运行范围与适配器边界
当前可运行范围：
- FastAPI + SQLite + MCP + Telegram update 主链路可本地启动与验证。
- `scripts/init_db.sh`、`scripts/start_backend.sh`、`scripts/start_mcp.sh`、`scripts/start_gateway.sh`、`scripts/stack_ctl.sh`、`scripts/start_edge.sh`、`scripts/smoke_test.sh` 均可执行。
- `scripts/switch_ollama_ctx.sh` 可切换远端 Ollama 上下文档位。

当前仍为适配器范围：
- 真实 Telegram token 与公网 webhook/long-polling 运维配置。
- nanobot 外部二进制、模型 provider 凭据与生产环境参数。
- RK3566 设备级守护进程与生产部署编排（systemd/k8s 等）。
