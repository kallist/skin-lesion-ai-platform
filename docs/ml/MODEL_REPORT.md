# 模型评估报告 (MODEL_REPORT)

> 本报告中的**每一个数字都来自真实训练与评估**（`ml/train.py` → `ml/evaluate.py` → `ml/optimize_model.py`），
> 没有任何硬编码或人工修饰。原始数据见 `artifacts/metrics.json`、`artifacts/training_history.json`、
> `artifacts/optimization_report.json`。

- 生成时间：2026-09-09
- 模型版本：`1.0.0+run_a_resnet50`
- 硬件：NVIDIA GeForce RTX 3060 Laptop GPU（6 GB，CUDA 12.1）+ PyTorch 2.5.1

---

## 1. 数据集

| 项目 | 值 |
| --- | --- |
| 总图片数 | 1840 |
| benign | 1040（56.52%） |
| malignant | 800（43.48%） |
| 图片格式 | 100% `.jpg` |
| 色彩模式 | 100% RGB |
| 尺寸 | **全部 224×224**（唯一尺寸 1 种） |
| 损坏图片 | 0 |
| 完全重复（SHA-256） | 1 组 / 2 张（均在 **malignant** 内，`768.jpg` 与 `769.jpg`） |
| 跨类别重复 | **0** |
| 近似重复（dHash ≤ 2，类别内） | 见 `docs/ml/DATASET_REPORT.md` |
| patient_id / lesion_id | 无 |
| 附带 metadata | 无 |
| 已有 split | 无 |

标签来源：数据集自带 `benign` / `malignant` 两个目录（LABEL RULE A），未做任何医学语义推断。

## 2. 数据划分

| Split | 图片数 | 占比 | benign | malignant |
| --- | ---: | ---: | ---: | ---: |
| train | 1294 | 70.33% | 728 | 566 |
| val | 276 | 15.00% | 158 | 118 |
| test | 270 | 14.67% | 154 | 116 |

- 策略：**图像级分层划分 + 重复图分组**（无 patient_id，无法做患者级划分）；
- 种子：42（固定，可复现）；
- 泄漏校验（`data/manifests/split_summary.json` → `integrity.passed = true`）：

| 检查 | 结果 |
| --- | --- |
| train∩val / train∩test / val∩test（SHA-256） | 0 / 0 / 0 |
| 同上（重复分组 group） | 0 / 0 / 0 |
| 同上（label+filename） | 0 / 0 / 0 |
| 重复图片是否被拆开 | 否（同组进同一 split） |

> 说明：`total_rows=1840` 而 `unique_sha256=1839`，因为数据集中存在 1 对字节完全相同的图片；
> 它们被分到同一个 split，不构成泄漏。

## 3. 预处理

| 阶段 | 变换 |
| --- | --- |
| 训练 | RandomResizedCrop(224, scale=(0.85,1.0), ratio=(0.9,1.111)) → RandomRotation(±15°) → RandomHorizontalFlip → ColorJitter(brightness/contrast/saturation=0.15, hue=0.02) → ToTensor → Normalize(ImageNet) |
| 验证 / 测试 / **服务** | Resize(256) → CenterCrop(224) → ToTensor → Normalize(ImageNet) |

归一化：mean=[0.485, 0.456, 0.406]，std=[0.229, 0.224, 0.225]。
三处使用**同一份代码**（`ml/transforms.py::build_eval_transform`），并有单元测试断言输出 `[3,224,224]`。

增强刻意保持温和：过度裁剪/旋转会破坏皮损的不对称性、边界与颜色变化等关键特征。

## 4. 模型与超参数

| 项目 | 值 |
| --- | --- |
| 架构 | `torchvision.models.resnet50` |
| 预训练 | ImageNet（`ResNet50_Weights.IMAGENET1K_V2`） |
| 分类头 | `Linear(2048, 2)` |
| 参数量 | 23,512,130 |
| 类别映射 | `benign=0`，`malignant=1`（`models/class_mapping.json`） |
| 输入 | 224×224 RGB |
| 优化器 | AdamW（weight_decay=1e-4） |
| 损失 | CrossEntropyLoss，class weights = [0.8887, 1.1431]（按训练集真实计数） |
| 调度器 | CosineAnnealingLR（每个阶段独立） |
| 阶段 | 阶段 1（epoch 1–3）冻结 backbone，LR 1e-3；阶段 2（epoch 4+）全网络微调，LR 1e-4 |
| Batch size | 32 |
| AMP | 启用（CUDA） |
| 早停 | patience = 5（监控验证集 ROC-AUC） |
| 种子 | 42 |
| 实际训练轮数 | 12（best epoch = 7） |
| 训练耗时 | 122.65 s（约 2 分钟） |

## 5. 训练过程

