# Privacy & IP Audit — Public Release

公开仓库前的审计记录。结论与待确认项都在这里，没有"看起来没问题"这种含糊表述。

审计脚本：[`scripts/audit_public_release.py`](../../scripts/audit_public_release.py)（可重复运行）。
**当前实测结果：`AUDIT: PASS (0 blocking, 19 review, 5 info)`** —— review 类为
占位符/测试夹具/历史证据路径，逐条列在脚本输出的 `PATH_REVIEW_ALLOWLIST` 与本文件第 3 节。

> 这份记录本身也经历过一次"自我审计失败"：初版写的是「exit 0 = 无阻断项」，但随后重新生成数据报告时，
> 报告生成器把本机绝对路径又写了进去，脚本实测返回 3 个阻断项。根因已修（生成器现在输出
> `data/raw` 这样的仓库相对根目录），并且这一条留在本节作为记录——**声称"已审计"必须配上脚本的实际输出**。

---

## 1. 仓库实际发布内容

| 项目 | 状态 |
| --- | --- |
| 受版本控制文件数 | 254 |
| 受控文件总大小 | 约 2.4 MB（含 12 份 DOCX/PDF 交付文档） |
| 训练数据集（1840 张图片） | **未提交**（`data/raw/`、`数据/` 均在 `.gitignore` 中；本地存在，公开 clone 不会包含） |
| 外部测试数据（797 张图片） | **未提交**（`data/external_test/` 被忽略；只保留统计与逐张哈希清单） |
| 模型权重 `models/*.pt` | **未提交**（`.gitignore` 排除；公开仓库需按 README 重新训练生成） |
| 用户数据库 `backend/data/app.sqlite3` | **未提交**，且已在打包前从本地删除 |
| 加密上传图片 `backend/data/encrypted_uploads/*` | **未提交**，且已在打包前从本地清空 |
| 运行日志 `logs/*`、启动器状态 `.runtime/*` | **未提交**，且已在打包前清空 |
| 真实 `.env`（含 `SESSION_SECRET` / `IMAGE_ENCRYPTION_KEY`） | **未提交**（仅 `.env.example` 占位符） |
| 提交的划分清单 `data/manifests/*.csv` | 已改为**仓库相对路径**（`data/raw/<class>/<file>`），不再包含本机绝对路径 |
| 自动生成的 `docs/ml/DATASET_REPORT.md` | 数据集根目录渲染为 `data/raw`（生成器不会再写回本机路径） |

## 2. 密钥与凭据扫描

结果：**无阻断项**。扫描分两层：工作区已跟踪文件（`scripts/audit_public_release.py`）
与**全部 git 历史 blob**（`scripts/audit_history.py`，覆盖 `--all` 可达对象）。

工作区扫描检查项包括：`SESSION_SECRET=` / `IMAGE_ENCRYPTION_KEY=` 的实际取值、
AWS access key、GitHub token、`sk-` 形式 API key、私钥块、硬编码口令字面量。

历史扫描结果（686 个对象 / 380 个文本 blob）：**未发现任何真实凭据、密钥或个人数据**。
唯一的命中是测试夹具里的合成密钥：

| 位置 | 内容 | 判定 |
| --- | --- | --- |
| `backend/tests/test_security.py`（历史 blob，当前内容同样如此） | 合成密钥（base64 解码后为 `foobarbazqux` 开头的假字符串） | **合成值**：加密测试使用的假密钥，不是项目密钥 |

复核后的 3 条工作区命中均为**占位符或测试夹具**，不含真实凭据：

| 文件 | 内容 | 判定 |
| --- | --- | --- |
| `.env.example` | 变量名与空占位符 | 可公开 |
| `backend/tests/test_auth.py` | 测试用口令字面量（如 `Str0ngPass!`） | 可公开 |
| `backend/tests/test_security.py` | 测试用临时加密密钥（上表） | 可公开（不是项目密钥） |

补充说明：本项目历史上出现过「检测上传接口缺少 CSRF 强制」「模型加载失败泄露模型路径」两个真实缺陷，
均在评审环节（同一 Agent 运行内按独立角色做的评审 pass，不是第三方人工评审）中发现并修复，
见 [`AI_ASSISTED_DEVELOPMENT.md`](AI_ASSISTED_DEVELOPMENT.md)。

## 3. 个人身份信息（PII）

结果：**无阻断项**。

- 未发现手机号、身份证号、真实姓名、学号；
- 唯一出现的邮箱是代码/文档里的合成地址（`*@example.com`）与 `frontend/package-lock.json`
  中 npm 官方仓库元数据里的第三方维护者地址，二者都不属于项目成员；
- 归档材料中的抬头表仍保留空白的模板行（姓名/学号/指导教师等栏目），**没有任何真实填写内容**；
  这些文件名与栏目本身会暴露"这是校内交付材料"，是否需要一并移出公开范围见第 7 节；
- 截图中的演示账号是每次运行时随机生成的（`demo<timestamp>`），不是真实账号；
  `docs/assets/screenshots/screenshots.json` 已改为只记录命名规则，不再写入具体账号。

**机器路径**：生成型 artifact（划分清单、`models/model_meta.json`、
`artifacts/external_test/audit.json`、`docs/ml/DATASET_REPORT.md`）中的本机绝对路径均已清除，
且**生成器已同步修复**（报告现在渲染 `data/raw` 这样的仓库相对根目录，不会在下次生成时把路径写回来）。
保留绝对路径的位置仅限于**历史证据类**文档与脚本示例（外部测试数据目录来源、迁移记录、
脚本参数示例），完整清单由审计脚本的 `PATH_REVIEW_ALLOWLIST` 列出——
它们指的是项目外部的数据目录，不含任何个人信息。

