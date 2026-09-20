# 测试报告 (TEST_REPORT)

- 测试日期：2026-09-09
- 环境：Windows 10 · Python 3.10.6 · Node.js 24.10.0 · PyTorch 2.5.1+cu121 · NVIDIA RTX 3060 Laptop 6 GB
- 原则：**不伪造任何测试结果**；无法执行的项明确标注 `NOT TESTED`

---

## 1. 测试总览

| 套件 | 命令 | 结果 | 数量 |
| --- | --- | --- | --- |
| 后端（pytest） | `cd backend; python -m pytest -q` | **PASS** | **106 passed** |
| 前端单元测试（Vitest） | `cd frontend; npm test` | **PASS** | **37 passed**（6 文件） |
| 前端类型检查 | `cd frontend; npm run typecheck` | **PASS** | 0 error |
| 前端静态检查（ESLint） | `cd frontend; npm run lint` | **PASS** | 0 problems |
| 前端生产构建 | `cd frontend; npm run build` | **PASS** | 235 KB JS / 22.7 KB CSS |
| E2E（Playwright） | `cd frontend; npm run e2e` | **PASS** | **20 passed**（4 项目） |
| 成品检查（无头浏览器核对品牌/措辞/评测页） | `node scripts/presentation_check.mjs` | **PASS** | 18/18 检查 |
| 真实模型端到端冒烟 | `python scripts/smoke_real_model.py --samples 12` | **PASS** | 12/12 |
| 模型训练 | `python -m ml.train ...` | **PASS** | 12 epochs |
| 内部测试集评估 | `python -m ml.evaluate --split test` | **PASS** | n=270 |
| 模型优化基准 | `python -m ml.optimize_model --torchscript` | **PASS** | 见 MODEL_REPORT §9 |
| 外部测试脚本 CASE A/B | `python -m ml.evaluate_external ...` | **PASS** | 8/8 预测正确（模拟数据） |
| Docker Compose 配置 | `docker compose --env-file .env.tmp config` | **PASS** | exit 0 |
| Docker 构建 / 运行 | `docker compose build` / `up` | **NOT TESTED** | Docker daemon 未运行 |

## 2. 后端测试（106 passed）

> 最近一次复跑：作品集整理完成后重跑 `pytest -q` → 106 passed（含把数据集划分路径改为可移植相对路径后的回归）。

```
cd backend
..\.venv\Scripts\python.exe -m pytest -q
# 106 passed, 1 warning in 23.15s
```

| 文件 | 数量 | 覆盖内容 |
| --- | ---: | --- |
| `tests/test_auth.py` | 16 | 注册成功、重复邮箱/用户名、弱密码、校验错误契约、邮箱/用户名登录、错误密码、未知用户、退出、退出幂等、会话端点、受保护路由、CSRF 必需/通过、密码非明文且为 Argon2id |
| `tests/test_detections.py` | 40 | JPEG/PNG/BMP 成功、不保存历史、未认证、**缺少/错误 CSRF 被拒**、无效图片、截断 JPEG、伪造 MIME、不支持扩展名、超大文件、解压炸弹、空文件、路径穿越文件名、历史创建/列表/筛选/分页、IDOR 隔离、图片需认证、解密为 PNG、删除记录并删文件、删除需 CSRF、CSV 列与鉴权、CSV 按用户隔离、幂等键去重/按用户隔离/不同键、模型不可用 503、推理异常 500、DB 失败回滚删文件、孤儿清理、密文缺失报错、健康检查、模型信息、安全响应头、404 |
| `tests/test_security.py` | 22 | 错误契约形状（401/404/422，部分为参数化）、错误不泄露内部信息、**未捕获异常仍走 JSON 契约**、**/model/info 与 /health 不泄露文件路径**、日志脱敏（密码/令牌/密钥/base64）、服务端生成文件名、路径穿越拦截、密文不含 JPEG 魔数、EXIF 被剥离、Cookie HttpOnly/SameSite、无效会话、CSRF 不匹配、CORS 允许/拒绝来源、无效加密密钥、跨密钥无法解密、Argon2id、密码不外泄、并发注册冲突 |
| `tests/test_ml_pipeline.py` | 26 | transform 形状/确定性/灰度/归一化数值、审计统计、损坏图与重复检测、SHA/感知哈希稳定性、划分无泄漏且全覆盖、固定种子可复现、完整性校验（含跨类别同名不误报）、manifest 列、Dataset 输出、空 manifest 报错、模型前向、checkpoint 往返/缺失/损坏、ModelMeta 往返、非法架构、指标（完美/漏检/边界/ROC 端点/ECE/单类别不崩溃） |

