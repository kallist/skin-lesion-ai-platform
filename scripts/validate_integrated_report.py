"""Validate the integrated report: structure, first-page content, metric numerals.

Checks the generated Markdown + DOCX for the items the delivery requirements call
out explicitly: the school test result must appear before the abstract, every key
number must be present and correct, no emoji / agent-status vocabulary / AI meta
language in the body, and no stale "external test not available" wording.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MD = REPO / "docs" / "archive" / "project-origin" / "皮肤癌图像检测系统_实习项目综合报告.md"
DOCX = REPO / "deliverables" / "docs" / "皮肤癌图像检测系统_实习项目综合报告_V1.0.docx"
EXT = json.loads((REPO / "artifacts" / "external_test" / "external_metrics.json").read_text(encoding="utf-8-sig"))
INT = json.loads((REPO / "artifacts" / "metrics.json").read_text(encoding="utf-8"))

text = MD.read_text(encoding="utf-8")
problems: list[str] = []
notes: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


# ---------------------------------------------------------------- required numbers
REQUIRED = {
    "797": "external sample count",
    "78.54%": "external accuracy",
    "88.44%": "external precision",
    "65.49%": "external recall",
    "91.50%": "external specificity",
    "75.25%": "external F1",
    "0.9079": "external ROC-AUC",
    "0.8929": "external PR-AUC",
    "626": "correct count",
    "171": "incorrect count",
    "137": "false negatives",
    "260": "true positives",
    "366": "true negatives",
    "92.96%": "internal accuracy",
    "93.97%": "internal recall",
    "0.9828": "internal ROC-AUC",
    "1840": "dataset total",
    "1040": "benign images",
    "800": "malignant images",
    "1294": "train split",
    "276": "validation split",
    "270": "internal test split",
    "9C385625FBA8D297FDFC2808C3504D034EADFCFDFA3182E844D604E4C2D164E8": "model SHA256",
}
for needle, label in REQUIRED.items():
    check(needle in text, f"missing number/text: {needle} ({label})")

# ---------------------------------------------------------------- ordering
school_pos = text.find("# 学校独立测试结果")
abstract_pos = text.find("# 摘要")
chapter1_pos = text.find("# 1 项目概述")
check(school_pos != -1, "missing '# 学校独立测试结果' section")
check(abstract_pos != -1, "missing '# 摘要' section")
check(chapter1_pos != -1, "missing '# 1 项目概述' chapter")
if school_pos != -1 and abstract_pos != -1:
    check(school_pos < abstract_pos, "school test result must appear BEFORE the abstract")
if abstract_pos != -1 and chapter1_pos != -1:
    check(abstract_pos < chapter1_pos, "abstract must appear before chapter 1")
check(text.find("78.54%") < abstract_pos, "78.54% must appear before the abstract (first pages)")

# ---------------------------------------------------------------- structure
for chapter in [
    "# 1 项目概述", "# 2 需求分析", "# 3 系统总体设计", "# 4 数据集与图像处理",
    "# 5 深度学习模型设计与训练", "# 6 内部模型评估", "# 7 后端系统设计",
    "# 8 数据库设计", "# 9 前端系统设计", "# 10 安全与隐私设计", "# 11 系统测试",
    "# 12 系统使用方法", "# 13 部署与运行", "# 14 项目完成情况",
    "# 15 项目不足与改进方向", "# 16 项目总结",
    "# 附录 A 主要功能需求", "# 附录 B 接口摘要", "# 附录 C 学校任务书验收对照",
    "# 附录 D 主要运行与测试命令", "# 附录 E AI Coding 过程材料",
]:
    check(chapter in text, f"missing chapter/appendix: {chapter}")

# ---------------------------------------------------------------- forbidden style
EMOJI = ["✅", "❌", "⚠", "🚀", "📊", "🔧", "🛑", "📁", "🎯", "💡", "🔍", "⭐"]
for symbol in EMOJI:
    check(symbol not in text, f"emoji present: {symbol}")

AGENT_WORDS = ["NOT TESTED", "NOT IMPLEMENTED", "NOT RECORDED", "COMPLETE（", "PARTIAL", "ACHIEVED", "PASS / FAIL"]
for word in AGENT_WORDS:
    check(word not in text, f"agent-style status vocabulary in body: {word}")

META_WORDS = ["诚实边界", "数据诚实声明", "Harness", "Agent", "独立 Review", "Final Delivery Report",
              "Source of Truth", "agent", "prompt 中", "本轮任务"]
for word in META_WORDS:
    if word in text:
        notes.append(f"meta-language occurrence: {word}")

AI_TICS = ["综上所述", "值得注意的是", "需要强调的是", "首先，", "其次，", "最后，", "显著提升", "大幅提高",
           "具有重要意义", "完整闭环", "赋能", "助力"]
for tic in AI_TICS:
    if tic in text:
        notes.append(f"AI-writing tic present: {tic}")

STALE = ["尚未提供", "外部测试结果未知", "NOT RECORDED", "明天"]
for word in STALE:
    check(word not in text, f"stale wording in the integrated report: {word}")

# ---------------------------------------------------------------- claim context
check("92.96%" in text and "78.54%" in text, "both internal and external accuracy must appear")
# A statement about reaching the 90% target must say which dataset it refers to.
for match in re.finditer(r"(达到|满足|达成)[^。\n]{0,24}90%[^。\n]{0,16}(目标|要求)?", text):
    window = text[max(0, match.start() - 260): match.end() + 160]
    if not any(word in window for word in ("内部", "训练阶段", "训练目标", "学校独立", "未达到", "没达到")):
        problems.append(f"unqualified '90% target' claim near: {match.group(0)!r}")

# ---------------------------------------------------------------- tables & figures
tables = text.count("\n| ---")
figures = len(re.findall(r"^!\[", text, re.M))
notes.append(f"markdown tables: {tables}, figures: {figures}")

# ---------------------------------------------------------------- docx
if not DOCX.exists():
    problems.append(f"DOCX not found: {DOCX}")
else:
    with zipfile.ZipFile(DOCX) as archive:
        names = archive.namelist()
        document = archive.read("word/document.xml").decode("utf-8")
        media = [n for n in names if n.startswith("word/media/")]
        check(len(names) == len(set(names)), "duplicate parts inside the DOCX package")
        check(len(media) == len(set(media)), "duplicate media parts inside the DOCX package")
        check(document.count("<w:drawing>") == len(media),
              f"drawing/media mismatch: {document.count('<w:drawing>')} vs {len(media)}")
        check("TOC \\o" in document or "TOC \\\\o" in document, "DOCX is missing the TOC field")
        check("footerReference" in document, "DOCX is missing the page-number footer")
        for marker in ("TODO", "TBD", "FIXME", "待补充"):
            check(marker not in document, f"placeholder in DOCX: {marker}")
    notes.append(f"docx media parts: {len(media)}")

# ---------------------------------------------------------------- report
print("=" * 74)
print("INTEGRATED REPORT VALIDATION")
print("=" * 74)
print(f"markdown        : {MD.name} ({MD.stat().st_size / 1024:.1f} KB)")
print(f"docx            : {DOCX.name} ({DOCX.stat().st_size / 1024:.1f} KB)" if DOCX.exists() else "docx: MISSING")
print(f"external metrics: n={EXT['n']} acc={EXT['accuracy']:.6f} recall={EXT['recall_sensitivity']:.6f} "
      f"spec={EXT['specificity']:.6f} f1={EXT['f1']:.6f} auc={EXT['roc_auc']:.6f}")
print(f"internal metrics: n={INT['n']} acc={INT['accuracy']:.6f} recall={INT['recall_sensitivity']:.6f}")
print()
for note in notes:
    print("note:", note)
if problems:
    print(f"\nPROBLEMS ({len(problems)}):")
    for item in problems:
        print("  -", item)
    print("\nRESULT: FAIL")
    sys.exit(1)
print("\nRESULT: PASS")
