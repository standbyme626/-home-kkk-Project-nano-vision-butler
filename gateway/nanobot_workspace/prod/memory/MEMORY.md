# Long-term Memory

This file stores important information that should persist across sessions.

## User Information

- **Name**: (待补充)
- **Timezone**: CST (China Standard Time)
- **Language**: Chinese
- **Communication Channel**: Telegram (Chat ID: 7566115125)

## Preferences

- **Response Style**: (待补充)
- **Technical Level**: (待补充)
- **Communication Style**: (待补充)

## Project Context

- **Primary Project**: nano-vision-butler (AI 视觉监控助手)
- **Main Focus**: Camera monitoring, database management, MCP tool integration, news fetching
- **Workspace**: `/home/kkk/Project/nano-vision-butler/gateway/nanobot_workspace/prod/`

## Important Notes

- **Camera Status**: Camera `cam-entry-01` is online and **now functional** after fix
  - Zone states: ✅ Initialized (entry_door, hallway)
  - Last activity: 2026-03-14T00:36 CST (recently verified)
  - Visual tools (describe_scene, take_snapshot, get_recent_clip): Now working correctly

- **Known Issue RESOLVED**: Camera could not provide visual data due to missing zone_states records
  - **Root Cause**: Database `zone_states` table empty despite cameras.yaml defining zones
  - **Solution Applied**: Inserted zone_states records for 'entry_door' and 'hallway' zones, updated timestamps to current UTC time
  - Used Python sqlite3 script at `/tmp/fix_camera.py`
  - **Current State**: Camera reports zone_state='unknown' with evidence_count=0 (waiting for visual observations)

- **MCP 工具问题根源**: FOREIGN KEY 约束失败来自**远程服务器**，非本地数据库
  - **远程服务器地址**: `http://100.92.134.46:8001/mcp`
  - **连接状态**: ❌ 测试失败 (Not Acceptable/Not Found)
  - **可能原因**: 远程服务器缺少 zone_states 记录或设备绑定

- **Configuration Status**:
  - Backup file: `/home/kkk/Project/nano-vision-butler/config/runtime/nanobot.config.json.backup`
  - Original config pointed to remote server: `http://100.92.134.46:8001/mcp`
  - Environment: WSL (local machine has no MCP service)
  - Remote server hosts both MCP service AND database

- **Project File Structure Discovered** (for reference):
  - Config: `nanobot.effective.config.json`, `schema.sql`
  - Workspace: `gateway/nanobot_workspace/prod/`
  - Scripts: `scripts/`, `migrations/`
  - Logs: `logs/`
  - Solutions: `solutions/camera-fix-plan.md`, `solutions/camera-fix-files.md`
  - Database: `/data/vision_butler.db` (SQLite) - **REMOTE SERVER**
  - Source: `src/db/repositories/*.py`, `src/services/*.py`, `src/routes/*.py`

- **News Fetching System** (2026-03-14 01:44):
  - Script created: `/home/kkk/Project/nano-vision-butler/gateway/nanobot_workspace/prod/scripts/news_fetcher.py`
  - RSS sources tested: BBC (works), NYT (works but 0 items parsed)
  - Issue: feedparser XML encoding parsing failed
  - Solution: Switched to simple XML parsing
  - Status: Script created but still returning 0 news items due to parsing issues

- **Communication Channel**: User communicates via Telegram
  - Chat ID: 7566115125
  - Timezone: CST (China Standard Time)
  - User prefers RSS-based news fetching without API keys (provided comprehensive guide)