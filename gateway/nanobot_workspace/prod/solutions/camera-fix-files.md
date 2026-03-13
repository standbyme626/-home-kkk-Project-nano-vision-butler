# 摄像头配置问题 - 文件修改清单

## 📅 创建时间
2026-03-14 00:32 CST

## 🎯 问题总结
摄像头 `cam-entry-01` 显示在线但无法使用，根本原因是 **缺少 zone_states 表记录**。

---

## 🔍 数据库状态分析

### ✅ 已存在的记录
```sql
-- devices 表中有设备记录
SELECT * FROM devices WHERE camera_id = 'cam-entry-01';
-- 结果：存在，status='online', last_seen='2026-03-13T13:20:48.659Z'
```

### ❌ 缺失的记录
```sql
-- zone_states 表中没有该摄像头的区域状态记录
SELECT * FROM zone_states WHERE camera_id = 'cam-entry-01';
-- 结果：空（没有任何记录）
```

### 📊 world_state_view 显示
```json
{
  "camera_id": "cam-entry-01",
  "device_status": "online",
  "zone_id": null,              ← 关键问题
  "zone_state_value": null,     ← 关键问题
  ...
}
```

---

## 📁 需要修改的文件清单

### 1️⃣ **配置文件** (无需修改)

| 文件 | 路径 | 说明 |
|------|------|------|
| cameras.yaml | `/config/cameras.yaml` | ✅ 已正确配置 zones |
| devices.yaml | `/config/devices.yaml` | ✅ 已正确配置 device |

**当前 cameras.yaml 内容**:
```yaml
cameras:
  - camera_id: cam-entry-01
    device_id: rk3566-dev-01
    display_name: entry-camera
    stream:
      source: "rtsp://__SET_CAMERA_URL__"
      fps: 10
      width: 1280
      height: 720
    zones:
      - zone_id: entry_door      ← 定义了 zone
        alias: 门口
      - zone_id: hallway         ← 定义了 zone
        alias: 走廊
```

**问题**: 配置文件中有 zones 定义，但数据库中 **没有对应的 zone_states 记录**。

---

### 2️⃣ **数据库** (需要修复) ⭐

| 文件 | 路径 | 操作 |
|------|------|------|
| vision_butler.db | `/data/vision_butler.db` | **插入 zone_states 记录** |

#### 需要执行的 SQL 语句:

```sql
-- 为 cam-entry-01 创建两个区域的初始状态记录

-- 1. 门口区域
INSERT INTO zone_states (
    id, camera_id, zone_id, state_value, state_confidence,
    observed_at, fresh_until, is_stale, evidence_count,
    source_layer, summary, updated_at
) VALUES (
    'zs-entry-door-init',
    'cam-entry-01',
    'entry_door',
    'unknown',
    0.0,
    NULL,
    datetime('now', 'utc'),
    1,
    0,
    'manual_init',
    'Initial zone state for entry_door',
    datetime('now', 'utc')
);

-- 2. 走廊区域
INSERT INTO zone_states (
    id, camera_id, zone_id, state_value, state_confidence,
    observed_at, fresh_until, is_stale, evidence_count,
    source_layer, summary, updated_at
) VALUES (
    'zs-hallway-init',
    'cam-entry-01',
    'hallway',
    'unknown',
    0.0,
    NULL,
    datetime('now', 'utc'),
    1,
    0,
    'manual_init',
    'Initial zone state for hallway',
    datetime('now', 'utc')
);
```

#### Python 脚本执行:

```python
import sqlite3
from datetime import datetime, timezone

def init_zone_states():
    conn = sqlite3.connect('/home/kkk/Project/nano-vision-butler/data/vision_butler.db')
    conn.row_factory = sqlite3.Row
    
    zones = [
        ('zs-entry-door-init', 'entry_door', '门口'),
        ('zs-hallway-init', 'hallway', '走廊'),
    ]
    
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    
    for zone_id, alias in zones:
        conn.execute("""
            INSERT OR IGNORE INTO zone_states (
                id, camera_id, zone_id, state_value, state_confidence,
                observed_at, fresh_until, is_stale, evidence_count,
                source_layer, summary, updated_at
            ) VALUES (?, 'cam-entry-01', ?, 'unknown', 0.0,
                      NULL, ?, 1, 0, 'manual_init', ?, ?)
        """, (zone_id, now, f'Initial zone state for {alias}', now))
    
    conn.commit()
    conn.close()
    print("Zone states initialized successfully!")

if __name__ == "__main__":
    init_zone_states()
```

---

### 3️⃣ **代码文件** (无需修改)

以下文件是系统核心代码，**不需要修改**:

| 文件 | 路径 | 说明 |
|------|------|------|
| schema.sql | `/schema.sql` | ✅ 数据库结构定义正确 |
| device_repo.py | `/src/db/repositories/device_repo.py` | ✅ 设备查询逻辑正确 |
| state_service.py | `/src/services/state_service.py` | ✅ 状态服务逻辑正确 |
| routes_device.py | `/src/routes_device.py` | ✅ API 路由正确 |
| settings.py | `/src/settings.py` | ✅ 配置加载逻辑正确 |

