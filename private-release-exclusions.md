# Private Release Exclusions

公开仓库发布前的排除清单。记录**已排除**的材料、**仍需授权确认**的材料，
以及建议在公开版本中如何处理。审计过程见
[`docs/engineering/PRIVACY_AND_IP_AUDIT.md`](docs/engineering/PRIVACY_AND_IP_AUDIT.md)。

清单中没有任何内容被删除——排除只意味着「不进入公开发布范围」。

---

## A. 已排除，且公开 clone 中不存在

| 材料 | 位置 | 排除方式 |
| --- | --- | --- |
| 真实环境变量（`SESSION_SECRET`、`IMAGE_ENCRYPTION_KEY`） | `backend/.env` | `.gitignore`（仅保留 `.env.example` 占位符） |
| 用户数据库 | `backend/data/app.sqlite3`（含 WAL/SHM） | `.gitignore`，且在打包前已从本地删除 |
| 加密上传的皮肤图像 | `backend/data/encrypted_uploads/*.enc` | `.gitignore`，且在打包前已清空 |
| 运行日志 | `logs/*.log` | `.gitignore`，打包前已清空 |
| 启动器运行状态（PID/绝对路径） | `.runtime/*` | `.gitignore`，打包前已清空 |
| 训练数据集（1840 张） | `data/raw/`、`数据/` | `.gitignore`（本地保留供复现训练） |
| 外部测试数据（797 张） | `data/external_test/`、项目外的验证数据目录 | `.gitignore` + 从不提交 |
| 模型权重（ResNet50 三个 `.pt`，约 282 MB） | `models/*.pt` | `.gitignore`（由训练脚本重新生成） |
| 外部测试只读暂存副本 | `artifacts/external_test/staging/` | `.gitignore` |

## B. 公开快照中已排除（2026 年作品集整理阶段决定）

项目所有者已决定：**公开快照只包含代码、工程文档与截图，不包含项目来源材料**。
下列材料仍完整保留在私有工作仓库与其历史中，只是不进入公开发布范围；
授权确认后可随时重新生成包含它们的快照（`--keep-origin-material`）。

| 材料 | 位置 | 处理 |
| --- | --- | --- |
| 项目需求文件 PDF | 根目录 `皮肤癌图像检测系统项目任务书V1.0.0.pdf` | 快照中排除 |
| 学校交付文档（Markdown） | `docs/archive/project-origin/**`（综合报告、PRD、总结报告、使用说明书、验收对照表、交付说明、外部测试报告、指标来源） | 快照中排除 |
| 交付文档正式版（DOCX + PDF，12 份） | `deliverables/docs/**` | 快照中排除（体量约占仓库 2.4 MB 的绝大部分） |

> 影响与处理：公共文档中原本指向 `docs/archive/` 的链接在快照里会变成无效目标，
> 因此快照生成后会在快照内重新运行 `scripts/check_links.py`；
> 若出现断链，需要把相关链接改写为「资料未包含在公开版本」的说明。
> 当前快照已验证：**无断链**。

## B2. 已确认无需授权的项目（已入库，按现状公开）

| 材料 | 说明 |
| --- | --- |
| 逐张哈希与错误样本清单 | `artifacts/external_test/sha256.csv`、`external_errors.csv`：不含图像像素，仅文件名与哈希／预测，且外部数据本身不入库 |
| 训练数据集元信息 | `data/manifests/*.csv`（文件名/SHA256/分组）、`docs/ml/DATASET_REPORT.md`：仅清单与统计，不含图像 |
| 评测曲线与混淆矩阵图 | 由本项目脚本从预测结果生成，不含原始图片 |
| 公司名称的文字表述 | 已统一为校企联合实习实践表述，且明确不是商业产品；未使用任何 Logo（如需在简历/社交平台使用建议再确认一次） |
| 数据集与模型权重 | 决定维持**不入库**；README 说明复现训练方式 |

## C. 发布步骤（三项决策已确定，可直接执行）

决定记录：① 数据集与模型权重**都不入库**；② 公开快照**排除**项目来源材料；③ LICENSE 采用 **MIT**
（已新增 `LICENSE`，README 增加 License 段与 badge）。

```powershell
# 1) 生成公开快照（默认排除项目来源材料，只含代码 / 工程文档 / 截图）
.\.venv\Scripts\python.exe -X utf8 scripts\build_public_snapshot.py
#    若日后确认来源材料可公开，用 --keep-origin-material 重新生成即可

# 2) 在快照内做发布前检查（脚本已自动校验收录与提交数，这里再跑一遍内容检查）
cd ~/portfolio-release
..\.venv\Scripts\python.exe -X utf8 scripts\audit_public_release.py   # 期望 PASS (0 blocking)
..\.venv\Scripts\python.exe -X utf8 scripts\check_links.py            # 期望 [OK] 无断链

# 3) 推送到 GitHub
git remote add origin https://github.com/<user>/skin-lesion-ai-platform.git
git push -u origin main
```

> **绝不要直接 push 现有仓库历史**：实测确认需求文件 PDF（blob `4360711cd6`）与
> `deliverables/docs/*.pdf` 的全部历史版本仍可被 `git rev-list --objects --all` 检出。
> 历史中未发现真实凭据泄漏（见 `docs/engineering/PRIVACY_AND_IP_AUDIT.md` 第 2 节）。
> 如确实需要从现有历史发布，必须先重写历史（`git filter-repo`）而不是直接推送。
若日后确认来源材料可以公开，用 `--keep-origin-material` 重新生成快照即可；
想先检查再推，可以先 `git clone ~/portfolio-release.git <check-dir>`。

## D. 确认无需排除的项目（供参考）

- `.env.example`：只有变量名与占位符；
- `backend/tests/**`：测试口令与临时密钥均为合成值；
- `docs/assets/demo/*.jpg`：程序化生成的合成示意图，非真实病例；
- `docs/assets/screenshots/**`：真实系统截图，输入图像为上述合成图，账号为运行时随机生成；
- `artifacts/*.json`、`artifacts/**/*.png`：本项目评测脚本产出的指标与图表；
- `frontend/package-lock.json`：第三方依赖元数据（含 npm 上的公开维护者邮箱）。
