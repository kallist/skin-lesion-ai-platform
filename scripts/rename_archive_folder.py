"""One-off: rename the archived origin material to a neutral folder name.

`docs/archive/project-origin/` told every reader that this was coursework before
they read a single line.  The material itself is preserved unchanged; only the
folder name and the links pointing at it change.

    docs/archive/project-origin/  ->  docs/archive/project-origin/

Usage (repository root):
    .\\.venv\\Scripts\\python.exe -X utf8 scripts\\rename_archive_folder.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OLD = "docs/archive/project-origin"
NEW = "docs/archive/project-origin"

TEXT_SUFFIXES = {".md", ".txt", ".py", ".ps1", ".mjs", ".ts", ".tsx", ".json", ".yml", ".yaml"}
SKIP_DIRS = {"node_modules", ".venv", "dist", "__pycache__", ".git", ".runtime", "logs", "data"}


def iter_text_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {".gitignore", ".env.example"}:
            files.append(path)
    return files


def rewrite_links(text: str, depth_change: bool) -> str:
    """Relative markdown links need one extra ``../`` after the extra nesting level."""
    return text


def main() -> int:
    source = REPO / OLD
    target = REPO / NEW
    if target.exists() and not source.exists():
        print(f"already renamed: {NEW}")
    elif not source.exists():
        print(f"source missing: {OLD}")
        return 1
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        print(f"renamed {OLD} -> {NEW}")

    changed = 0
    for path in iter_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if OLD not in text:
            continue
        updated = text.replace(OLD, NEW)
        updated = updated.replace(OLD.replace("/", "\\"), NEW.replace("/", "\\"))
        if updated != text:
            path.write_text(updated, encoding="utf-8", newline="")
            changed += 1
            print(f"  updated references in {path.relative_to(REPO).as_posix()}")

    # After the rename the archived files sit at the same depth (archive/<folder>/),
    # so relative links between them and the public docs keep working unchanged.
    print(f"\n{changed} file(s) referenced the old folder name")
    return 0


if __name__ == "__main__":
    sys.exit(main())
