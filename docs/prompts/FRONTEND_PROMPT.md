# FRONTEND PROMPT — 前端与 UI 提示词

> 本文件是前端实现阶段实际使用的指令整理稿。

## 技术栈

React 18 + TypeScript。UI 优先 TailwindCSS；除非已有 Ant Design，否则不要同时引入两个大型 UI 体系。
目标风格：专业、医疗科技感、简洁、可信、现代、响应式。**不要用默认模板风格堆砌页面。**

## 页面（至少）

1. **Landing**：项目名称、AI 辅助皮肤病变识别、简短功能介绍、医疗免责声明、Login / Start Detection
2. **Register**
3. **Login**
4. **Detection**：拖拽上传、点击上传、预览、文件信息、Detect 按钮、Loading 状态
5. **Result**：良性倾向 / 恶性倾向（可附英文 Benign / Malignant）、置信度百分比、
   Benign x% / Malignant y%，并注明"模型置信度不代表临床诊断概率"
6. **History**：列表、时间、缩略图、预测结果、confidence、detail 入口
7. **History Detail**：展示以前的图片与结果
8. **Compare**：选择两条历史记录，并排比较图片、预测、confidence、日期
9. **Profile**
10. **About / Disclaimer**

## 结果文案（强制）

禁止写"你患有皮肤癌"。

- 恶性："模型检测结果倾向于恶性风险。该结果不能替代医生诊断，建议尽快由皮肤科专业人员进一步评估。"
- 良性："模型检测结果倾向于良性，但 AI 检测不能完全排除风险。如皮损持续变化、出现不适或你仍有疑虑，建议咨询皮肤科医生。"
- 页面明显位置长期显示："本系统仅作为皮肤健康辅助自检工具，检测结果仅供参考，不能替代专业医生诊断。"

## UX 细节

- Upload：drag state、invalid type、oversized file、preview、remove image、replace image
- Inference：idle / uploading / processing / success / error，防止重复点击
- 移动端：按钮可触控、图片不超出屏幕、表格转 card
- Desktop：结果与图片可双栏展示
- 实现 loading skeleton、empty history state、error state、confirmation dialog

## 无障碍

语义化 HTML、button label、form label、键盘导航、alt text、focus state、合理对比度。
**不能只依赖颜色**判断 benign/malignant，必须有文字。

## API 使用

- 前端**不得自行计算 prediction**，标签映射来自 `GET /api/v1/model/info`；
- 所有请求 `credentials: 'include'`；
- 写操作自动带上 `X-CSRF-Token`（读取 `csrf_token` Cookie）；
- 上传接口带 `Idempotency-Key`，网络重试不产生重复记录；
- 统一处理后端错误契约并显示 `error.message`。

## 测试

至少覆盖：Upload 组件、校验、Result 渲染、History 状态、Login 表单、API 失败、Disclaimer。
E2E 覆盖完整 happy path：Register → Login → Upload → Preview → Detect → Result → History →
History detail → Logout。