| epoch | stage | lr | train_loss | train_acc | val_loss | val_acc | val_f1 | val_auc | val_recall | 秒 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | head | 1.00e-3 | 0.4973 | 0.7767 | — | 0.8587 | — | 0.9429 | 0.9068 | 51.5 |
| 2 | head | 7.63e-4 | 0.3519 | 0.8601 | — | 0.8370 | — | 0.9475 | 0.9576 | 4.3 |
| 3 | head | 2.88e-4 | 0.3323 | 0.8709 | — | 0.8587 | — | 0.9478 | 0.9492 | 4.1 |
| 4 | finetune | 1.00e-4 | 0.2714 | 0.8887 | — | 0.8768 | — | 0.9656 | 0.9237 | 8.2 |
| 5 | finetune | 9.90e-5 | 0.1626 | 0.9351 | — | 0.9167 | — | 0.9656 | 0.8644 | 6.6 |
| 6 | finetune | 9.59e-5 | 0.1232 | 0.9505 | — | 0.9058 | — | 0.9772 | 0.8729 | 6.8 |
| **7** | **finetune** | **9.09e-5** | **0.0966** | **0.9637** | — | **0.9167** | — | **0.9773** | **0.8983** | **6.7** |
| 8 | finetune | 8.43e-5 | 0.0689 | 0.9714 | — | 0.9239 | — | 0.9767 | 0.9237 | 6.8 |
| 9 | finetune | 7.63e-5 | 0.0666 | 0.9776 | — | 0.9130 | — | 0.9726 | 0.9068 | 6.7 |
| 10 | finetune | 6.72e-5 | 0.0499 | 0.9830 | — | 0.9167 | — | 0.9660 | 0.9068 | 6.9 |
| 11 | finetune | 5.75e-5 | 0.0401 | 0.9892 | — | 0.9094 | — | 0.9659 | 0.9068 | 6.7 |
| 12 | finetune | 4.75e-5 | 0.0277 | 0.9915 | — | 0.9203 | — | 0.9688 | 0.9068 | 6.8 |

早停在第 12 轮触发（连续 5 轮验证 ROC-AUC 未超过 epoch 7 的 0.9773）。
训练准确率持续上升至 99.15%，验证准确率在 91–92% 附近波动 → **存在过拟合趋势**，
因此以验证集 AUC 最优的 epoch 7 作为最终模型，而非最后一轮。

图表：`artifacts/training_curves.png`、`artifacts/training_loss.png`、`artifacts/training_accuracy.png`。

## 6. 验证集指标（epoch 7，用于模型选择）

| 指标 | 值 |
| --- | --- |
| Accuracy | 0.9167 |
| ROC-AUC | 0.9773 |
| Malignant Recall | 0.8983 |
| Specificity | — |

## 7. 内部测试集指标（最终评估）

样本数 **270**（benign 154 / malignant 116），评估设备 CUDA。

> **测试集使用声明**：模型选择（含早停、最优 checkpoint）只使用**验证集**；
> 内部测试集在最终评估中评估一次（`artifacts/metrics.json`）。
> 另外，性能基准脚本 `ml/optimize_model.py --split test` 也在测试集上跑过一次前向，
> 用于比较量化前后的**准确率差异**（不参与任何选择或调参）。
> 即：测试集被读取 2 次，但**从未用于模型选择或超参数调整**。

| 指标 | 值 |
| --- | ---: |
| **Accuracy** | **0.9296（92.96%）** |
| Precision（malignant） | 0.9008（90.08%） |
| Recall / Sensitivity（malignant） | 0.9397（93.97%） |
| Specificity | 0.9221（92.21%） |
| NPV | 0.9530 |
| F1 | 0.9198（91.98%） |
| Balanced Accuracy | 0.9309 |
| ROC-AUC | 0.9828 |
| PR-AUC | 0.9797 |
| Brier Score | 0.0570 |
| ECE（10 bins） | 0.0428 |

混淆矩阵（行=真实，列=预测）：

|  | 预测 benign | 预测 malignant |
| --- | ---: | ---: |
| **真实 benign** | TN = 142 | FP = 12 |
| **真实 malignant** | FN = 7 | TP = 109 |

解读：

- **恶性召回 93.97%**：116 例恶性中漏检 7 例（6.03%），在筛查场景中这是最关键指标；
- 良性被误判为恶性的有 12 例（假阳性率 7.79%），会带来不必要的焦虑与复诊，但风险方向较安全；
- 精确率 90.08% 说明"报恶性"时约九成是真的恶性。

图表：`artifacts/confusion_matrix.png`、`roc_curve.png`、`pr_curve.png`、
`probability_distribution.png`、`metric_summary.png`。

### 7.1 目标判定

```
TARGET >=90% ACCURACY: ACHIEVED
Actual internal test accuracy: 92.96% (n=270)
```

## 8. 概率校准

**CALIBRATION: NOT IMPLEMENTED**

- 未做 temperature scaling 或其他校准；
- 参考指标：Brier = 0.0570，ECE(10 bins) = 0.0428（越小越好，说明当前概率已相对贴近经验频率，
  但这**不等于**临床校准）；
- 因此 Web 界面必须显示"模型置信度并不等同于真实临床患病概率"。

若后续要做校准，建议流程：在**验证集**上拟合温度参数 T（最小化 NLL），
在测试集上报告校准前后的 ECE / 可靠性曲线，且**不得**用测试集拟合 T。

