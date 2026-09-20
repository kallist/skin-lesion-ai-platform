# 模型交付说明 (deliverables/models)

| 文件 | 说明 |
| --- | --- |
| `best_model.pt` | 生产使用模型（ResNet50 FP32，90 MB），内部测试集 Accuracy 92.96% |
| `model_meta.json` | 训练元数据：架构、类别映射、输入尺寸、归一化、验证指标、超参、环境、种子 |
| `class_mapping.json` | 类别索引映射（benign=0, malignant=1），客户端不得自行猜测 |
| `best_model_torchscript.pt` | TorchScript 导出（与原始模型输出差异 0.00e+00），可选部署产物 |

加载方式：把 `best_model.pt` 放到 `models/best_model.pt`（或设置 `MODEL_PATH`），重启后端即可。

模型未提交到 Git（体积原因，见 .gitignore），交付时请连同本目录一起拷贝。
