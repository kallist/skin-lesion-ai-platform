---
name: skin-lesion-ai-webapp
description: 端到端构建"医学图像二分类（如皮肤病变良性/恶性）Web 应用"的可复用流程：数据集审计、泄漏安全划分、ResNet 迁移学习训练与评估、FastAPI 模型服务、医疗免责声明、独立外部测试集评估、隐私与安全加固。适用于需要"训练真实模型 + 提供可运行 Web 服务 + 可复核文档"的医学影像项目。
---

# SKILL — Medical Image Classification WebApp (皮肤病变识别)

## When to use（何时使用）

在以下情况加载本 Skill：

- 需要基于图像数据集训练二分类模型（尤其是医学/皮肤影像），并交付可运行的 Web 应用；
- 需要**科学划分数据集**并证明没有数据泄漏；
- 需要把 PyTorch 模型接入 FastAPI 并处理并发、隐私、失败回滚；
- 需要为项目评审准备可复现的评估报告与独立外部测试入口；
- 需要在医疗场景中正确使用免责声明与措辞。

**不适用**：多标签/分割/检测任务、需要 DICOM 与临床 PACS 集成的生产系统、
需要患者级划分但数据中确实没有患者标识却要求"患者级"结论的场景。

## Inputs（输入）

| 输入 | 必需 | 说明 |
| --- | --- | --- |
| 图像数据集 | 是 | 至少两个类别目录，或带 label 列的 CSV |
| 类别语义 | 是 | 必须来自数据本身或随附文档（禁止医学常识猜测） |
| 患者/病灶 ID | 否 | 若存在则必须用于分组划分 |
| 模型架构偏好 | 否 | 默认 `torchvision` ResNet50 + ImageNet 预训练 |
| 计算设备 | 否 | 自动检测 CUDA / MPS / CPU |
| 上传大小与像素上限 | 否 | 默认 10 MB / 4000 万像素 |

## Workflow（工作流）

### 1. 数据集审计（先审计，再设计）

```
扫描图片 → 统计类别/格式/尺寸分布 → SHA-256 去重 → dHash 近重复聚类
        → 损坏文件检测 → 标签来源确认 → 输出 DATASET_REPORT.md
```

要点：

- **标签规则**：数据已明确 → 直接用；metadata 明确 → 用 metadata；多类别 → 必须依据
  数据集自带说明映射；**无法确定就记录 LABEL BLOCKER 并继续其余工作，禁止猜**。
- 重复/近重复检测要**按类别内**聚类，避免把不同病灶误并成一组。
- 文件名在类别间可能重复（`benign/953.jpg` vs `malignant/953.jpg`），
  泄漏检查应使用 `(label, filename)` 或内容哈希，不要用裸文件名。

### 2. 泄漏安全划分

```python
# 伪代码：并查集把"内容相同或近重复"的图片绑成一个 group
for rec in records:
    union(f"sha:{rec.sha256}", f"ph:{rec.label}:{rec.dhash}")
# 同一 group 只进一个 split；按类别分层；固定种子
```

必须验证：`train∩val = train∩test = val∩test = ∅`（按 SHA-256、group、label+filename 三重校验），
并把校验结果写入划分摘要。

### 3. 训练

- 两阶段迁移学习：冻结 backbone 训 head（较大 LR）→ 解冻微调（小 LR）；
- AdamW + CrossEntropyLoss + CosineAnnealingLR；
- 类别不平衡用 **class weights**（只选一种矫正手段，不要叠加多种）；
- AMP（CUDA）、早停、最优 checkpoint；
- **模型选择只用验证集**；测试集只评估一次；
- 轻度增强：RandomResizedCrop(0.85–1.0) + 旋转 ±15° + 水平翻转 + 轻度 ColorJitter。

### 4. 评估

输出 Accuracy / Precision / Recall(Sensitivity) / Specificity / F1 / ROC-AUC / PR-AUC /
混淆矩阵 / ECE；**突出恶性类召回**；生成真实图表；
未做校准时明确写 `CALIBRATION: NOT IMPLEMENTED`。

### 5. FastAPI 模型服务

- 模型**进程内单例**，启动时加载一次；
- 阻塞前向放到线程池（`anyio.to_thread.run_sync`），避免阻塞事件循环；
- `threading.BoundedSemaphore` 限制并发；
- 模型不可用返回 503，推理异常返回 500，**不泄露 traceback**。

### 6. 隐私与安全

