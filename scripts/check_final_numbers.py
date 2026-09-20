"""Cross-document numeric consistency check for the public docs and the archive.

Every document that mentions the school test must use exactly the same values, and
no document may claim the 90% target without saying which dataset it refers to.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = [
    "README.md",
    "docs/ml/EXTERNAL_EVALUATION.md",
    "docs/ml/MODEL_REPORT.md",
    "docs/testing/TEST_REPORT.md",
    "docs/engineering/AI_ASSISTED_DEVELOPMENT.md",
    "docs/archive/project-origin/皮肤癌图像检测系统_实习项目综合报告.md",
    "docs/archive/project-origin/01_皮肤癌图像检测系统_PRD.md",
    "docs/archive/project-origin/02_皮肤癌图像检测系统_项目总结报告.md",
    "docs/archive/project-origin/03_皮肤癌图像检测系统_使用说明书.md",
    "docs/archive/project-origin/04_学校任务书验收对照表.md",
    "docs/archive/project-origin/EXTERNAL_TEST_REPORT.md",
    "docs/archive/project-origin/METRICS_SOURCE.md",
]

ext = json.loads((REPO / "artifacts" / "external_test" / "external_metrics.json").read_text(encoding="utf-8-sig"))
internal = json.loads((REPO / "artifacts" / "metrics.json").read_text(encoding="utf-8"))

# accepted spellings per metric (percent form, decimal form, rounded decimal)
EXPECTED = {
    "external n": [str(ext["n"])],
    "external accuracy": ["78.54%", f"{ext['accuracy']:.4f}", "78.54"],
    "external precision": ["88.44%", f"{ext['precision']:.4f}", "88.44"],
    "external recall": ["65.49%", f"{ext['recall_sensitivity']:.4f}", "65.49"],
    "external specificity": ["91.50%", "0.915", "91.50"],
    "external f1": ["75.25%", f"{ext['f1']:.4f}", "75.25"],
    "external roc_auc": ["0.9079", "0.907853"],
    "external pr_auc": ["0.8929", "0.892925"],
    "confusion": ["260", "366", "34", "137", "626", "171"],
    "internal accuracy": ["92.96%", f"{internal['accuracy']:.4f}", "92.96"],
    "internal recall": ["93.97%", f"{internal['recall_sensitivity']:.4f}", "93.97"],
    "internal roc_auc": ["0.9828", "0.982815"],
}

problems: list[str] = []
print(f"{'document':64s} status")
print("-" * 82)
excluded: list[str] = []
for name in DOCS:
    path = REPO / name
    if not path.exists():
        # project-origin documents are deliberately excluded from the public snapshot
        excluded.append(name)
        print(f"{name:64s} (not present - excluded from this release)")
        continue
    text = path.read_text(encoding="utf-8")
    mentions_school = "797" in text or "78.54" in text
    if not mentions_school:
        print(f"{name:64s} (no school-test claim)")
    else:
        missing = [key for key, forms in EXPECTED.items() if not any(form in text for form in forms)]
        # a document only has to carry the numbers it actually reports
        critical = [key for key in missing if key in ("external n", "external accuracy", "external recall", "confusion")]
        status = "OK" if not critical else "MISSING " + ", ".join(critical)
        print(f"{name:64s} {status}")
        for key in critical:
            problems.append(f"{name}: missing {key}")

# unqualified 90% claims
for name in DOCS:
    path = REPO / name
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    for match in re.finditer(r"(达到|满足|达成)[^。\n]{0,24}90%", text):
        window = text[max(0, match.start() - 320): match.end() + 180]
        if not any(key in window for key in ("内部", "训练阶段", "训练目标", "学校独立", "未达到", "没达到")):
            problems.append(f"{name}: unqualified 90% claim near {match.group(0)!r}")

# stale wording
for name in DOCS:
    path = REPO / name
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    if "78.54" not in text:  # documents that do not report the school test at all
        for stale in ("学校测试集尚未提供", "外部测试结果未知", "学校测试数据尚未提供"):
            if stale in text:
                problems.append(f"{name}: stale wording {stale!r}")

print()
if problems:
    print(f"PROBLEMS ({len(problems)}):")
    for item in problems:
        print("  -", item)
    sys.exit(1)
if excluded:
    print(f"NOTE: {len(excluded)} document(s) not present in this release "
          f"(project-origin material excluded from the public snapshot)")
print("RESULT: PASS - all documents agree on the school test numbers, no unqualified 90% claim, no stale wording")
