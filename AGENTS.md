# Agent Instructions

Use `bd` for task tracking.

This project uses **Beads (`bd`)** for task management.

## Required bd Workflow

- Always run `bd ready` to check for open tasks before starting work.
- Create new tasks with `bd create "Task Name"`.
- Claim a task with `bd update <id> --claim`.
- Close finished work with `bd close <id>`.
- For full usage, see: <https://github.com/steveyegge/beads>

## Quick Reference

```bash
bd onboard
bd ready
bd show <id>
bd create "Task Name"
bd update <id> --claim
bd close <id>
bd sync
```

## MCP-First Workflow (Mandatory)

Every task in this repo must start with MCP-first code reading and scoping.

### Required tool order

1. `list_project_files`: narrow candidate files by directory.
2. `search_code`: locate symbols/routes/fields.
3. `read_file_excerpt`: read only relevant ranges.
4. `summarize_for_change` (optional): summarize top 2-3 files per pass from the 3-8 candidate pool before editing.
5. Implement changes only after the above steps.

### Required behavior

- Do not begin with full-file traversal when MCP tools can locate context first.
- Keep one investigation round to 3-8 candidate files.
- Read excerpts in small ranges (prefer <= 200 lines per chunk).
- For large refactors, use a balanced summary cadence: run `summarize_for_change` once per 2-3 candidate files (or once per module), not once per file.
- After each summary, narrow to top 1-2 files and re-check key claims via `read_file_excerpt` before making decisions.
- Mark conclusions as `source-verified` vs `summary-inference` when reporting scope/risk.
- After changes, re-read only impacted files/ranges for verification.

### MCP Token Budget Guardrails (Mandatory)

- Keep MCP-first workflow, but enforce token discipline on every task.
- Never start with `list_project_files` on `.` unless the user explicitly asks for full-repo scan.
- Run `list_project_files` against target subdirs first; default `max_results <= 80`.
- Use `search_code` before `read_file_excerpt`; do symbol-centered reads (prefer 40-120 lines per chunk, hard cap 200).
- Limit one file to at most 3 excerpt reads per investigation round before summarizing.
- Keep candidate pool to 3-8 files per round; if more than 8, narrow before additional reads.
- For large tasks, run `summarize_for_change` once per 2-3 candidate files, then re-verify only top 1-2 files.
- If two consecutive reads produce no new `source-verified` facts, stop and re-anchor with `search_code`.
- During investigation, avoid noisy full-repo verification scans; use path-scoped checks (for example `git status -- <target_path>`).
- Keep a compact evidence ledger in analysis output: file path, line windows, extracted claim, and `source-verified` vs `summary-inference`.

### Preferred instruction templates

```text
先不要改代码。优先使用 MCP（list_project_files -> search_code -> read_file_excerpt）。
先给我 3-8 个最相关文件和最小改动方案。
```

```text
优先使用 MCP 控制 token。先检索并局部读取，再直接修改并跑测试。
输出修改文件清单、测试结果和风险点。
```

```text
这是大改动，采用平衡策略：每收敛 2-3 个候选文件就做一次 summarize_for_change，
然后只对 Top 1-2 文件做 read_file_excerpt 复核；不要每个文件都摘要。
输出时标注 source-verified 和 summary-inference。
```

```text
必须先调用 loco_explorer 的 list_project_files、search_code、read_file_excerpt，
不要直接全文件遍历。
```

## Landing the Plane (Session Completion)

When ending a work session, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

### Mandatory Workflow

1. File issues for remaining work: Create issues for anything that needs follow-up.
2. Run quality gates (if code changed): tests, linters, builds.
3. Update issue status: close finished work, update in-progress items.
4. Push to remote (MANDATORY):
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. Clean up: clear stashes, prune remote branches.
6. Verify: all changes committed AND pushed.
7. Hand off: provide context for next session.

### Critical Rules

- Work is NOT complete until `git push` succeeds.
- NEVER stop before pushing; that leaves work stranded locally.
- NEVER say "ready to push when you are"; YOU must push.
- If push fails, resolve and retry until it succeeds.


### Project-Specific Constraints

## 项目定位
- 本项目是一个通过 Telegram 交互的视觉管家系统。
- Telegram 是正式唯一用户入口。
- nanobot 是唯一主控宿主，但不是业务真相层。
- MCP / Skill 是正式能力层，不是临时扩展。
- RK3566 前端只负责边缘感知，不负责长期记忆和权限治理。

## 核心架构边界
- 模型负责理解与决策，工具负责事实与动作。
- object_state / zone_state / freshness / stale / fallback 必须落在后端服务与数据库层。
- 所有业务能力优先通过 MCP 暴露给 nanobot，不要深改 nanobot 核心。

## 仓库级硬约束
- 目录职责必须保持清晰：`docs/`, `config/`, `edge_device/`, `src/services/`, `src/security/`, `src/schemas/`, `src/db/`, `src/mcp_server/`, `skills/`, `tests/`, `scripts/`。
- 对 SQLite 的复杂 schema 变更，优先采用“新表迁移 + 重建索引/触发器”。
- Telegram update 必须去重。
- 所有敏感动作必须写入 `audit_logs`。

## 禁止事项
- 不要深改 nanobot 核心代码来承载业务逻辑。
- 不要把状态逻辑硬编码进 Telegram 处理层。
- 不要把数据库访问散落到无约束脚本中。
- 不要让前端 RK3566 承担长期记忆、世界状态推理或复杂工具编排。
- 不要跳过测试直接交付。

## 完成定义
- 任务完成必须同时满足：目标文件正确、代码可运行、对应测试通过、目录职责未破坏、关键行为可审计追踪。

## 完成打勾（强制）
- 每完成一个任务，必须在 `PROGRESS_CHECKLIST.md` 中同步打勾。
- 至少要更新两处：`A. Prompt 执行清单` 对应项、`B. TASKS 任务清单` 对应项。
- 若任务完成但未打勾，视为未完成，不得进入下一个任务。

## 本地地址备忘（用户指定）
- 当前 PC（tailscale）IPv4：`100.92.134.46`
- 当前 PC（tailscale）IPv6：`fd7a:115c:a1e0::5a01:86a3`
- RK3566 SSH：`ssh root@100.103.105.108`
- RK3566 SSH 密码：`wasd1234`

## Task Board
- 可变的任务清单（T0~T16、状态、依赖、并行建议）统一维护在 `TASKS.md`。
- 修改任务状态时只更新 `TASKS.md`，避免和 `AGENTS.md` 双份漂移。
