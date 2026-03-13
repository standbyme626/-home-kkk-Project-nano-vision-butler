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
- [ ] Prompt12C 真实采集层替换（V4L2/GStreamer）
- [ ] Prompt12D 真实 Snapshot 落地（JPEG）
- [ ] Prompt12E 命令闭环最小打通（替换后端 StubEdgeDeviceAdapter）
- [ ] Prompt12F RKNN 检测模型部署（主检测）
- [ ] Prompt12G 跟踪/Zone/事件压缩质量提升
- [ ] Prompt12H Recent Clip 真实化（MP4 + ring buffer）
- [ ] Prompt12I 可靠性/安全/压测验收
- [x] Prompt13 安全与访问控制落地
- [x] Prompt14 测试矩阵落地
- [x] Prompt15 最终联调收尾与交付

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
- [ ] T13C 真实采集层替换（V4L2/GStreamer）
- [ ] T13D 真实 Snapshot 落地（JPEG）
- [ ] T13E 命令闭环最小打通（替换后端 StubEdgeDeviceAdapter）
- [ ] T13F RKNN 检测模型部署（主检测）
- [ ] T13G 跟踪/Zone/事件压缩质量提升
- [ ] T13H Recent Clip 真实化（MP4 + ring buffer）
- [ ] T13I 可靠性/安全/压测验收
- [x] T14 安全与访问控制落地
- [x] T15 测试矩阵落地
- [x] T16 最终联调收尾与交付

## C. 验收打勾规则
- [ ] 目标文件已创建或修改正确
- [ ] 对应命令可运行
- [ ] 对应测试通过
- [ ] 无越权改动（遵守 AGENTS 边界）
- [ ] 关键行为可追踪（日志/审计）