## 3. 前端测试（37 passed）

> 本节数字更新于作品集整理时（新增 `/evaluation` 页的 5 个用例后，由 32 增至 37，文件由 5 增至 6）。

```
cd frontend
npm test        # 37 passed (6 files)
npm run typecheck  # 0 errors
npm run build      # dist/index.html 0.66 kB, CSS 22.65 kB, JS 235.36 kB
```

| 文件 | 数量 | 覆盖内容 |
| --- | ---: | --- |
| `src/test/ImageUploader.test.tsx` | 7 | 空态与可访问按钮、有效图片回调、非图片拒绝、超大文件拒绝、预览/文件信息/移除、服务端错误展示、禁用态 |
| `src/test/ResultCard.test.tsx` | 7 | 恶性结果渲染（倾向/置信度/概率条/模型版本）、良性文案、免责声明与校准提示常驻、禁止用语断言（"你患有皮肤癌/确诊/100%/无需就医/保证"）、概率条 aria-valuenow |
| `src/test/pages.test.tsx` | 5 | 登录失败错误提示、表单 label、历史空态、历史错误态、历史列表渲染与计数 |
| `src/test/format.test.ts` | 8 | 百分比/字节/时间格式化、中英文标签、非颜色符号、文件类型与大小校验 |
| `src/test/client.test.ts` | 5 | 错误契约解析、CSRF 头与 credentials、网络异常映射、multipart + 幂等键、图片 URL |
| `src/test/evaluation.test.tsx` | 5 | 评测页内外部双指标可见、外部未达标表述、恶性召回下降与 FN=137、泄漏检查与"未针对测试集重训"声明、真实曲线图与免责声明 |

## 4. E2E 测试（20 passed）

```
cd frontend
npm run e2e          # 自行启动 4173 预览服务器（/api 代理到后端），需后端已运行
# 20 passed (35.5s)
```

> 无需任何环境变量：`playwright.config.ts` 默认驱动 `http://localhost:4173` 并自动启动
> `vite preview`，`/api` 由预览服务器代理到 `http://127.0.0.1:8000`（同源 Cookie）。
> 可选覆盖：`E2E_BASE_URL`（传入 `127.0.0.1` 会被归一化为 `localhost`，因为 `vite preview`
> 只绑定该主机名）、`E2E_API_URL`、`E2E_NO_SERVER=1`（自带服务器时跳过自动启动）。

| 项目 | 浏览器 | 结果 |
| --- | --- | --- |
| chromium | Chromium 最新版 | ✅ 5 passed |
| firefox | Firefox 最新版 | ✅ 5 passed |
| webkit | WebKit（Safari 引擎） | ✅ 5 passed |
| mobile-chrome | Pixel 5 视口 | ✅ 5 passed |

> **条件说明**：每个项目的 5 个用例中，第 4、5 个属于"真实模型冒烟"分组，
> 当后端以 `MODEL_BACKEND=stub` 启动时会被 `test.skip()` 跳过（此时只会有 3 个用例执行）。
> 本次运行后端使用 `MODEL_BACKEND=auto` + 真实 `best_model.pt`，因此 20 个用例全部真实执行。

每个项目覆盖：

1. **完整 happy path**：注册 → 自动登录 → 上传 → 预览 → 检测 → 结果（倾向/置信度/免责声明/模型版本）→ 历史列表 → 详情（含解密历史图片）→ 第二次检测 → 勾选两条 → 对比页 → CSV 导出（真实下载）→ 个人中心改名 → 退出 → 受保护路由跳登录；
2. 非图片文件被前端拦截且不发请求；
3. 匿名访问受保护路由重定向登录；
4. **真实模型冒烟**：`/model/info` 断言 `architecture=resnet*`、`model_version` 不含 `stub`、`class_mapping={benign:0,malignant:1}`、`input_size=224`、`calibration=NOT IMPLEMENTED`；
5. **真实推理**：注册临时账号后上传真实 JPEG，断言概率和为 1、模型版本非 stub。

