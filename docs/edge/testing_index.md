# Edge Testing Split Index

## 说明
- 源文档保留：`/home/kkk/Project/nano-vision-butler/测试.md`
- 本索引用于把超长测试文档按“单文档单职责”拆分，便于执行与复盘。

## 拆分结果
- `docs/edge/model_selection_strategy.md`：主检测模型选型与上线顺序。
- `docs/edge/model_ab_test_matrix.md`：A/B 测试分组、指标、执行命令、记录模板。
- `docs/edge/test_necessity_analysis.md`：为什么必须分层测试，以及不测的风险。
- `docs/edge/light_edge_heavy_backend_refactor.md`：轻前端重后端改造方案与第一阶段落地项。

## 使用顺序
1. 先读 `model_selection_strategy.md`，确定首发模型和备选。
2. 再按 `model_ab_test_matrix.md` 跑测试并填表。
3. 最后用 `test_necessity_analysis.md` 对照验收，判断测试是否覆盖计划书目标。