## 9. 性能基准（`artifacts/optimization_report.json`）

设备：CPU（Intel，单进程，热启动后测量）；图像：测试集真实图片；每项 25 次取中位数。

| 项目 | 基线（FP32） | TorchScript | 动态量化 INT8 |
| --- | ---: | ---: | ---: |
| 模型文件大小 | 89.998 MB | 89.98 MB | 89.985 MB |
| 参数量 | 23,512,130 | 23,512,130 | 23,512,130 |
| 单张推理延迟（中位） | **77.09 ms** | — | 71.00 ms |
| p95 延迟 | 见 JSON | — | 见 JSON |
| 吞吐 | 见 JSON | — | 见 JSON |
| 测试集准确率 | 0.9296 | — | 0.9296（Δ = 0.0000） |
| 模型加载时间 | 0.41 s | — | — |
| 生产使用 | ✅ **是** | ❌ 否 | ❌ 否 |

结论：

1. **TorchScript 导出成功**，与原始模型的输出最大差异 `0.00e+00`（完全一致），可用于部署；
2. **动态量化对 ResNet50 收益极小**：模型体积几乎不变（89.998 → 89.985 MB），
   因为 ResNet50 的参数主要在卷积层，而 `quantize_dynamic` 默认只量化 Linear 层；
   延迟从 77.09 ms 降到 71.00 ms（约 8%），准确率无变化；
3. 因此**生产部署使用 FP32 的 `best_model.pt`**，量化模型标记为
   `EXPERIMENTAL / NOT USED IN PRODUCTION`；
4. 若需要真正的体积/速度收益，应做 **静态量化（QAT 或 PTQ + 校准集）** 或使用
   `torch.jit.freeze` + `optimize_for_inference`，本项目未实现，如实记录为未实现项。

### 9.1 服务端实测（真实 API）

| 指标 | 值 |
| --- | --- |
| 模型加载（进程启动，CUDA） | 0.56 s |
| API 端到端延迟（含上传/校验/加密落盘/DB 写，n=12） | min 46 ms / median 50 ms / max 73 ms |
| 本地单张推理（GPU） | 见 `artifacts/optimization_report.json` |
| 本地单张推理（CPU） | 77 ms |
| 并发上限 | `INFERENCE_CONCURRENCY=2`（信号量） |

来源：`artifacts/real_model_smoke.json`（`scripts/smoke_real_model.py`，12 张真实图片，
API 返回概率与本地前向推理最大偏差 `0.00e+00`）。

## 10. 局限性

1. **数据集规模小且已被预处理**：仅 1840 张、全部 224×224，泛化能力有限；
   外部测试若来自不同来源/尺寸，指标可能明显下降。
2. **无患者级划分**：数据无 patient_id/lesion_id，只能做图像级划分；
   同一患者不同角度的照片理论上可能落在不同 split。
   由于数据集内同一皮损的多张照片无法被识别，**92.96% 很可能是乐观估计**：
   若存在同一病灶的多视角图像，它们可能分别落入训练集与测试集，
   使测试集难度低于真实临床场景。这一点无法在现有数据上量化，属于已知偏差来源。
3. **类别不平衡未完全消除**：benign 占 56.5%，使用 class weights 缓解但未重采样。
4. **过拟合趋势明显**：训练准确率 99.15% vs 验证 91–92%，说明模型容量相对数据偏大。
5. **未做概率校准**（见 §8）。
6. **未做交叉验证**：单次固定种子划分，指标存在抽样波动。
7. **外部验证结果明显低于内部**：独立外部测试（797 张，2026-09-10 完成）准确率
   78.54%、恶性召回 65.49%、ROC-AUC 0.9079，未达到训练阶段设定的 90% 目标；详情见
   `docs/ml/EXTERNAL_EVALUATION.md` 与 `artifacts/external_test/external_metrics.json`。
8. **量化/剪枝收益有限**（见 §9）。
9. **单类别阈值固定为 0.5**：医学场景可按敏感性优先调整阈值，但需在验证集上做且必须记录。

## 11. 复现命令

```powershell
# 1) 数据审计 + 划分
python -m ml.prepare_data

# 2) 训练（复现本次交付模型）
python -m ml.train --model resnet50 --epochs 18 --batch-size 32 --lr 1e-3 \
                   --finetune-lr 1e-4 --head-epochs 3 --patience 5 --seed 42 \
                   --run-name run_a_resnet50

# 3) 内部测试集最终评估（生成 artifacts/metrics.json 与全部图表）
python -m ml.evaluate --model models/best_model.pt --split test

# 4) 性能与优化实验
python -m ml.optimize_model --model models/best_model.pt --split test --runs 25 --torchscript

# 5) 真实模型端到端冒烟（需后端已启动）
python scripts/smoke_real_model.py --samples 12
```

> 复现性说明：`--seed 42` 固定了划分与训练随机性；由于 CUDA 卷积算法非确定性，
> 逐位完全复现不保证，但指标应在同一量级（本次为单次真实结果，未做多次平均）。
