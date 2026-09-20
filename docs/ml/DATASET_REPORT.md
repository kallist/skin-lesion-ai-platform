# DATASET REPORT — 皮肤病变图像数据集审计报告

> 自动生成：`python ml/dataset.py audit`。所有数字均来自真实扫描，未做任何人工修饰。

## 1. 数据集来源

- 数据集根目录：`data/raw`
- 标签来源：folder-name (benign / malignant class directories shipped with the dataset)
- 是否包含 metadata 文件：否
- 是否存在 patient_id：否
- 是否存在 lesion_id：否
- 是否已存在 train/val/test 划分：否

## 2. 数据规模与类别分布

| 类别 | 图片数 | 占比 |
| --- | ---: | ---: |
| benign | 1040 | 56.52% |
| malignant | 800 | 43.48% |
| **合计** | **1840** | 100% |

## 3. 图片格式与尺寸

- 扩展名分布：{'.jpg': 1840}
- 色彩模式分布：{'RGB': 1840}
- 宽度：min=224 p25=224 median=224 p75=224 max=224
- 高度：min=224 p25=224 median=224 p75=224 max=224

## 4. 数据质量检查

- 损坏 / 无法解码图片：**0**
- 唯一 SHA-256 数量：1839
- 完全重复分组数：1（涉及 2 张）
- **跨类别**完全重复分组数：**0**（涉及 0 张）
- 近似重复（dHash 距离 ≤ 2，同类别内检测）分组数：24（涉及 62 张）

重复明细：

| SHA-256 (前12位) | 文件 |
| --- | --- |
| `19a74bc9c333` | malignant/768.jpg, malignant/769.jpg |

## 5. 标签规则

数据集自带 `benign` / `malignant` 两个目录，属于 LABEL RULE A（数据已明确给出良性/恶性标签），因此直接使用目录名作为标签，无需任何医学语义推断。

## 6. 划分方案

- 策略：group-aware stratified image-level split (no patient_id in dataset); exact-SHA and aHash<=2 near-duplicate clusters are never split across sets
- 随机种子：42

| Split | 图片数 | benign | malignant | 分组数 |
| --- | ---: | ---: | ---: | ---: |
| train | 1294 | 728 | 566 | 1255 |
| val | 276 | 158 | 118 | 269 |
| test | 270 | 154 | 116 | 269 |

- 泄漏检查：**PASS**（SHA-256 / 分组 / 类别内文件名 三重交集均为 0）
- 校验明细：`{"train_vs_val_by_sha256": 0, "train_vs_test_by_sha256": 0, "val_vs_test_by_sha256": 0, "train_vs_val_by_group": 0, "train_vs_test_by_group": 0, "val_vs_test_by_group": 0, "train_vs_val_by_label_filename": 0, "train_vs_test_by_label_filename": 0, "val_vs_test_by_label_filename": 0, "total_rows": 1840, "unique_sha256": 1839, "distinct_content_every_row": false, "note": "total_rows may legitimately exceed unique_sha256 when the raw dataset contains byte-identical images; those are grouped into one split."}`

## 7. 审计结论

- 62 images belong to near-duplicate clusters (aHash distance <= 2); clusters are kept inside one split.
- No patient_id / lesion_id available: image-level stratified split with duplicate-group awareness is used instead of a patient-level split.

> 本报告由脚本生成，未对数据做任何主观修改。若后续更换数据集，请重新运行 `python ml/dataset.py audit --build-splits` 覆盖本文件。
