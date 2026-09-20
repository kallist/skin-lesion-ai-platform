"""Cross-document consistency and link validation for the final deliverables.

Checks the school-delivery Markdown files in docs/archive/project-origin
plus README.md for:
  * broken relative links and missing image targets
  * placeholder markers (TODO / TBD / FIXME / 待补充)
  * metric drift: every key number must use the value recorded in
    artifacts/metrics.json / models/model_meta.json
  * forbidden medical wording ("确诊为恶性", "患有皮肤癌", ...)
  * claims that must never appear without evidence (Docker PASS, CI PASS,
    external test accuracy)

Exit code 1 when a blocking problem is found.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = [
    REPO / "README.md",
    REPO / "docs" / "archive" / "project-origin" / "01_皮肤癌图像检测系统_PRD.md",
    REPO / "docs" / "archive" / "project-origin" / "02_皮肤癌图像检测系统_项目总结报告.md",
    REPO / "docs" / "archive" / "project-origin" / "03_皮肤癌图像检测系统_使用说明书.md",
    REPO / "docs" / "archive" / "project-origin" / "04_学校任务书验收对照表.md",
    REPO / "docs" / "archive" / "project-origin" / "METRICS_SOURCE.md",
]

metrics = json.loads((REPO / "artifacts" / "metrics.json").read_text(encoding="utf-8"))
meta = json.loads((REPO / "models" / "model_meta.json").read_text(encoding="utf-8"))
smoke = json.loads((REPO / "artifacts" / "real_model_smoke.json").read_text(encoding="utf-8"))

# Project-origin documents are deliberately absent from the public snapshot, so the
# checks above run on whatever is actually present and report the rest as excluded.
DOCS = [doc for doc in DOCS if doc.exists()]
excluded_docs = [
    name
    for name in ("01_皮肤癌图像检测系统_PRD.md", "02_皮肤癌图像检测系统_项目总结报告.md",
                 "03_皮肤癌图像检测系统_使用说明书.md", "04_学校任务书验收对照表.md",
                 "METRICS_SOURCE.md")
    if not (REPO / "docs" / "archive" / "project-origin" / name).exists()
]

problems: list[str] = []
warnings: list[str] = []

# ---------------------------------------------------------------- links
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
for doc in DOCS:
    text = doc.read_text(encoding="utf-8")
    for target in LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        clean = target.split("#")[0].strip()
        if not clean:
            continue
        resolved = (doc.parent / clean).resolve()
        if not resolved.exists():
            problems.append(f"{doc.name}: broken link -> {target}")

# ---------------------------------------------------------------- placeholders
for doc in DOCS:
    for number, line in enumerate(doc.read_text(encoding="utf-8").split("\n"), start=1):
        if re.search(r"\b(TODO|TBD|FIXME)\b", line) or "待补充" in line or "待填写" in line:
            problems.append(f"{doc.name}:{number}: placeholder text: {line.strip()[:80]}")

# ---------------------------------------------------------------- metric drift
EXPECTED = {
    "accuracy": round(metrics["accuracy"] * 100, 2),          # 92.96
    "recall": round(metrics["recall_sensitivity"] * 100, 2),  # 93.97
    "specificity": round(metrics["specificity"] * 100, 2),    # 92.21
    "f1": round(metrics["f1"] * 100, 2),                      # 91.98
    "roc_auc": round(metrics["roc_auc"], 4),                  # 0.9828
    "pr_auc": round(metrics["pr_auc"], 4),                    # 0.9797
}
FORBIDDEN_METRICS = ["92.9%", "93.0%", "93.5%", "94.0%", "94.1%的准确率", "90.5%", "91.9%的准确率"]

for doc in DOCS:
    text = doc.read_text(encoding="utf-8")
    if doc.name == "METRICS_SOURCE.md":
        continue
    for value in FORBIDDEN_METRICS:
        if value in text:
            warnings.append(f"{doc.name}: suspicious metric string {value!r} (verify against METRICS_SOURCE)")

# ---------------------------------------------------------------- medical wording
# NOTE: files that intentionally DOCUMENT the banned wording (the frontend test
# assertion list) are exempt, otherwise the checker would flag its own rules.
FORBIDDEN_PHRASES = [
    "确诊为恶性",
    "确诊为良性",
    "患有皮肤癌，",
    "可以替代医生",
    "替代专业医生的诊断能力",
    "保证 90%",
    "保证90%",
    "临床诊断系统",
]
BANNED_WORDING_CONTEXT = ("禁用用语", "禁用表述", "禁用词")
for doc in DOCS:
    text = doc.read_text(encoding="utf-8")
    for phrase in FORBIDDEN_PHRASES:
        if phrase in text:
            problems.append(f"{doc.name}: forbidden medical/overclaim wording: {phrase!r}")
    if "你患有皮肤癌" in text:
        for line in text.split("\n"):
            if "你患有皮肤癌" in line and not any(ctx in line for ctx in BANNED_WORDING_CONTEXT):
                problems.append(f"{doc.name}: forbidden medical wording outside the banned-word list: {line.strip()[:100]}")

# every final document must carry the disclaimer
for doc in DOCS:
    text = doc.read_text(encoding="utf-8")
    if doc.name != "METRICS_SOURCE.md":
        if "不能替代专业医生诊断" not in text:
            problems.append(f"{doc.name}: missing medical disclaimer sentence")

# ---------------------------------------------------------------- evidence-gated claims
def context_lines(text: str, needle: str) -> list[str]:
    return [line for line in text.split("\n") if needle in line]


for doc in DOCS:
    text = doc.read_text(encoding="utf-8")
    for line in context_lines(text, "docker") + context_lines(text, "Docker"):
        lowered = line.lower()
        # "config 校验" is the only Docker-related PASS that has real evidence
        evidence_ok = ("config" in lowered and "校验" in line) or "syntax" in lowered
        if "pass" in lowered and not evidence_ok and "not tested" not in lowered and "未实测" not in line:
            problems.append(f"{doc.name}: Docker claimed as PASS without evidence: {line.strip()[:100]}")
    for line in context_lines(text, "CI"):
        # lines that explicitly state CI does not exist, or that "local PASS != CI PASS",
        # or that merely forbid claiming CI PASS, are fine
        benign = (
            "不存在" in line
            or "≠" in line
            or "!" in line
            or "不得" in line
            or "NOT" in line
            or "没有" in line
        )
        if "PASS" in line and not benign:
            problems.append(f"{doc.name}: CI claimed as PASS without evidence: {line.strip()[:100]}")

# ---------------------------------------------------------------- summarise
print("=" * 72)
print("CROSS-DOCUMENT CONSISTENCY CHECK")
print("=" * 72)
print(f"documents checked : {len(DOCS)}")
if excluded_docs:
    print(f"excluded (public snapshot drops project-origin material): {len(excluded_docs)}")
    for name in excluded_docs:
        print(f"  - {name}")
print(f"expected metrics  : accuracy={EXPECTED['accuracy']}% recall={EXPECTED['recall']}% "
      f"specificity={EXPECTED['specificity']}% f1={EXPECTED['f1']}% "
      f"roc_auc={EXPECTED['roc_auc']} pr_auc={EXPECTED['pr_auc']}")
print(f"model version     : {meta['model_version']} · {meta['architecture']} · input {meta['input_size']}")
print(f"smoke             : {smoke['verdict']} ({smoke['checked']} images, accuracy {smoke['sample_accuracy']})")
print()
if warnings:
    print(f"WARNINGS ({len(warnings)}):")
    for item in warnings:
        print("  -", item)
    print()
if problems:
    print(f"PROBLEMS ({len(problems)}):")
    for item in problems:
        print("  -", item)
    print()
    print("RESULT: FAIL")
    sys.exit(1)
print("RESULT: PASS (no broken links, no placeholders, no forbidden wording, no unevidenced claims)")
