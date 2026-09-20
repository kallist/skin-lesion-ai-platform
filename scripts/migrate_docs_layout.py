"""One-off migration: reorganise docs/ for the public portfolio layout.

Moves:
  docs/final/**                -> docs/archive/project-origin/**
  docs/PRD.md                  -> docs/product/PRD.md
  docs/UI_UX.md                -> docs/product/UI_UX.md
  docs/ARCHITECTURE.md         -> docs/engineering/ARCHITECTURE.md
  docs/API.md                  -> docs/engineering/API.md
  docs/DATABASE.md             -> docs/engineering/DATABASE.md
  docs/MODEL_REPORT.md         -> docs/ml/MODEL_REPORT.md
  docs/DATASET_REPORT.md       -> docs/ml/DATASET_REPORT.md
  docs/TEST_REPORT.md          -> docs/testing/TEST_REPORT.md
  docs/DEPLOYMENT.md           -> docs/deployment/DEPLOYMENT.md
  docs/OPERATIONS.md           -> docs/deployment/OPERATIONS.md
  docs/PROJECT_REPORT.md       -> docs/archive/project-origin/PROJECT_REPORT.md
  docs/DELIVERY_CHECKLIST.md   -> docs/archive/project-origin/DELIVERY_CHECKLIST.md
  docs/TOMORROW_TEST_GUIDE.md  -> docs/testing/EXTERNAL_TEST_RUNBOOK.md

Then rewrites, inside every move target:
  * markdown links / images whose resolved target also moved (new relative path)
  * literal old paths ("docs/final/...", "docs/PRD.md", ...) in prose and code spans

Run once, from the repository root, with the virtualenv python:
    .\\.venv\\Scripts\\python.exe -X utf8 scripts\\migrate_docs_layout.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]

FILE_MOVES = {
    "docs/final/01_皮肤癌图像检测系统_PRD.md": "docs/archive/project-origin/01_皮肤癌图像检测系统_PRD.md",
    "docs/final/02_皮肤癌图像检测系统_项目总结报告.md": "docs/archive/project-origin/02_皮肤癌图像检测系统_项目总结报告.md",
    "docs/final/03_皮肤癌图像检测系统_使用说明书.md": "docs/archive/project-origin/03_皮肤癌图像检测系统_使用说明书.md",
    "docs/final/04_学校任务书验收对照表.md": "docs/archive/project-origin/04_学校任务书验收对照表.md",
    "docs/final/EXTERNAL_TEST_REPORT.md": "docs/archive/project-origin/EXTERNAL_TEST_REPORT.md",
    "docs/final/METRICS_SOURCE.md": "docs/archive/project-origin/METRICS_SOURCE.md",
    "docs/final/delivery_notice.txt": "docs/archive/project-origin/delivery_notice.txt",
    "docs/final/training_data_readme.txt": "docs/archive/project-origin/training_data_readme.txt",
    "docs/final/assets/taskbook_extract.txt": "docs/archive/project-origin/assets/taskbook_extract.txt",
    "docs/final/皮肤癌图像检测系统_实习项目综合报告.md": "docs/archive/project-origin/皮肤癌图像检测系统_实习项目综合报告.md",
    "docs/final/assets/diagrams/architecture.png": "docs/assets/diagrams/architecture.png",
    "docs/final/assets/diagrams/erd.png": "docs/assets/diagrams/erd.png",
    "docs/final/assets/diagrams/ml_pipeline.png": "docs/assets/diagrams/ml_pipeline.png",
    "docs/final/assets/external/confusion_matrix.png": "docs/archive/project-origin/assets/external/confusion_matrix.png",
    "docs/final/assets/external/internal_vs_external.png": "docs/archive/project-origin/assets/external/internal_vs_external.png",
    "docs/final/assets/external/pr_curve.png": "docs/archive/project-origin/assets/external/pr_curve.png",
    "docs/final/assets/external/roc_curve.png": "docs/archive/project-origin/assets/external/roc_curve.png",
    "docs/final/assets/external/score_distribution.png": "docs/archive/project-origin/assets/external/score_distribution.png",
    "docs/final/assets/internal/confusion_matrix.png": "docs/archive/project-origin/assets/internal/confusion_matrix.png",
    "docs/final/assets/internal/training_curves.png": "docs/archive/project-origin/assets/internal/training_curves.png",
    "docs/PRD.md": "docs/product/PRD.md",
    "docs/UI_UX.md": "docs/product/UI_UX.md",
    "docs/ARCHITECTURE.md": "docs/engineering/ARCHITECTURE.md",
    "docs/API.md": "docs/engineering/API.md",
    "docs/DATABASE.md": "docs/engineering/DATABASE.md",
    "docs/MODEL_REPORT.md": "docs/ml/MODEL_REPORT.md",
    "docs/DATASET_REPORT.md": "docs/ml/DATASET_REPORT.md",
    "docs/TEST_REPORT.md": "docs/testing/TEST_REPORT.md",
    "docs/DEPLOYMENT.md": "docs/deployment/DEPLOYMENT.md",
    "docs/OPERATIONS.md": "docs/deployment/OPERATIONS.md",
    "docs/PROJECT_REPORT.md": "docs/archive/project-origin/PROJECT_REPORT.md",
    "docs/DELIVERY_CHECKLIST.md": "docs/archive/project-origin/DELIVERY_CHECKLIST.md",
    "docs/TOMORROW_TEST_GUIDE.md": "docs/testing/EXTERNAL_TEST_RUNBOOK.md",
}

# directories that are moved wholesale (git mv handles the tree)
DIR_MOVES = [("docs/final/assets/screenshots", "docs/assets/screenshots")]

SCREENSHOT_FILES = {}

MD_LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\s+\"[^\"]*\")?(\))")

# literal path rewrites for prose / tables / code spans: explicit and ordered
LITERAL_REWRITES: list[tuple[str, str]] = [
    ("docs/final/", "docs/archive/project-origin/"),
    ("docs\\final\\", "docs\\archive\\school-delivery\\"),
    ("docs/final", "docs/archive/project-origin"),
    ("docs/TOMORROW_TEST_GUIDE.md", "docs/testing/EXTERNAL_TEST_RUNBOOK.md"),
    ("docs/PRD.md", "docs/product/PRD.md"),
    ("docs/UI_UX.md", "docs/product/UI_UX.md"),
    ("docs/ARCHITECTURE.md", "docs/engineering/ARCHITECTURE.md"),
    ("docs/API.md", "docs/engineering/API.md"),
    ("docs/DATABASE.md", "docs/engineering/DATABASE.md"),
    ("docs/MODEL_REPORT.md", "docs/ml/MODEL_REPORT.md"),
    ("docs/DATASET_REPORT.md", "docs/ml/DATASET_REPORT.md"),
    ("docs/TEST_REPORT.md", "docs/testing/TEST_REPORT.md"),
    ("docs/DEPLOYMENT.md", "docs/deployment/DEPLOYMENT.md"),
    ("docs/OPERATIONS.md", "docs/deployment/OPERATIONS.md"),
    ("docs/PROJECT_REPORT.md", "docs/archive/project-origin/PROJECT_REPORT.md"),
    ("docs/DELIVERY_CHECKLIST.md", "docs/archive/project-origin/DELIVERY_CHECKLIST.md"),
]


def git_mv(src_rel: str, dst_rel: str) -> None:
    """Move a file on disk; git detects the rename from content identity.

    A plain filesystem move is used instead of ``git mv`` because the repository
    is full of non-ASCII paths and this script must not depend on the console
    code page.
    """
    src = REPO / src_rel
    dst = REPO / dst_rel
    if not src.exists():
        if dst.exists():
            return  # already migrated
        raise SystemExit(f"source missing: {src_rel}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise SystemExit(f"destination already exists: {dst_rel}")
    src.replace(dst)


def build_screenshot_moves() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for src_dir, dst_dir in DIR_MOVES:
        source = REPO / src_dir
        if not source.is_dir():
            raise SystemExit(f"missing directory: {src_dir}")
        for path in sorted(source.iterdir()):
            if path.is_file():
                mapping[f"{src_dir}/{path.name}"] = f"{dst_dir}/{path.name}"
    return mapping


def apply_moves() -> dict[str, str]:
    mapping = dict(FILE_MOVES)
    mapping.update(build_screenshot_moves())
    # children first so directories end up empty
    for src_rel, dst_rel in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        git_mv(src_rel, dst_rel)
    # remove the now-empty original directories
    for old_dir in ("docs/final/assets/screenshots", "docs/final/assets/diagrams",
                    "docs/final/assets/external", "docs/final/assets/internal",
                    "docs/final/assets", "docs/final"):
        directory = REPO / old_dir
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    return mapping


def new_location(old_rel: str, mapping: dict[str, str]) -> str | None:
    """Where does an old repo-relative path live now?"""
    if old_rel in mapping:
        return mapping[old_rel]
    for src, dst in mapping.items():
        if old_rel.startswith(src + "/"):
            return dst + old_rel[len(src):]
    return None


def rewrite_links(text: str, source_old: str, source_new: str, mapping: dict[str, str]) -> tuple[str, int]:
    """Rewrite markdown links/images that point at files which also moved."""
    source_dir_old = PurePosixPath(source_old).parent
    source_dir_new = PurePosixPath(source_new).parent
    changed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        prefix, target, title, suffix = match.group(1), match.group(2), match.group(3) or "", match.group(4)
        if target.startswith(("http://", "https://", "mailto:", "#", "/")):
            return match.group(0)
        path_part, _, anchor = target.partition("#")
        if not path_part:
            return match.group(0)
        resolved = str((source_dir_old / path_part))
        resolved = str(PurePosixPath(resolved))
        # normalise ./ and ../
        parts: list[str] = []
        for chunk in resolved.split("/"):
            if chunk in ("", "."):
                continue
            if chunk == ".." and parts and parts[-1] != "..":
                parts.pop()
                continue
            parts.append(chunk)
        normalised = "/".join(parts)
        destination = new_location(normalised, mapping)
        if destination is None:
            return match.group(0)
        import posixpath

        relative = posixpath.relpath(destination, str(source_dir_new) or ".")
        if anchor:
            relative = f"{relative}#{anchor}"
        if relative != target:
            changed += 1
            return f"{prefix}{relative}{title}{suffix}"
        return match.group(0)

    return MD_LINK.sub(replace, text), changed


def rewrite_literals(text: str) -> tuple[str, int]:
    """Replace literal old paths that appear in prose, tables or code spans."""
    changed = 0
    for src, dst in LITERAL_REWRITES:
        if src in text:
            changed += text.count(src)
            text = text.replace(src, dst)
    return text, changed


def main() -> int:
    status = subprocess.run(
        ["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    dirty = [line for line in status.splitlines() if line and not line.startswith("??")]
    if dirty:
        print("[warn] working tree already has modifications:")
        for line in dirty:
            print("   ", line)

    mapping = apply_moves()
    print(f"moved {len(mapping)} files")

    total_links = 0
    total_literals = 0
    for src, dst in sorted(mapping.items()):
        if not dst.endswith((".md", ".txt")):
            continue
        path = REPO / dst
        original = path.read_text(encoding="utf-8")
        text, links = rewrite_links(original, src, dst, mapping)
        text, literals = rewrite_literals(text)
        if text != original:
            path.write_text(text, encoding="utf-8", newline="")
        total_links += links
        total_literals += literals

    print(f"rewrote {total_links} markdown links and {total_literals} literal path mentions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