## 5. 真实模型端到端冒烟（PASS）

```
python scripts/smoke_real_model.py --samples 12
```

- 12 张**真实测试集图片**经 HTTP API 推理；
- 对每张图同时做一次**本地进程内前向推理**，比较 API 返回概率：

| 项目 | 结果 |
| --- | --- |
| 预测一致 | 12/12 |
| 概率最大偏差 | `0.00e+00` |
| 概率和 = 1 | 12/12 |
| 模型版本一致 | 12/12 |
| 免责声明存在 | 12/12 |
| 历史记录条数 | 12 |
| **样本准确率（12 张真实图）** | **91.7%（11/12）**，并设有 0.5 的"随机水平"下限断言 |
| 历史图片解密 | PNG 78,423 字节 ✅ |
| CSV 导出列 | 9 列，含 `malignant_probability` ✅ |
| API 端到端延迟 | min 45 ms / median 53 ms / max 504 ms |

报告：`artifacts/real_model_smoke.json`（`verdict: PASS`，`sample_accuracy: 0.9167`）。

> **该脚本主要验证"链路一致性"，同时设有准确率下限**：它逐张比对 API 返回概率与本地前向推理概率，
> 若模型整体失效（样本准确率 < 0.5）会直接判 FAIL；但少量错误仍可能通过一致性检查。
> 完整准确率由 `ml/evaluate.py`（内部测试集）与 `ml/evaluate_external.py`（外部测试集）负责衡量。
>
> 说明：该测试证明了**服务端预处理与训练/评估使用完全相同的代码路径**，
> 因此内部测试集指标对生产请求具有参考意义。

## 6. 模型与数据测试

| 项目 | 结果 |
| --- | --- |
| 数据集审计 | 1840 张，benign 1040 / malignant 800，损坏 0，重复 1 组，跨类重复 0 |
| 划分完整性 | PASS（SHA-256 / group / label+filename 三重交集均为 0） |
| 训练 | 12 epochs，best epoch 7，耗时 118 s |
| 内部测试集 | **Accuracy 92.96%**（n=270），恶性召回 93.97%，ROC-AUC 0.9828 |
| `TARGET >=90%` | **ACHIEVED** |
| 概率校准 | `NOT IMPLEMENTED` |
| 模型大小 / 加载时间 | 89.998 MB / 0.41 s（CPU） |
| 单张推理延迟 | 77.09 ms（CPU 中位）、CUDA 下更快（见 JSON） |
| TorchScript 导出 | 成功，与原始模型输出最大差 `0.00e+00` |
| 动态量化 | 体积几乎不变（-0.013 MB），延迟 -8%，准确率无变化 → 生产不用 |

## 7. 独立外部测试（2026-09-10 已完成，真实数据）

外部提供的外部测试数据目录（原始数据**只读**，未移动/重命名/删除；目录路径记录在
`artifacts/external_test/audit.json`，此处不写本机绝对路径）。

