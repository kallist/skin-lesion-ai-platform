# MODEL PROMPT — 模型与训练提示词

> 本文件是训练/评估阶段实际使用的指令整理稿。

## 目标

在给定的皮肤病变数据集上训练一个 ResNet50 二分类器（benign / malignant），
目标准确率 ≥ 90%，且所有指标必须来自真实评估。

## 数据阶段

1. **审计**：扫描 `*.jpg/*.jpeg/*.png/*.bmp/*.webp`，统计类别数量、比例、格式、尺寸分布、
   损坏图片数、重复图片（SHA-256）、近重复图片（感知哈希）、标签格式、是否存在
   patient_id / lesion_id、是否有 metadata、是否已有 split。
2. **标签规则**：
   - A：数据已明确 benign/malignant → 直接使用；
   - B：metadata 已提供 → 使用 metadata；
   - C：多类别皮肤病数据 → 必须依据数据集自带标签说明才能映射为二分类；
   - D：**禁止**凭模型自己的医学常识把未知标签映射为 malignant。
   无法确定标签时记录 `DATASET LABEL BLOCKER`，但仍继续完成 WebApp / API / pipeline / 文档。
3. **划分**：有 patient_id/lesion_id 必须按患者/病灶分组划分；否则图像级分层划分。
   默认 70/15/15，种子 42。必须验证 train∩val、train∩test、val∩test 为空（基于文件名与 SHA-256，
   条件允许时加入感知哈希近重复检测）。
4. **增强**：RandomResizedCrop(scale 0.85–1.0) → 旋转 ±15° → 水平翻转 → 轻度 ColorJitter →
   ToTensor → ImageNet 归一化。禁止过度增强导致皮损特征丢失。
5. **验证/测试/服务**：Resize → CenterCrop 224×224 → Tensor → Normalize，三处必须一致。

## 模型阶段

- 架构：`torchvision.models.resnet50`，ImageNet 预训练权重，`fc` 改为 `Linear(2048, 2)`。
- 类别：0 = benign，1 = malignant；映射写入 `models/class_mapping.json`。
- 训练：阶段 1 冻结 backbone（LR 1e-3），阶段 2 全网络微调（LR 1e-4），AdamW，CosineAnnealingLR，
  CrossEntropyLoss，类别不平衡用 class weights，AMP（CUDA），早停 + 最优 checkpoint 保存。
- checkpoint 至少包含：model state、class mapping、architecture、input size、normalization、
  validation metrics、training timestamp、software version、random seed。
- **模型选择只用验证集**；内部测试集仅做一次最终评估。
- 最多 2–3 次有限调参实验（学习率、class weights、增强强度、冻结轮数、batch size、ResNet101），
  禁止无限参数搜索，禁止用测试集调参。

## 指标要求

必须输出 Accuracy、Precision、Recall/Sensitivity、Specificity、F1、ROC-AUC、混淆矩阵，
可行时增加 PR-AUC，并**明确突出 Malignant Recall**（恶性漏检风险更高）。

图表：`artifacts/{confusion_matrix,roc_curve,training_loss,training_accuracy,pr_curve,metric_summary}.png`
与 `artifacts/metrics.json`。**禁止伪造任何图表**。

## 置信度

置信度必须来自模型真实 `softmax` 概率。UI 必须说明"模型置信度并不等同于真实临床患病概率"。
未做 temperature scaling 时必须明确记录 `CALIBRATION: NOT IMPLEMENTED`。

## 模型优化

实现 `ml/optimize_model.py`，记录 baseline 模型大小与推理延迟；若实现量化/剪枝，必须真实 benchmark
并记录 model size / latency / accuracy difference。若优化无实际收益，如实报告
`EXPERIMENTAL / NOT USED IN PRODUCTION`，生产使用最可靠的模型。

## 最终验收报告格式

必须报告：Dataset size（train/val/internal test）、Best model、Epochs、Best validation metric、
Internal test 的 Accuracy/Precision/Recall/Specificity/F1/ROC-AUC、
以及明确的 `TARGET >=90%: ACHIEVED / NOT ACHIEVED`。
