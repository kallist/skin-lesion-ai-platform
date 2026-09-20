"""Repository-wide relative markdown link/image checker.

Scans every tracked markdown file (or a directory tree given on the command line)
and reports links and image targets that do not resolve on disk.

Usage (repository root):
    .\\.venv\\Scripts\\python.exe -X utf8 scripts\\check_links.py [path ...]
Exit code 0 = no broken links, 1 = broken links found.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
SKIP_DIRS = {"node_modules", ".venv", "dist", "__pycache__", ".git", ".runtime"}


def iter_markdown(roots: list[Path]):
    for root in roots:
        if root.is_file() and root.suffix == ".md":
            yield root
            continue
        for path in root.rglob("*.md"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            yield path


def collect(roots: list[Path]) -> list[Path]:
    return sorted(set(iter_markdown(roots)))


def normalise(base: PurePosixPath, target: str) -> str:
    parts: list[str] = []
    for chunk in (base / target).parts:
        if chunk in ("", "."):
            continue
        if chunk == ".." and parts and parts[-1] != "..":
            parts.pop()
            continue
        parts.append(chunk)
    return "/".join(parts)


def is_ignored(relative: str) -> bool:
    """True when the path is deliberately excluded by .gitignore.

    The public snapshot drops material whose publication rights are unconfirmed
    (see private-release-exclusions.md).  Links to those paths are expected to be
    absent there, so they are reported as excluded rather than as broken links.
    """
    result = subprocess.run(
        ["git", "-C", str(REPO), "check-ignore", "-q", relative],
        capture_output=True,
    )
    return result.returncode == 0


def main(argv: list[str]) -> int:
    roots = [Path(arg).resolve() for arg in argv[1:]] or [REPO]
    broken: list[tuple[str, str]] = []
    excluded: list[tuple[str, str]] = []
    checked = 0
    documents = collect(roots)

    for doc in documents:
        rel_doc = doc.relative_to(REPO).as_posix()
        base = PurePosixPath(rel_doc).parent
        text = doc.read_text(encoding="utf-8")
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#", "/")):
                continue
            path_part = target.partition("#")[0]
            if not path_part:
                continue
            checked += 1
            resolved = normalise(base, path_part)
            if (REPO / resolved).exists():
                continue
            # a link into deliberately excluded material is not a broken link
            candidates = [resolved]
            current = PurePosixPath(resolved)
            while current.parent != current:
                current = current.parent
                candidates.append(current.as_posix())
            if any(is_ignored(candidate) for candidate in candidates):
                excluded.append((rel_doc, target))
            else:
                broken.append((rel_doc, target))

    if excluded:
        print(f"excluded by .gitignore (expected in the public snapshot): {len(excluded)}")
        for doc, target in excluded:
            print(f"  {doc} -> {target}")

    print(f"checked {checked} relative links in {len(documents)} markdown files")
    if broken:
        print(f"\nBROKEN ({len(broken)}):")
        for doc, target in broken:
            print(f"  {doc} -> {target}")
        return 1
    print("[OK] no broken relative links")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
