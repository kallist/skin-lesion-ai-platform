# TEST PROMPT — 测试提示词

> 本文件是测试阶段实际使用的指令整理稿。

## 通用原则

- 禁止伪造测试结果；无法执行的测试项写 `NOT TESTED`，不要写 PASS。
- 测试不得依赖下载数 GB 的数据集；使用合成小图与临时目录。
- 本地 PASS 不等于 Hosted CI PASS。

## ML 测试

Dataset loading、Corrupted image、Transform shape（断言 `[3,224,224]`）、Class mapping、
Split integrity（train/val/test 三重交集为 0）、Duplicate detection、Model forward、
Prediction probability（和为 1）、Checkpoint loading（含损坏文件）、
Inference preprocessing parity（训练/评估/服务三处一致）。

## 后端测试（pytest）

Register success、Duplicate email、Login success、Wrong password、Logout、Protected route、
Valid JPEG、Valid PNG、Invalid image、Fake MIME、Oversized image、Inference success、
Inference failure、History creation、History listing、History ownership、
Unauthorized image access、CSV export、Idempotency、Database failure、Model unavailable。

补充安全测试：错误契约形状、日志脱敏、路径穿越、密文落盘、EXIF 去除、CSRF、CORS、
会话 Cookie 属性、密码哈希算法、密钥错误处理。

## 前端测试

unit/component tests 覆盖：Upload 组件、Validation、Result 渲染、History 状态、
Login 表单、API failure、Disclaimer。

## E2E（Playwright）

至少覆盖完整 happy path：
Register → Login → Upload image → Preview → Detect → Result → History → History detail → Logout。

E2E 中允许使用 deterministic test inference adapter 检查 UI 流程，但**必须另外执行
REAL MODEL SMOKE TEST**：使用实际训练完成的 `best_model.pt`，至少对真实图片执行一次
Frontend/API → preprocessing → PyTorch model → prediction → response。不能全部测试都依赖 mock。

## 浏览器兼容

尽量覆盖 Chromium、Firefox、WebKit（对应 Chrome/Edge、Firefox、Safari）。
若环境无法完整执行某浏览器，最终报告写 `NOT TESTED`，不要写 PASS。

## 必须运行的验证命令

```
后端：pytest
前端：npm test、npm run build
E2E：Playwright
ML：dataset audit、training、evaluation、real inference smoke
静态：python compile / lint、frontend lint（如配置）
Docker：docker compose config；若运行时可用则 docker compose build / up + health check
```

任何无法执行的项目写 `NOT TESTED`。

## 模型验收报告

必须报告 Dataset size（train/val/internal test）、Best model、Epochs、Best validation metric、
Internal test 的 Accuracy/Precision/Recall/Specificity/F1/ROC-AUC，以及明确的
`TARGET >=90%: ACHIEVED / NOT ACHIEVED`。不要模糊表达。

## WebApp 验收清单

注册、登录、图片上传、Drag & Drop、图片预览、224×224 preprocessing、Real PyTorch inference、
Benign/Malignant result、Confidence、Disclaimer、History、Image history、Compare、CSV export、
Profile、Authorization isolation、Responsive layout、Error handling。

## 明日测试验收

`data/external_test/` 目录、`evaluate_external.py`、无标签预测 CSV、有标签评估、
`docs/testing/EXTERNAL_TEST_RUNBOOK.md` 全部就绪，并明确告诉用户"拿到测试图片后需要执行什么"，
且**不要求重新训练模型**。