## 4. 数据集与图片的公开权利

| 材料 | 当前处理 | 状态 |
| --- | --- | --- |
| 训练数据集（1840 张，benign/malignant 目录） | 不入库，仅保留划分清单与统计 | **REVIEW REQUIRED**：需确认数据提供方的再分发授权 |
| 外部测试数据（797 张） | 不入库，仅保留指标、逐张哈希与错误样本清单 | **REVIEW REQUIRED**：同上 |
| 模型权重（ResNet50，94 MB） | 不入库 | **REVIEW REQUIRED**：权重可视为训练数据衍生物，公开前需确认数据授权 |
| README 截图中的输入图片 | 使用 `docs/assets/demo/` 下程序化生成的**合成示意图** | CLEAR：非真实病例、无第三方权利 |
| 评测曲线与混淆矩阵图 | 由本项目的评测脚本生成，不含原始图片 | CLEAR |

刻意做的一步：**README 与文档不再使用数据集里的真实病变照片**，
因此公开仓库里不存在"需要为图片版权做判断"的内容；界面与推理仍然是真实的。

## 5. 校企合作相关材料与品牌

| 项目 | 处理 | 状态 |
| --- | --- | --- |
| 广州泰迪智能科技有限公司的表述 | 统一为「校企联合 AI 应用实习实践项目，由广州泰迪智能科技有限公司相关人员参与项目指导与实践」；明确写出**不是商业产品 / 不是生产系统 / 未在医疗机构上线** | CLEAR（表述准确、无商业主张） |
| 公司 Logo | **未使用**（仓库中不存在公司 Logo 文件，README、前端与文档都没有引入） | CLEAR |
| 前端页面 / 页脚 | 仅文字说明，无公司标识 | CLEAR |
| 学校任务书与交付文档（`docs/archive/project-origin/`、`deliverables/docs/`、根目录任务书 PDF） | 保留作为项目来源归档 | **REVIEW REQUIRED**：学校/企业是否允许公开这些过程材料 |

> **BRAND USAGE REVIEW REQUIRED**：即使项目背景属实，公司名称的公开使用范围
> （尤其是是否允许在公开仓库、简历与社交平台中出现）仍建议由相关方确认一次。
> 当前做法是只使用文字说明、不使用任何 Logo 或视觉标识。

## 6. 隐私与合规边界（写入文档的事实）

- 本项目**不是医疗器械**，未取得任何认证，也没有临床验证数据；
- 模型输出不能替代专业医生诊断，外部测试中仍有 137 例恶性样本被漏判；
- 面向用户的免责声明在首页、检测页、结果卡、关于页常驻，不可关闭；
- 前端组件测试把「确诊 / 你患有皮肤癌 / 100% / 无需就医 / 保证」等禁用词写成断言，
  防止后续改动引入误导性表述。

## 7. 发布决策记录（2026 年作品集整理阶段确定）

前三项已由项目所有者决定并落地，后两项属于操作注意事项：

| # | 事项 | 决定 | 落地方式 |
| --- | --- | --- | --- |
| 1 | 数据集与模型权重是否公开 | **都不入库**（维持原状） | 仓库只保留划分清单、统计与指标 artifact；README 说明如何重新训练生成权重 |
| 2 | 项目来源材料是否公开 | **公开快照中排除** | 快照生成时移除需求文件 PDF、`deliverables/docs/`、`docs/archive/project-origin/`；工作仓库与历史完整保留，授权确认后可重新生成包含它们的快照 |
| 3 | 仓库 LICENSE | **MIT** | 新增 `LICENSE`（MIT 正文 + 授权范围说明：不覆盖数据集/权重/派生图片），README 增加 License 段与 badge |
| 4 | 公司名称使用范围 | 仅文字说明，未使用任何 Logo | 保留；如需在简历/社交平台使用建议再确认一次 |
| 5 | Git 历史 | **不直接公开历史** | 历史中需求文件 PDF（blob `4360711cd6`）与 `deliverables/docs/*.pdf` 全部版本仍可达，因此改为用干净快照发布（见下表） |

> 第 2 项意味着：**公开快照不含任何学校/企业过程材料**，`docs/archive/` 只存在于私有工作仓库。
> 公共文档中指向这些材料的链接仅存在于工作仓库版本；快照生成后会在快照内重新运行
> `check_links.py` 校验，确保公开版本没有断链。

| 快照状态 | 结果 |
| --- | --- |
| 生成脚本 | `scripts/build_public_snapshot.py`（复制当前工作区，拒绝纳入权重/数据集/数据库/`.env`，并校验只含 1 个提交） |
| 提交数 / 跟踪文件 | **1 个提交 / 259 个跟踪文件** |
| 快照内 `audit_public_release.py` | **PASS（0 blocking）** |
| 快照内 `check_links.py` / `check_final_numbers.py` / `check_metrics_consistency.py` | OK / PASS / OK |
| 仍含待确认材料 | 是（第 2 条列出的来源材料），确认后再推送 |

详细清单与排除建议见仓库根目录 [`private-release-exclusions.md`](../../private-release-exclusions.md)。
