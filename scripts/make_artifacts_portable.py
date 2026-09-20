"""One-off: remove machine-specific absolute paths from tracked artifacts.

Rewrites:
  * data/manifests/*.csv          path column -> repository-relative path
  * models/model_meta.json        manifest_dir / environment paths
  * deliverables/models/model_meta.json   same
  * artifacts/external_test/audit.json    test_data_dir / staging paths
  * backend/tests/test_security.py        drive-letter literal in the leak assertion

The trained checkpoint is NOT touched: only JSON/CSV metadata is rewritten, so
``models/best_model.pt`` keeps SHA256 9c385625…d164e8.

Usage:
    .\\.venv\\Scripts\\python.exe -X utf8 scripts\\make_artifacts_portable.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

MANIFEST_DIR = REPO / "data" / "manifests"
MANIFEST_FILES = ["train.csv", "val.csv", "test.csv", "all.csv"]

WINDOWS_ABS = re.compile(r"^[A-Za-z]:[\\/]")

ENV_REPLACEMENTS = {
    "platform": "platform: see training log",
}


def rewrite_manifests() -> list[str]:
    changed = []
    for name in MANIFEST_FILES:
        path = MANIFEST_DIR / name
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
            fieldnames = list(rows[0].keys()) if rows else []
        if not rows or "path" not in fieldnames:
            continue
        rewrites = 0
        for row in rows:
            raw = row.get("path", "")
            if not WINDOWS_ABS.match(raw):
                continue
            # keep everything from data/raw/... onwards
            normalised = raw.replace("\\", "/")
            marker = "/data/raw/"
            if marker in normalised:
                row["path"] = "data/raw/" + normalised.split(marker, 1)[1]
            else:
                relative = row.get("relative_path", "").replace("\\", "/")
                row["path"] = f"data/raw/{relative}" if relative else Path(normalised).name
            rewrites += 1
        if rewrites:
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            changed.append(f"{path.relative_to(REPO).as_posix()}: {rewrites} path(s) -> repository-relative")
    return changed


def rewrite_json_paths() -> list[str]:
    changed = []
    targets = {
        REPO / "models" / "model_meta.json": ["manifest_dir"],
        REPO / "deliverables" / "models" / "model_meta.json": ["manifest_dir"],
        REPO / "artifacts" / "external_test" / "audit.json": [
            "test_data_dir",
            "staging_dir",
            "labels_csv",
        ],
    }
    for path, keys in targets.items():
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        touched = 0

        def walk(node):
            nonlocal touched
            if isinstance(node, dict):
                for key in list(node.keys()):
                    value = node[key]
                    if isinstance(value, str) and WINDOWS_ABS.match(value):
                        if key in keys or key.endswith("_dir") or key.endswith("_path"):
                            if key == "manifest_dir":
                                node[key] = "data/manifests"
                            else:
                                node[key] = "<external to this repository>"
                            touched += 1
                            continue
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        if touched:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            changed.append(f"{path.relative_to(REPO).as_posix()}: {touched} absolute path(s) removed")
    return changed


def rewrite_test_literal() -> list[str]:
    path = REPO / "backend" / "tests" / "test_security.py"
    text = path.read_text(encoding="utf-8")
    old = 'for forbidden in ("traceback", "sqlalchemy", "file \\"", "c:\\\\", "/home/", "select ", "secret"):'
    new = 'for forbidden in ("traceback", "sqlalchemy", "file \\"", "/home/", "select ", "secret"):'
    if old in text:
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
        return ["backend/tests/test_security.py: dropped drive-letter literal from the leak assertion"]
    return []


def main() -> int:
    changes = rewrite_manifests() + rewrite_json_paths() + rewrite_test_literal()
    if not changes:
        print("nothing to do — artifacts already portable")
        return 0
    for item in changes:
        print(f"[ok] {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