---

## 💡 问题根源分析

### 为什么会出现这个问题？

1. **设备注册成功** - `devices` 表有记录
2. **配置文件完整** - `cameras.yaml` 定义了 zones
3. **但 zone_states 未初始化** - 数据库中没有区域状态记录

### 为什么会这样？

可能的原因：
- 系统启动时没有自动初始化 zone_states
- 设备注册流程不完整（只注册了设备，没注册区域）
- 手动删除了 zone_states 记录但未重新创建

---

## 🔧 解决方案

### 方案一：直接插入数据（推荐）⭐

**优点**: 快速、简单、安全  
**耗时**: 5 分钟

```bash
# 执行 Python 脚本
cd /home/kkk/Project/nano-vision-butler
python scripts/init_zone_states.py
```

然后验证:
```bash
python -c "import sqlite3; conn = sqlite3.connect('data/vision_butler.db'); conn.row_factory = sqlite3.Row; rows = conn.execute('SELECT * FROM zone_states').fetchall(); print([dict(r) for r in rows])"
```

### 方案二：重启系统自动初始化

**优点**: 符合系统设计  
**缺点**: 可能不会自动触发

检查是否有初始化逻辑:
```bash
grep -r "zone_states" /home/kkk/Project/nano-vision-butler/src/ --include="*.py"
```

### 方案三：重新注册设备

**优点**: 完整流程  
**缺点**: 复杂、可能丢失数据

---

## 📋 实施步骤

### Step 1: 备份数据库
```bash
cp /home/kkk/Project/nano-vision-butler/data/vision_butler.db \
   /home/kkk/Project/nano-vision-butler/data/vision_butler.db.backup.$(date +%Y%m%d_%H%M%S)
```

### Step 2: 创建初始化脚本
```bash
cat > /home/kkk/Project/nano-vision-butler/scripts/init_zone_states.py << 'EOF'
import sqlite3
from datetime import datetime, timezone

def init_zone_states():
    db_path = '/home/kkk/Project/nano-vision-butler/data/vision_butler.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    zones = [
        ('zs-entry-door-init', 'entry_door', '门口'),
        ('zs-hallway-init', 'hallway', '走廊'),
    ]
    
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    
    for zone_id, alias in zones:
        conn.execute("""
            INSERT OR IGNORE INTO zone_states (
                id, camera_id, zone_id, state_value, state_confidence,
                observed_at, fresh_until, is_stale, evidence_count,
                source_layer, summary, updated_at
            ) VALUES (?, 'cam-entry-01', ?, 'unknown', 0.0,
                      NULL, ?, 1, 0, 'manual_init', ?, ?)
        """, (zone_id, now, f'Initial zone state for {alias}', now))
    
    conn.commit()
    conn.close()
    print(f"✓ Initialized {len(zones)} zone states for cam-entry-01")

if __name__ == "__main__":
    init_zone_states()
EOF
```

### Step 3: 执行初始化
```bash
python /home/kkk/Project/nano-vision-butler/scripts/init_zone_states.py
```

### Step 4: 验证结果
```bash
python -c "
import sqlite3
conn = sqlite3.connect('/home/kkk/Project/nano-vision-butler/data/vision_butler.db')
conn.row_factory = sqlite3.Row

print('=== Zone States ===')
for row in conn.execute('SELECT * FROM zone_states'):
    print(dict(row))

print('\n=== World State View ===')
for row in conn.execute('SELECT * FROM world_state_view'):
    print(dict(row))

conn.close()
"
```

### Step 5: 测试功能
```bash
# 测试场景描述
mcp_vision-butler-mcp_describe_scene(camera_id="cam-entry-01", zone_id="entry_door")

# 测试快照
mcp_vision-butler-mcp_take_snapshot(device_id="cam-entry-01")
```

---

## ✅ 预期结果

执行成功后:

```json
// world_state_view
{
  "camera_id": "cam-entry-01",
  "device_status": "online",
  "zone_id": "entry_door",           ← 现在有值了
  "zone_state_value": "unknown",     ← 现在有值了
  ...
}

// zone_states 表
[
  {
    "id": "zs-entry-door-init",
    "camera_id": "cam-entry-01",
    "zone_id": "entry_door",
    "state_value": "unknown",
    ...
  },
  {
    "id": "zs-hallway-init",
    "camera_id": "cam-entry-01",
    "zone_id": "hallway",
    "state_value": "unknown",
    ...
  }
]
```

---

## 🛡️ 预防措施

### 短期措施
1. ✅ 添加 zone_states 初始化脚本
2. ✅ 在设备注册流程中添加区域初始化步骤

### 长期措施
1. 完善设备注册 API，确保同时创建 zone_states
2. 添加健康检查，定期检查 zone_states 完整性
3. 设置告警，当 zone_states 缺失时通知管理员

---

## 📞 联系人

- **系统管理员**: TBD
- **数据库管理员**: TBD

---

*最后更新时间：2026-03-14 00:32 CST*
