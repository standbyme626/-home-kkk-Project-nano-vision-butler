# RK3566 Baseline Report (T13A)

本模板用于记录板级 bring-up 与基线测量结果，对应 `Prompt12A / T13A`。

## 1. 基本信息

| 字段 | 值 |
| --- | --- |
| 测试日期 | `<YYYY-MM-DD>` |
| 执行人 | `<name>` |
| 板卡型号 | `RK3566` |
| OS / Kernel | `<output of uname -a>` |
| 摄像头型号 | `<camera model>` |
| 采集节点 | `</dev/videoX>` |
| 测试分支 / 提交 | `<git branch + commit>` |

## 2. 执行命令

```bash
# 1) 枚举 + 采集稳定性测试（建议 30~60 分钟）
scripts/edge_baseline_capture.sh \
  --device /dev/video0 \
  --width 1280 \
  --height 720 \
  --fps 25 \
  --pixel-format NV12 \
  --duration-sec 1800

# 2) 资源指标采集（建议与采集测试同时间窗）
scripts/edge_baseline_metrics.sh \
  --duration-sec 1800 \
  --interval-sec 5
```

产物默认在 `data/edge_device/baseline/` 下：
- `capture_<timestamp>/camera_enumeration.log`
- `capture_<timestamp>/stream_test.log`
- `capture_<timestamp>/capture_summary.txt`
- `metrics_<timestamp>/metrics.csv`
- `metrics_<timestamp>/system_info.txt`
- `metrics_<timestamp>/metrics_summary.txt`

## 3. 摄像头枚举基线

| 项目 | 结果 |
| --- | --- |
| `/dev/video*` 枚举是否稳定 | `<pass/fail>` |
| 可用像素格式 | `<e.g. NV12 / YUYV / MJPG>` |
| 可用分辨率 | `<e.g. 1280x720 / 1920x1080>` |
| 可用 FPS 档位 | `<e.g. 15 / 25 / 30>` |
| 备注 | `<driver quirks / warm-up requirement>` |

## 4. 连续采集稳定性（30~60 分钟）

| 项目 | 结果 |
| --- | --- |
| 目标时长 | `<1800~3600 sec>` |
| 实际运行时长 | `<sec>` |
| 是否崩溃/中断 | `<yes/no>` |
| 是否持续掉流 | `<yes/no>` |
| 报错关键字 | `<none or error summary>` |
| 原始日志 | `<path to stream_test.log>` |

## 5. 资源基线（CPU/内存/NPU）

| 指标 | 结果 |
| --- | --- |
| CPU 平均占用 | `<xx.xx %>` |
| CPU 峰值占用 | `<xx.xx %>` |
| 内存平均占用 | `<xx.xx %>` |
| 内存峰值占用 | `<xx.xx %>` |
| 温度范围 | `<min~max C>` |
| NPU 频率（若可读） | `<value or N/A>` |
| NPU 负载（若可读） | `<value or N/A>` |

> 说明：若板端未暴露 NPU 指标文件，可标记为 `N/A`，但需在备注中说明检测路径和原因。

## 6. 验收结论（T13A）

- [ ] 摄像头节点可稳定枚举
- [ ] 分辨率/FPS/像素格式基线可复现
- [ ] 连续 30-60 分钟采集无崩溃/无持续掉流
- [ ] CPU/内存/NPU（若可读）指标有基线记录

结论：`<PASS / FAIL>`

## 7. 风险与后续

- 风险1：`<...>`
- 风险2：`<...>`
- 下一步（T13B）：协议冻结 event / heartbeat / command 字段。
