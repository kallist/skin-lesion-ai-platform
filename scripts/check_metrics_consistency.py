"""Verify that the web app's static evaluation figures match the evaluation artifacts.

The public "模型评测" page must never show numbers that disagree with the files
produced by the evaluation scripts.  This check re-reads the artifacts and compares
them against ``frontend/src/data/evaluation.ts``.

Checked:
  artifacts/metrics.json                        -> internal held-out test split
  artifacts/external_test/external_metrics.json -> independent external test set
  artifacts/external_test/audit.json            -> class balance + SHA256 overlap
  models/model_meta.json                        -> architecture / version / input size

Usage (repository root):
    .\\.venv\\Scripts\\python.exe scripts\\check_metrics_consistency.py
Exit code 0 = consistent, 1 = drift (details printed).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TS_FILE = REPO / "frontend" / "src" / "data" / "evaluation.ts"

INTERNAL_JSON = REPO / "artifacts" / "metrics.json"
EXTERNAL_JSON = REPO / "artifacts" / "external_test" / "external_metrics.json"
AUDIT_JSON = REPO / "artifacts" / "external_test" / "audit.json"
MODEL_META_JSON = REPO / "models" / "model_meta.json"

# artifact metric key -> TypeScript field name
METRIC_FIELDS = {
    "accuracy": "accuracy",
    "precision": "precision",
    "recall_sensitivity": "recall",
    "specificity": "specificity",
    "f1": "f1",
    "roc_auc": "rocAuc",
    "pr_auc": "prAuc",
}

# Values that must appear verbatim inside an exported object literal.
STRING_FIELDS = {
    "MODEL_INFO": {
        "architecture": "resnet50",
        "modelVersion": "1.0.0+run_a_resnet50",
        "calibration": "NOT IMPLEMENTED",
    },
}


def fail(message: str) -> None:
    print(f"[FAIL] {message}")


def load_ts() -> str:
    if not TS_FILE.is_file():
        raise SystemExit(f"missing file: {TS_FILE}")
    return TS_FILE.read_text(encoding="utf-8")


def object_block(source: str, export_name: str) -> str:
    """Return the body of ``export const <name> ... = { ... }`` (first level)."""
    pattern = re.compile(
        r"export\s+const\s+" + re.escape(export_name) + r"\s*(?::[^=]+)?=\s*\{",
        re.MULTILINE,
    )
    match = pattern.search(source)
    if not match:
        raise SystemExit(f"{export_name} not found in {TS_FILE.name}")
    start = match.end() - 1  # at '{'
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise SystemExit(f"unterminated object literal for {export_name}")


def number_value(block: str, field: str) -> float:
    match = re.search(rf"\b{re.escape(field)}\s*:\s*(-?\d+(?:\.\d+)?)", block)
    if not match:
        raise SystemExit(f"field '{field}' not found in {block[:80]}…")
    return float(match.group(1))


def string_value(block: str, field: str) -> str:
    match = re.search(rf"\b{re.escape(field)}\s*:\s*'([^']*)'", block)
    if not match:
        raise SystemExit(f"string field '{field}' not found in block")
    return match.group(1)


def check_metrics_block(
    block: str, artifact: dict, label: str, problems: list[str]
) -> None:
    if number_value(block, "n") != float(artifact["n"]):
        problems.append(
            f"{label}: n {number_value(block, 'n')} != artifact {artifact['n']}"
        )
    for artifact_key, ts_field in METRIC_FIELDS.items():
        expected = float(artifact[artifact_key])
        actual = number_value(block, ts_field)
        if abs(actual - expected) > 1e-12:
            problems.append(
                f"{label}: {ts_field} {actual!r} != artifact {artifact_key} {expected!r}"
            )
    confusion = artifact["confusion_matrix"]
    for field in ("tp", "tn", "fp", "fn"):
        actual = number_value(block, field)
        if int(actual) != int(confusion[field]):
            problems.append(
                f"{label}: confusion.{field} {int(actual)} != artifact {confusion[field]}"
            )


def check_evidence_links() -> list[str]:
    """The page claims plots it renders as static files — make sure they exist."""
    problems: list[str] = []
    for name in (
        "internal_confusion_matrix.png",
        "external_confusion_matrix.png",
        "external_roc_curve.png",
        "external_pr_curve.png",
    ):
        if not (REPO / "frontend" / "public" / "evaluation" / name).is_file():
            problems.append(f"missing plot asset: frontend/public/evaluation/{name}")
    return problems


def main() -> int:
    source = load_ts()
    internal = json.loads(INTERNAL_JSON.read_text(encoding="utf-8-sig"))
    external = json.loads(EXTERNAL_JSON.read_text(encoding="utf-8-sig"))
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8-sig"))
    model_meta = json.loads(MODEL_META_JSON.read_text(encoding="utf-8"))

    problems: list[str] = []

    check_metrics_block(object_block(source, "INTERNAL_TEST"), internal, "INTERNAL_TEST", problems)
    check_metrics_block(object_block(source, "EXTERNAL_TEST"), external, "EXTERNAL_TEST", problems)

    # class balance of the external set
    balance = object_block(source, "EXTERNAL_CLASS_BALANCE")
    for field in ("benign", "malignant"):
        expected = int(audit["by_class"][field])
        actual = int(number_value(balance, field))
        if actual != expected:
            problems.append(f"EXTERNAL_CLASS_BALANCE.{field} {actual} != audit {expected}")

    # byte-level overlap between the external set and each internal split
    overlap = object_block(source, "EXTERNAL_OVERLAP")
    for field in ("train", "val", "test"):
        expected = int(audit["overlap_with_internal"][field])
        actual = int(number_value(overlap, field))
        if actual != expected:
            problems.append(f"EXTERNAL_OVERLAP.{field} {actual} != audit {expected}")

    # model identity
    info_block = object_block(source, "MODEL_INFO")
    if string_value(info_block, "architecture") != model_meta["architecture"]:
        problems.append(
            f"MODEL_INFO.architecture != model_meta.architecture ({model_meta['architecture']})"
        )
    if string_value(info_block, "modelVersion") != model_meta["model_version"]:
        problems.append(
            f"MODEL_INFO.modelVersion != model_meta.model_version ({model_meta['model_version']})"
        )
    if int(number_value(info_block, "inputSize")) != int(model_meta["input_size"]):
        problems.append(f"MODEL_INFO.inputSize != model_meta.input_size ({model_meta['input_size']})")
    if string_value(info_block, "calibration") != model_meta["calibration"]:
        problems.append(
            f"MODEL_INFO.calibration != model_meta.calibration ({model_meta['calibration']})"
        )

    problems.extend(check_evidence_links())

    if problems:
        print("[FAIL] frontend/src/data/evaluation.ts is out of sync with the artifacts:")
        for problem in problems:
            fail(problem)
        return 1

    print("[OK] evaluation.ts matches the artifacts")
    print(
        "     internal n={n} acc={acc:.4f}   external n={en} acc={eacc:.4f}   overlap={ov}".format(
            n=internal["n"],
            acc=internal["accuracy"],
            en=external["n"],
            eacc=external["accuracy"],
            ov=audit["overlap_with_internal"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
