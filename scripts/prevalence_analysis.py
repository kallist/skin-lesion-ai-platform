"""Prevalence sensitivity of the deployed operating point.

The external evaluation set is class-balanced (400 benign / 397 malignant), but a
screening population is not.  This prints PPV/NPV and the error counts an
operator would actually see, for the frozen model's measured operating point.

Usage:
    .\\.venv\\Scripts\\python.exe -X utf8 scripts\\prevalence_analysis.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXTERNAL = REPO / "artifacts" / "external_test" / "external_metrics.json"

PREVALENCES = [0.01, 0.02, 0.05, 0.10, 0.20, 0.43, 0.50]
N = 1000


def main() -> int:
    metrics = json.loads(EXTERNAL.read_text(encoding="utf-8-sig"))
    sens = float(metrics["recall_sensitivity"])
    spec = float(metrics["specificity"])

    print(f"operating point from {EXTERNAL.relative_to(REPO).as_posix()}")
    print(f"  sensitivity {sens:.4f}   specificity {spec:.4f}   (balanced evaluation set)")
    print()
    header = f"{'prevalence':>11} | {'PPV':>7} | {'NPV':>7} | {'missed/1000':>11} | {'false alarms/1000':>17}"
    print(header)
    print("-" * len(header))
    for prevalence in PREVALENCES:
        ppv = sens * prevalence / (sens * prevalence + (1 - spec) * (1 - prevalence))
        npv = spec * (1 - prevalence) / (spec * (1 - prevalence) + (1 - sens) * prevalence)
        missed = N * prevalence * (1 - sens)
        false_alarms = N * (1 - prevalence) * (1 - spec)
        print(
            f"{prevalence * 100:10.1f}% | {ppv * 100:6.1f}% | {npv * 100:6.1f}% | "
            f"{missed:11.1f} | {false_alarms:17.1f}"
        )
    print()
    print("Reading: on a balanced set the headline accuracy is 78.54%, but the positive")
    print("predictive value collapses as prevalence falls, so the model is not usable as a")
    print("stand-alone screening tool -- it can only be a supplementary signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