| 项目 | 结果 |
| --- | --- |
| 测试图片 | **797**（benign 400 / malignant 397，全部 224×224 RGB JPG，损坏 0） |
| 标签来源 | 目录结构（`benign\` / `malignant\`），无 labels.csv |
| 标签匹配 | 797 / 797（无缺失、无重复） |
| 与训练 / 验证 / 内部测试集 SHA256 重合 | **0 / 0 / 0**（无字节级泄漏） |
| **Accuracy** | **78.54%** |
| Precision（恶性） | 88.44% |
| **Recall（恶性）** | **65.49%** |
| Specificity | 91.50% |
| F1 | 75.25% |
| ROC-AUC / PR-AUC | 0.9079 / 0.8929 |
| 混淆矩阵 | TP=260 / TN=366 / FP=34 / FN=137 |
| 错误样本 | 171（FN 137 / FP 34）→ `artifacts/external_test/external_errors.csv` |
| 独立复核 | **PASS**（7/7：样本数、概率范围/和、argmax、混淆矩阵、指标重算） |
| 训练阶段 ≥90% 目标 | **未达成（NO）** |
| 模型是否被修改 | **NO**（SHA256 `9C385625…D164E8` 前后一致） |

**外部 vs 内部（n=270）**：Accuracy 92.96% → 78.54%（−14.42 pt）、Recall 93.97% → 65.49%（−28.47 pt）、
Specificity 92.21% → 91.50%（−0.71 pt）、ROC-AUC 0.9828 → 0.9079（−7.50 pt）。

> 差距集中在**恶性漏检**，Specificity 几乎不变 → 不是单纯阈值问题
> （阈值降到 0.3 时外部准确率也仅 80.93%，仅作分析、未应用于模型）。
> 由于缺乏采集设备、患者来源与病灶级元数据，**无法严格归因**，数据分布差异只是可能因素之一。
> 本轮**未重新训练、未微调、未调阈值、未将外部数据加入训练/验证**。
> 完整报告见 [`docs/ml/EXTERNAL_EVALUATION.md`](../ml/EXTERNAL_EVALUATION.md)；
> 项目来源的原始专项报告归档在 `docs/archive/project-origin/EXTERNAL_TEST_REPORT.md`
> （该目录属于未确认公开权限的来源材料，公开快照中不包含，见 `private-release-exclusions.md`）。

### 7.1 外部测试脚本的可用性验证（历史记录，数据到手前）

| 情况 | 命令 | 结果 |
| --- | --- | --- |
| A（无标签） | `python -m ml.evaluate_external --input <图片目录>` | 生成 `external_predictions.csv` ✅ |
| B（有标签） | `... --labels <labels.csv>` | accuracy/precision/recall/specificity/f1/roc_auc 全部输出 + 3 张图 ✅ |

> 那次用的是**内部测试集抽样的 8 张图**，只证明脚本两种模式可运行，**不代表外部评测成绩**。
> 真实外部评测结果见上方 §7 表格（已完成）。

## 8. 静态检查

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| Python 语法 | `python -m compileall backend/app ml scripts` | ✅ 无错误 |
| TypeScript | `npm run typecheck` | ✅ 0 error |
| 前端构建 | `npm run build` | ✅ 成功 |
| Docker Compose 语法 | `docker compose --env-file <tmp> config` | ✅ exit 0 |
| ESLint | `npm run lint` | ✅ 0 problems（作品集整理时补上 `frontend/.eslintrc.cjs`，规则集见该文件） |

## 9. 未测试项（NOT TESTED）

| 项目 | 原因 |
| --- | --- |
| Docker 镜像构建（`docker compose build`） | 本机 Docker daemon 未运行（`docker version` 报 cannot connect） |
| Docker 运行与容器健康检查 | 同上 |
| 独立外部测试集评估 | **已完成（2026-09-10）**：797 张，Accuracy 78.54%（未达 90%）；详见 §7 与 `docs/ml/EXTERNAL_EVALUATION.md` |
| 概率校准（temperature scaling） | 本次未实现（`CALIBRATION: NOT IMPLEMENTED`） |
| Hosted CI | 仓库无远程 CI 配置，**本地 PASS ≠ Hosted CI PASS**；ESLint 已于作品集整理时补齐配置并本地实测通过（见 §8） |
| 真实 HTTPS 环境下的 Cookie Secure | 本地为 HTTP 开发环境，未在生产 HTTPS 下验证 |
| 高并发压测（>10 并发） | 未做压力测试；仅验证了信号量限流代码路径 |
| 多实例部署 | 未测试（SQLite + 进程内单例适用于单实例） |

## 10. 失败与修复记录（本次开发过程中真实发生并已修复）

| 编号 | 问题 | 严重度 | 处理 |
| --- | --- | --- | --- |
| 1 | **`POST /detections` 缺少 CSRF 校验**（其他写操作都有），跨站 multipart POST 可被接受 | **High** | 端点加入 `CsrfProtected` 依赖；新增 2 个回归测试 |
| 2 | 未认证的 `/model/info` 把模型加载异常原文（含绝对路径）返回客户端 | **High** | 对外只暴露异常类型，原文仅写服务器日志；新增 2 个测试 |
| 3 | `aHash` 近重复检测过粗，导致 289 张不相关图片被并入同一泄漏组 | High | 改用 `dHash` 并限制**类别内**聚类 |
| 4 | 文件名跨类别重复（benign/953.jpg vs malignant/953.jpg）被误判为泄漏 | Medium | 完整性检查改为 `(label, filename)` |
| 5 | Windows DataLoader 多进程无法 pickle 动态生成的 Dataset 类 | High | 类改为模块级定义 |
| 6 | Windows GBK 控制台无法输出 `↳` 字符导致训练崩溃 | High | 改为 ASCII 并强制 UTF-8 输出 |
| 7 | 按 README 从 `backend/` 启动时 `ModuleNotFoundError: No module named 'ml'` | High | 新增 `app/_bootstrap.py` 自动加入项目根到 `sys.path` |
| 8 | `.env` 中相对模型路径随工作目录变化而失效 | Medium | 配置层解析相对路径（先 backend 再项目根） |
| 9 | `MODEL_WARMUP=false` 时模型永不加载 | Medium | 首次请求惰性加载（失败只尝试一次） |
| 10 | 未知用户登录时每次请求现算一次 Argon2 哈希（资源耗尽风险） | Medium | 预计算常量 dummy 哈希 |
| 11 | 路径穿越解析未显式拒绝 `..` | Medium | `_resolve()` 显式拒绝分隔符与 `..` |
| 12 | 移动端导航折叠导致 E2E 点击超时 | Low | E2E 增加菜单展开辅助函数 |
| 13 | 结果页断言文案与实际免责声明不一致 | Low | 断言改为实际文案 |
| 14 | 文档不实：重复图类别写错、训练耗时写错、Docker 卷路径写错、测试集使用表述过度 | Medium | 全部按实测数据更正（见 `MODEL_REPORT.md`、`DEPLOYMENT.md`） |
| 15 | **删除账号时先删图片文件、后提交数据库**，提交失败将导致记录指向不可读图片 | **High** | 改为「先提交数据库、后删文件」，并新增顺序断言测试 |
| 16 | 反向代理后登录限流以代理 IP 为键，所有用户共用同一桶 | Medium | uvicorn 加 `--proxy-headers --forwarded-allow-ips`，并优先取 `X-Forwarded-For` |
| 17 | `Image.MAX_IMAGE_PIXELS = None` 全局关闭 Pillow 炸弹防护 | Medium | 改为有限值（`max_image_pixels * 2`） |
| 18 | 解压炸弹测试只构造头部、未走真实解码路径 | Medium | 新增真实可解码的 100 万像素 PNG 炸弹测试 |
| 19 | `torch.load(weights_only=False)` 存在 pickle 反序列化风险 | Medium | 改为 `weights_only=True`（实测 checkpoint 可正常加载） |
| 20 | 详情页重复加载会泄漏 object URL | Low | 替换前先 `revokeObjectURL` |
| 21 | CSV 导出存在公式注入风险（文件名以 `=`/`+`/`-`/`@` 开头） | Low | 导出前加 `'` 前缀中和 |
| 22 | 冒烟测试不校验准确率，模型全错也 PASS | Medium | 增加 0.5 随机水平下限断言（实测 91.7%） |
| 23 | 模型元数据 `test_metrics` 为空，模型文件不自描述 | Low | `ml/evaluate.py --update-model-meta` 写回实测指标 |
| 24 | 数据集发现逻辑硬编码本机绝对路径 | Low | 改为 `DATASET_ROOT` 环境变量 + 项目根相对路径 |

> 第 1、2 项由**独立审查**发现（审查中提出的"未捕获异常绕过 JSON 契约"经实测不成立，
> 已补充回归测试锁定该行为）；第 3–9、11 项在开发过程中通过真实运行/测试发现；
> 第 10 项由独立审查提示后修复；第 12–14 项为一致性修正。

## 11. 复现全部测试

```powershell
# 1) 后端
cd backend; ..\.venv\Scripts\python.exe -m pytest -q

# 2) 前端单元测试 + 构建
cd ..\frontend; npm test; npm run typecheck; npm run build

# 3) 启动后端（终端 1）
cd ..\backend; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# 4) 启动前端预览（终端 2）
cd ..\frontend; npm run preview -- --port 4173

# 5) E2E（终端 3）
cd frontend
$env:E2E_BASE_URL='http://localhost:4173'; $env:E2E_NO_SERVER='1'
npx playwright test

# 6) 真实模型冒烟
cd ..; .\.venv\Scripts\python.exe scripts\smoke_real_model.py --samples 12
```