| 项 | 做法 |
| --- | --- |
| 上传校验 | 真实 decode（Pillow `verify()`），不信任 MIME/扩展名，限制字节数与像素数 |
| 文件名 | 服务端生成 `uuid4().enc`；解析时拒绝 `/`、`\`、`..` |
| 元数据 | 重新 `paste` 到新 RGB 图像，丢弃 EXIF |
| 存储 | Fernet 加密落盘，密钥来自环境变量 |
| 读取 | 先鉴权（`WHERE id=? AND user_id=?`，越权 404）再解密 |
| 一致性 | 临时文件 → 原子 rename → DB 事务；commit 失败则删除文件 |
| 孤儿清理 | 启动时扫描磁盘上无 DB 引用的密文并清理 |
| 密码 | Argon2id；会话只存 token 哈希；CSRF 双提交 |
| 日志 | 过滤器掩码密码/令牌/密钥/长 base64 |

### 7. 医疗免责与措辞

必须常驻显示："本系统仅作为皮肤健康辅助自检工具，检测结果仅供参考，不能替代专业医生诊断。"
并说明"模型置信度并不等同于真实临床患病概率"。

禁止用语：`确诊`、`保证`、`100% 安全`、`无需就医`、`你患有 X 病`。
建议用语：恶性 → "倾向于恶性风险……建议尽快由专科医生进一步评估"；
良性 → "倾向于良性，但 AI 检测不能完全排除风险……"。
状态不能只靠颜色表达（需文字 + 符号）。

### 8. 外部测试入口（提前做好）

```bash
# 只有图片
python -m ml.evaluate_external --input data/external_test --model models/best_model.pt
# 有 labels.csv（filename,label）
python -m ml.evaluate_external --input data/external_test --labels data/external_test/labels.csv
```

外部数据**绝不参与训练/调参/阈值调整**；脚本只做推理与统计；
无标签时只输出预测 CSV，有标签时额外输出完整指标与图表。

## Outputs（产出物）

```
models/{best_model.pt, model_meta.json, class_mapping.json}
data/manifests/{train,val,test,all}.csv + split_summary.json
artifacts/{metrics.json, confusion_matrix.png, roc_curve.png, pr_curve.png,
           training_curves.png, optimization_report.json, real_model_smoke.json}
docs/ml/{DATASET_REPORT, MODEL_REPORT}.md、docs/testing/TEST_REPORT.md
backend/ FastAPI 服务 + 测试
frontend/ React SPA + 测试 + E2E
```

## Safety（安全与合规红线）

1. 不伪造指标、图表、测试结果。
2. 不把测试集用于调参；不把外部测试集并入训练。
3. 不根据文件名/文件大小等元信息决定预测。
4. 不硬编码答案、不加载随机权重却声称已训练。
5. 密钥、密码、令牌不进入仓库/前端/日志/截图。
6. 医疗结论必须带免责声明，禁止"确诊"类表述。
7. 用户图像属于敏感数据：加密存储 + 授权访问 + 可删除。

## Validation（验收清单）

- [ ] 数据集审计报告包含类别数、比例、损坏数、重复数、标签来源
- [ ] 划分三重交集为 0，且重复图在同一 split
- [ ] transform 输出 `[3,224,224]`，训练/评估/服务三处一致
- [ ] checkpoint 含 class mapping / 架构 / 输入尺寸 / 归一化 / 指标 / 时间戳 / 种子
- [ ] 内部测试集指标完整（含恶性召回）且 `TARGET` 判定明确
- [ ] 真实模型端到端冒烟测试通过（API 与本地前向推理一致）
- [ ] 用户 A 无法访问用户 B 的记录与图片
- [ ] 磁盘上的图片为密文，且无密钥无法解密
- [ ] 错误契约统一，不泄露内部细节
- [ ] 免责声明常驻，措辞合规
- [ ] 外部测试一键脚本可用且无需重新训练

## Anti-patterns（反模式）

- 用 `if exists: insert` 实现幂等 → 必须用数据库唯一约束
- 在 async handler 里直接跑 `model(batch)` → 阻塞事件循环
- 每次请求 `torch.load()` → 必须单例加载
- 用文件名判断类别 → 泄漏/作弊
- 用 `aHash` 做近重复检测 → 对同尺寸图像几乎全同，改用 `dHash`
- 先写数据库再写文件（或反之）而不做回滚 → 产生孤儿数据
- 只报告 Accuracy → 医学场景必须报告恶性召回与混淆矩阵
