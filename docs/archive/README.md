# 项目来源材料（公开版本中不包含）

这个目录在**私有工作仓库**中保存项目的原始来源材料：需求文件、综合报告、专项 PRD、项目总结报告、
使用说明书、验收对照表、外部测试报告、指标来源说明与交付说明。

**公开版本不包含这些文件**：它们的公开权限尚未由相关方确认，因此公开快照在生成时会排除
`docs/archive/project-origin/`。你在公开仓库里看到的只有这个说明文件。

排除范围与理由记录在 [`../../private-release-exclusions.md`](../../private-release-exclusions.md)
与 [`../../docs/engineering/PRIVACY_AND_IP_AUDIT.md`](../../docs/engineering/PRIVACY_AND_IP_AUDIT.md)；
如果相关方确认可以公开，重新生成快照时加 `--keep-origin-material`
（见 `scripts/build_public_snapshot.py`）即可把这些材料包含进来。

## 当前的公开文档在哪

| 主题 | 位置 |
| --- | --- |
| 需求、页面与交互设计 | [`../product/`](../product/) |
| 架构、接口、数据库、AI 辅助开发、隐私审计 | [`../engineering/`](../engineering/) |
| 数据集审计、模型报告、独立外部评测 | [`../ml/`](../ml/) |
| 测试报告与外部评测操作手册 | [`../testing/`](../testing/) |
| 部署与运维 | [`../deployment/`](../deployment/) |
| 简历文案、面试口径、工程复盘 | [`../career/`](../career/) |
| 真实界面截图与架构图 | [`../assets/`](../assets/) |
