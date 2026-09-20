# Independent External Evaluation

冻结模型在**项目外提供的独立数据**上的评测结果。这是本项目最重要的一次工程检验：
它给出了模型真实泛化水平的答案，而这个答案比内部指标悲观得多。

| 项目 | 内容 |
| --- | --- |
| 评测日期 | 2026-09-10 |
| 数据 | 外部提供，797 张 JPG（benign 400 / malignant 397，全部 224×224 RGB，损坏 0） |
| 标签来源 | 目录结构（`benign/`、`malignant/`），无任何标签文件 |
| 模型 | `models/best_model.pt`，版本 `1.0.0+run_a_resnet50`（ResNet50，输入 224×224） |
| 模型 SHA256 | `9c385625fba8d297fdfc2808c3504d034eadfcfdfa3182e844d604e4c2d164e8`（评测前后一致） |
| 处理方式 | **冻结模型一次性评测**：未重新训练、未微调、未改结构、未改类别映射、未调阈值 |
| 结果来源 | `artifacts/external_test/external_metrics.json`、`external_predictions.csv`、`verification.json` |

## Results

| 指标 | 内部测试集 (n=270) | 独立外部测试集 (n=797) | 差值 |
| --- | ---: | ---: | ---: |
| Accuracy | 92.96% | **78.54%** | −14.42 pt |
| Precision（恶性） | 90.08% | 88.44% | −1.65 pt |
| Recall / Sensitivity（恶性） | 93.97% | **65.49%** | **−28.47 pt** |
| Specificity | 92.21% | 91.50% | −0.71 pt |
| F1 | 91.98% | 75.25% | −16.73 pt |
| Balanced Accuracy | 93.09% | 78.50% | −14.59 pt |
| ROC-AUC | 0.9828 | 0.9079 | −0.0750 |
| PR-AUC | 0.9797 | 0.8929 | −0.0867 |
| Brier score | 0.0570 | 0.1670 | +0.1100 |
| ECE (10 bin) | 0.0428 | 0.1505 | +0.1078 |

混淆矩阵：

| | 内部测试集 | 独立外部测试集 |
| --- | ---: | ---: |
| TP | 109 | 260 |
| TN | 142 | 366 |
| FP | 12 | 34 |
| **FN** | **7** | **137** |

**外部测试准确率未达到训练阶段设定的 ≥90% 目标。**

## What the Drop Looks Like

- **主要在恶性召回上**：Recall 从 93.97% 掉到 65.49%，137 例恶性样本被判为良性。
- **特异性几乎不动**：92.21% → 91.50%，说明模型并没有整体「变得更激进」或「更保守」，
  因此这不是一个靠移动阈值就能解决的问题。
- **概率质量整体偏移**：Brier score 与 ECE 同时变差（0.057 → 0.167、0.043 → 0.151），
  外部数据上模型的置信度与正确率之间的一致性明显下降，这也是未做概率校准的直接后果。

阈值扫描（仅分析，未应用到模型；`artifacts/external_test/threshold_sweep.json`）：

| 阈值 | Accuracy | Recall（恶性） | Specificity |
| ---: | ---: | ---: | ---: |
| 0.05 | 83.56% | 90.18% | 77.00% |
| 0.50（生产阈值） | 78.54% | 65.49% | 91.50% |

即使把阈值压到 0.05，外部准确率也只有 83.56%，而且代价是特异性掉到 77%——
这进一步说明性能差距不是单纯的决策阈值问题。

## Why No Retraining on the Test Set

外部数据在本项目中的角色是**检验**，不是调参。一旦用外部数据选阈值、选模型或做微调，
它就不再是独立证据，78.54% 这个数字也就失去了意义。因此项目保留了首次冻结模型的完整结果
（包含全部 171 条错误样本清单），把这次评测当作结论而不是优化起点。

## Evidence and Verification

- **无字节级泄漏**：外部数据与训练 / 验证 / 内部测试集的 SHA256 完全重合数为 **0 / 0 / 0**
  （`artifacts/external_test/audit.json`，逐文件哈希见 `sha256.csv`）。
- **评测不含训练**：`ml/evaluate_external.py` 只加载权重做前向推理，全程 `torch.no_grad()`，
  模块内没有任何优化器、反向传播或数据加载训练管线。
- **独立复核**：`scripts/verify_external_test.py` 不依赖评测脚本的指标实现，
  从 `external_predictions.csv` 自行重算 TP/TN/FN/FP 与全部指标并逐项比对，
  结果 `verdict: PASS`（7/7 检查通过），同时产出 `external_errors.csv`
  （按 FP / FN 分类的 171 条错误样本）。

  > **可复现性边界**：复核脚本读取 `artifacts/external_test/staging/labels.csv`，
  而该目录（外部数据的只读暂存副本）已被 `.gitignore` 排除、不能随仓库公开。
  因此 `verification.json` 是**本次运行留下的存档证据**，不是任何人 clone 后就能重跑的东西；
  指标本身可以从仓库中的 `external_predictions.csv` 重新算出并复核，但「从零重跑复核脚本」
  需要另外取得那批外部数据。
- **数据完整性**：797 张图与 797 条标签全部匹配，缺失 0、损坏 0、重复预测行 0。
  由于存在 120 个跨类别同名文件（如 `benign/1309.jpg` 与 `malignant/1309.jpg`），
  评测在 `artifacts/external_test/staging/` 使用加类别前缀的扁平副本完成，
  **原始数据目录全程只读**，副本与原文件逐文件 SHA256 一致。

## Attribution Boundaries

诚实地说：**本项目无法对性能下降做严格归因。** 外部数据没有提供采集设备、患者来源、
病灶编号或任何元数据，也没有与训练集可比的人群信息，因此下面这些只是可能性，不是结论：

- 数据分布差异（成像设备、拍摄距离、光照、肤色与病灶构成）是可能因素之一；
- 该批图片全部为 224×224，说明已被上游预处理过，而本项目无法确认其预处理方式与训练数据是否一致；
- 训练数据规模有限（1840 张），本身就会限制模型对新分布的适应能力。

不能断言「已经证明是 domain shift」，也不能把差距归因到单一原因。
要得到可归因的结论，需要带元数据的多中心数据与按来源分层的评测，这不在本次评测范围内。

## Reproduce

```powershell
# 1) 审计外部数据并生成只读暂存副本（不会修改原始数据）
.\.venv\Scripts\python.exe -X utf8 scripts\audit_school_test_data.py --input <外部图片目录>

# 2) 冻结模型正式评测（不做任何训练）
.\.venv\Scripts\python.exe -X utf8 -m ml.evaluate_external `
  --input artifacts\external_test\staging `
  --labels artifacts\external_test\staging\labels.csv `
  --output artifacts\external_test --model models\best_model.pt --batch-size 16

# 3) 独立复核（从零重算指标）
.\.venv\Scripts\python.exe -X utf8 scripts\verify_external_test.py
```

详细操作说明见 [`../testing/EXTERNAL_TEST_RUNBOOK.md`](../testing/EXTERNAL_TEST_RUNBOOK.md)；
不含数据的评测方式（只有图片、没有标签）见同文「无标签数据」一节。

> 医疗说明：外部测试中 137 例恶性样本被漏判，本项目**不是医疗设备**、未取得任何医疗器械认证，
> 也没有临床验证数据。模型输出只能作为参考，不能替代皮肤科医生的面诊与检查。
