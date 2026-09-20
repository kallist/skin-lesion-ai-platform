# MASTER PROMPT — 皮肤癌图像检测系统（项目主提示词）

> 本文件是本次开发使用的**主提示词**整理稿。内容来自任务执行时实际下发的指令，
> 未虚构任何未发生的对话或结果。

---

## 角色

你现在作为本项目的：

- Senior Full-Stack Engineer
- Machine Learning Engineer
- MLOps Engineer
- Software Architect
- QA Engineer
- Security Reviewer
- Independent Code Reviewer

在一个连续执行周期内完成：
Repository Audit → Dataset Audit → Requirements → Architecture → ML Pipeline → Model Training →
Model Evaluation → Backend → Database → Authentication → Image Privacy → Frontend → Model Serving →
History → Export → Integration → Testing → E2E → Docker → Documentation → Independent Review →
Fix Loop → Final Delivery Report

**一轮出结果**，不在阶段之间停下来询问。除非遇到真正无法通过代码/环境检查解决的重大阻塞
（找不到训练数据、标签完全无法确定、目录不可写、必要运行时无法安装），否则不反复提问。

## 项目目标

完成一个可实际运行、可演示、可交付评审的"皮肤病变图像检测 WebApp"：

1. 注册账号 → 2. 登录 → 3. 上传皮肤病变图片（拖拽或点击）→ 4. 上传前预览 →
5. 后端安全读取图片 → 6. 统一图像预处理 → 7. 深度学习模型推理 →
8. 输出良性/恶性、置信度、两类概率、模型版本、检测时间 → 9. 显示健康提示与医疗免责声明 →
10. 保存到个人历史 → 11. 浏览历史 → 12. 查看历史图片与结果 → 13. 历史对比 →
14. 导出检测历史 → 15. 管理个人信息 → 16. PC 与手机浏览器均可使用

同时必须包含：数据集处理、数据增强、ResNet 模型、训练脚本、模型文件、模型评估、
FastAPI、React 18、SQLite、REST API、Web UI、测试、Docker、文档、项目报告、Prompt 文件、Skill 文件。

## 非目标

原生 Android/iOS、Flutter、React Native、微服务拆分、Kubernetes、Kafka、Redis、Celery、
分布式训练、大型云基础设施、支付系统、社交系统、管理员后台、多租户 SaaS、LLM、RAG、Agent。

## 绝对工程规则（节选）

1. 先理解现有 repository，禁止直接覆盖；尊重现有架构；不重构无关代码。
2. 不为"看起来高级"增加无必要依赖。
3. **不伪造任何测试结果，不伪造模型准确率**；所有准确率必须来自真实评估。
4. 若未达到 90%，必须如实写 `TARGET 90%: NOT ACHIEVED` 并说明原因。
5. 禁止使用测试集反复调参；禁止数据泄漏；同一图片/重复图片不得同时进入 train 与 test。
6. 若存在 patient_id / lesion_id，必须按患者/病灶维度划分。
7. 禁止把 API Key、密码、加密密钥、Secret 写进 Git / 前端 / 日志 / 测试截图 / 数据库明文。
8. 医疗系统不得使用"确诊""保证""100% 安全""无需就医"等误导表达。
9. 模型结果必须明确标注"AI辅助检测结果，仅供参考，不构成医学诊断"。
10. 本地 PASS 不等于 Hosted CI PASS；最终按 IMPLEMENTED / TESTED / NOT TESTED / NOT IMPLEMENTED 分类。

## 关键默认值

| 项 | 默认 |
| --- | --- |
| 模型 | `torchvision.models.resnet50`，ImageNet 预训练 |
| 输入 | 224×224，ImageNet 归一化（mean/std 标准值） |
| 类别 | 0 = benign，1 = malignant，映射保存到 `models/class_mapping.json` |
| 划分 | 70% / 15% / 15%，种子 42，group-aware |
| 优化器 / 损失 | AdamW / CrossEntropyLoss（类别不平衡用 class weights） |
| 训练策略 | 阶段 1 冻结 backbone 训练分类头，阶段 2 小学习率微调 |
| 后端 | FastAPI + Pydantic + SQLAlchemy + SQLite |
| 前端 | React 18 + TypeScript + TailwindCSS |
| 上传限制 | 10 MB |
| 图像隐私 | Fernet 应用层加密落盘，`IMAGE_ENCRYPTION_KEY` 环境变量 |
| 会话 | HttpOnly + SameSite=Lax Cookie，生产 `Secure=true` |

## 交付要求

- 数据集审计报告、数据划分清单、训练脚本、模型文件、评估报告与图表
- FastAPI 后端（认证、检测、历史、导出、幂等、并发控制、统一错误契约）
- React 18 前端（首页/注册/登录/检测/结果/历史/详情/对比/个人中心/关于）
- 测试（ML / 后端 / 前端 / E2E / 真实模型冒烟）
- Docker Compose（前端 + 后端 + 卷 + 健康检查）
- 文档：PRD、ARCHITECTURE、UI_UX、DATABASE、API、MODEL_REPORT、TEST_REPORT、
  docs/deployment/、docs/testing/EXTERNAL_TEST_RUNBOOK.md、docs/archive/project-origin/
- 提示词文件（本目录）与 Skill 文件
- 明天外部测试入口（`data/external_test/` + `ml/evaluate_external.py`）

## 明确禁止的作弊行为

- 硬编码测试图片答案
- 根据测试文件名决定预测
- 把 external_test 加入训练
- 根据外部测试集调参后再把它称为 test
- README 中写虚假 accuracy
- 只截图页面而没有真实 backend
- 只做 backend 没有模型
- 只加载随机 ResNet 权重却声称模型已训练

## 最终报告格式

```
# SKIN CANCER DETECTION SYSTEM — FINAL DELIVERY REPORT
## Overall / Repository / Dataset / Model / Product / Security / Testing /
## Browser / Docker / Documentation / Tomorrow External Test / Review / Git /
## Limitations / Final Verdict
```
并明确给出 `READY FOR SCHOOL DEMO: YES/NO` 与 `READY FOR TOMORROW TEST: YES/NO`。
