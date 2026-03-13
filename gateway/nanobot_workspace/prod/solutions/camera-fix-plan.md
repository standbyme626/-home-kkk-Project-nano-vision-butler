# 摄像头配置问题 - 解决计划

## 📅 创建时间
2026-03-14 00:28 CST

## 🎯 问题概述
摄像头 `cam-entry-01` 显示在线但无法使用，根本原因是缺少监控区域 (zone_id) 配置。

---

## 🔍 问题分析总结

### 当前状态
| 项目 | 值 | 状态 |
|------|-----|------|
| 设备 ID | cam-entry-01 | ✅ 已注册 |
| 设备状态 | online | ✅ 在线 |
| zone_id | null | ❌ **缺失** |
| 最后活动 | 2026-03-13T13:20:48Z | ⚠️ 约 11 小时前 |

### 失败的功能
- ❌ `take_snapshot` - FOREIGN KEY constraint failed
- ❌ `describe_scene` - zone_id is required
- ❌ `get_recent_clip` - zone_id is required
- ❌ `device_status` - Device not found

---

## 💡 解决方案

### 方案一：重新配置监控区域（推荐）⭐

#### 步骤 1：确认可用监控区域
```bash
# 查询系统中可用的 zones
# 需要系统管理员权限或访问数据库
```

#### 步骤 2：绑定摄像头到区域
```sql
-- 示例 SQL（需根据实际表结构调整）
UPDATE cameras 
SET zone_id = 'zone-xxx' 
WHERE camera_id = 'cam-entry-01';

-- 或者插入关联记录
INSERT INTO camera_zones (camera_id, zone_id) 
VALUES ('cam-entry-01', 'zone-xxx');
```

#### 步骤 3：验证配置
```bash
# 测试快照功能
mcp_vision-butler-mcp_take_snapshot(device_id="cam-entry-01")

# 测试场景描述
mcp_vision-butler-mcp_describe_scene(camera_id="cam-entry-01", zone_id="zone-xxx")
```

**预计耗时**: 15-30 分钟  
**所需权限**: 系统管理员 / 数据库管理员

---

### 方案二：删除并重新注册设备

#### 步骤 1：备份现有配置
```bash
# 导出当前设备信息
SELECT * FROM cameras WHERE camera_id = 'cam-entry-01';
```

#### 步骤 2：删除不完整记录
```sql
DELETE FROM cameras WHERE camera_id = 'cam-entry-01';
DELETE FROM device_registry WHERE device_id = 'cam-entry-01';
```

#### 步骤 3：完整重新注册
```bash
# 使用完整的注册流程，确保包含 zone_id
# 需要调用设备注册 API 或管理界面
```

**预计耗时**: 30-60 分钟  
**风险**: 可能丢失历史数据

---

### 方案三：使用其他可用摄像头

如果 `cam-entry-01` 是测试设备且无法修复：

#### 步骤 1：查找可用摄像头
```bash
# 查询所有在线摄像头
SELECT camera_id, device_status, zone_id 
FROM cameras 
WHERE device_status = 'online' AND zone_id IS NOT NULL;
```

#### 步骤 2：切换到可用摄像头
```python
# 在代码中更新摄像头 ID
CAMERA_ID = "cam-available-01"  # 替换为实际可用 ID
```

**预计耗时**: 5-10 分钟  
**适用场景**: 紧急情况下快速恢复功能

---

## 📋 实施计划

### 阶段一：诊断与准备（立即执行）

| 任务 | 负责人 | 预计时间 | 状态 |
|------|--------|----------|------|
| 1. 确认是否有其他可用摄像头 | 系统管理员 | 5 分钟 | ⏳ 待执行 |
| 2. 检查数据库中的 zones 表 | DBA | 10 分钟 | ⏳ 待执行 |
| 3. 确定目标 zone_id | 系统管理员 | 5 分钟 | ⏳ 待执行 |

### 阶段二：执行修复（优先级高）

| 任务 | 负责人 | 预计时间 | 状态 |
|------|--------|----------|------|
| 1. 备份当前配置 | 系统管理员 | 5 分钟 | ⏳ 待执行 |
| 2. 执行 zone_id 绑定操作 | DBA | 10 分钟 | ⏳ 待执行 |
| 3. 验证功能恢复正常 | 测试人员 | 10 分钟 | ⏳ 待执行 |

### 阶段三：验证与监控（修复后）

| 任务 | 负责人 | 预计时间 | 状态 |
|------|--------|----------|------|
| 1. 测试所有视觉功能 | 测试人员 | 15 分钟 | ⏳ 待执行 |
| 2. 监控系统稳定性 | 运维人员 | 持续 | ⏳ 待执行 |
| 3. 更新文档记录 | 技术文档 | 5 分钟 | ⏳ 待执行 |

---

## 🛡️ 预防措施

### 短期措施
1. **添加配置完整性检查**
   ```python
   def validate_camera_config(camera_id):
       camera = get_camera(camera_id)
       if not camera.zone_id:
           raise ValueError(f"Camera {camera_id} missing zone_id")
   ```

2. **设置健康检查告警**
   - 定期检查设备配置完整性
   - 对配置不完整的设备发出告警

### 长期措施
1. **完善设备注册流程**
   - 确保新设备注册时同步配置区域
   - 添加必填字段校验

2. **数据库约束优化**
   - 添加外键约束防止孤儿记录
   - 设置级联删除规则

3. **自动化监控**
   - 每日自动检查设备状态
   - 异常自动通知管理员

---

## 📞 联系人

| 角色 | 职责 | 联系方式 |
|------|------|----------|
| 系统管理员 | 配置管理 | TBD |
| 数据库管理员 | 数据修复 | TBD |
| 运维人员 | 监控维护 | TBD |

---

## 📝 备注

- 此问题可能是测试/模拟设备未完全配置导致
- 建议评估是否需要保留该设备或移除
- 如频繁出现类似问题，需审查设备注册流程

---

*最后更新时间：2026-03-14 00:28 CST*
