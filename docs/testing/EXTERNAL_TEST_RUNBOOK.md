# 外部测试操作手册 (EXTERNAL TEST RUNBOOK)

> 外部提供的真实测试图片已经完成评测（2026-09-10，797 张，准确率 78.54%），
> 结果见 [`../ml/EXTERNAL_EVALUATION.md`](../ml/EXTERNAL_EVALUATION.md)。
> 本手册保留为**复现与后续重测的操作说明**：把图片放进目录 → 运行一条命令。
> **不需要重新训练，不需要改代码。**
>
> 注意：本次 797 张数据已经用于评估。如果将来基于这批数据做训练、参数选择或阈值调整，
> 它就不能再作为未见过的测试集使用，需要另外准备新的独立数据。

---

## 1. 测试图片放在哪里

```
data/external_test/
```

把外部提供的所有图片（jpg / jpeg / png / bmp / webp）直接复制进这个目录即可。
子目录不会被自动扫描，除非加 `--recursive`。

该目录已在 `.gitignore` 中忽略，不会被提交到 Git（避免把第三方数据推到公开仓库）。

```powershell
# 示例：把图片从下载目录复制进来
Copy-Item "<图片目录>\*" data\external_test\ -Force
```

## 2. 执行哪条命令

### 情况 A：只有图片，没有答案

```powershell
.\.venv\Scripts\python.exe -m ml.evaluate_external --input data/external_test --model models/best_model.pt
```

### 情况 B：外部数据同时提供了标签文件 `labels.csv`

标签文件格式（列名大小写不敏感，支持 `filename`/`file`/`image` 与 `label`/`class`/`target`）：

```csv
filename,label
ISIC_0001.jpg,benign
ISIC_0002.jpg,malignant
```

把 `labels.csv` 放在 `data/external_test/` 下，然后：

```powershell
.\.venv\Scripts\python.exe -m ml.evaluate_external --input data/external_test --labels data/external_test/labels.csv --model models/best_model.pt
```

标签取值支持：`benign` / `b` / `0` / `良性` / `nevus` / `normal`，
`malignant` / `m` / `1` / `恶性` / `melanoma` / `cancer`（大小写不敏感）。

### 可选参数

| 参数 | 说明 |
| --- | --- |
| `--output <目录>` | 输出目录，默认与 `--input` 相同 |
| `--batch-size N` | 批大小，默认 16 |
| `--device cpu\|cuda` | 强制设备 |
| `--recursive` | 递归扫描子目录 |

## 3. 输出在哪里

输出都在 `data/external_test/`（或 `--output` 指定目录）：

| 文件 | 情况 A | 情况 B | 内容 |
| --- | --- | --- | --- |
| `external_predictions.csv` | ✅ | ✅ | `filename, prediction, confidence, benign_probability, malignant_probability`（B 情况额外含 `true_label, correct`） |
| `external_metrics.json` | — | ✅ | accuracy / precision / recall / specificity / f1 / roc_auc / pr_auc / 混淆矩阵 |
| `confusion_matrix.png` | — | ✅ | 混淆矩阵图 |
| `roc_curve.png` | — | ✅ | ROC 曲线 |
| `pr_curve.png` | — | ✅ | PR 曲线 |

`external_predictions.csv` 示例：

```csv
filename,prediction,confidence,benign_probability,malignant_probability
ISIC_0001.jpg,benign,0.913742,0.913742,0.086258
ISIC_0002.jpg,malignant,0.874311,0.125689,0.874311
```

## 4. 如果提供标签，accuracy 如何计算

脚本内部对每一行做如下处理（`ml/evaluate_external.py`）：

1. 用标签文件把 `filename` 映射为 `0=benign` / `1=malignant`；
2. 模型输出 `malignant_probability`；若 `malignant_probability ≥ benign_probability`
   则预测为 `malignant`（等价于阈值 0.5），否则 `benign`；
3. 统计四个量：

   - `TP` = 真实恶性且预测恶性
   - `TN` = 真实良性且预测良性
   - `FP` = 真实良性但预测恶性
   - `FN` = 真实恶性但预测良性

4. 指标定义：

   | 指标 | 公式 |
   | --- | --- |
   | Accuracy | `(TP + TN) / (TP + TN + FP + FN)` |
   | Precision | `TP / (TP + FP)` |
   | Recall (Sensitivity) | `TP / (TP + FN)` |
   | Specificity | `TN / (TN + FP)` |
   | F1 | `2·P·R / (P + R)` |
   | ROC-AUC | 基于 `malignant_probability` 的秩统计（含并列处理） |
   | PR-AUC | 逐步法 average precision |

5. 控制台会直接打印：

   ```
   ===== EXTERNAL TEST METRICS (real, no tuning) =====
   n=120  accuracy=0.9417
   precision=0.9375  recall=0.9231
   specificity=0.9565  f1=0.9302
   roc_auc=0.9812  pr_auc=0.9744
   confusion={'tp': 48, 'tn': 66, 'fp': 3, 'fn': 4}
   TARGET >=90%: ACHIEVED
   ```

## 5. 重要约束（不可违反）

- 外部测试数据**绝对不能**参与训练、调参、阈值调整；
- 该脚本**只做推理与统计**，没有任何训练或拟合代码；
- 预测只依赖模型对像素的推理结果，**不读取文件名做任何判断**；
- 如果某些图片没有对应标签，它们仍会被预测，但不计入指标（`unmatched` 字段会显示数量）。

## 6. 拿到图片后的完整操作清单

```powershell
# 1. 放图片
Copy-Item "<外部图片目录>\*" data\external_test\ -Force

# 2. 确认模型在位
Test-Path models\best_model.pt      # 必须为 True

# 3A. 无标签
.\.venv\Scripts\python.exe -m ml.evaluate_external --input data/external_test

# 3B. 有标签
.\.venv\Scripts\python.exe -m ml.evaluate_external --input data/external_test --labels data/external_test/labels.csv

# 4. 查看结果
Get-Content data\external_test\external_predictions.csv -TotalCount 5
Get-Content data\external_test\external_metrics.json   # 仅 3B 情况
```

## 7. 也可以在 Web 界面上逐张测试

如果评审需要现场演示，直接在前端上传图片即可：
注册/登录 → 检测页 → 上传 → 开始检测 → 查看结果（预测、置信度、两类概率、模型版本、免责声明）。

批量评估仍建议使用上面的命令，因为界面不输出 CSV 指标。
