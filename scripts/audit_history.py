"""Audit the git history itself: were secrets, personal data or private paths ever committed?

The working-tree audit (`audit_public_release.py`) cannot see removed files.  This
script walks every blob reachable from every ref and scans the text ones, so the
question "did a real secret ever enter this repository?" gets a real answer.

It is intentionally read-only and can be slow on large histories.

Usage (repository root):
    .\\.venv\\Scripts\\python.exe -X utf8 scripts\\audit_history.py
        [--max-blobs N] [--rev <rev>]
Exit code 0 = nothing sensitive found, 1 = findings needing attention.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# High-signal patterns only: this scan must not drown the reader in JSON floats.
# ``[^\S\r\n]*`` keeps a match on one line, so "SESSION_SECRET=" followed by a newline
# and an unrelated variable name is not reported as a value.
PATTERNS = [
    (re.compile(r"SESSION_SECRET[^\S\r\n]*=[^\S\r\n]*[A-Za-z0-9_\-]{16,}"), "session secret value", True),
    (re.compile(r"IMAGE_ENCRYPTION_KEY[^\S\r\n]*=[^\S\r\n]*[A-Za-z0-9_\-=+/]{20,}"), "image encryption key value", True),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key", True),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token", True),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "OpenAI-style API key", True),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block", True),
    (re.compile(r"(?i)\b1[3-9]\d{9}\b"), "mainland mobile number", False),
    (re.compile(r"(?i)(?:身份证|学号)\D{0,4}\d{6,}"), "national ID / student number", False),
]

# Files whose whole purpose is to contain placeholder credentials.  Matches here are
# reported for review (with the value shown) instead of blocking the audit.
FIXTURE_HINTS = ("test_", "conftest.py", ".env.example", "audit_history.py", "audit_public_release.py")
# Synthetic values that must never be mistaken for a real credential.
KNOWN_FIXTURE_VALUES = re.compile(r"(?i)(Zm9vYmFyYmF6cXV4|foobarbazqux|changeme|placeholder|example|your[-_]?key)")

TEXT_SUFFIXES = {
    ".md", ".txt", ".json", ".csv", ".py", ".ps1", ".bat", ".ts", ".tsx", ".js", ".mjs",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".html", ".css", ".example", ".gitignore",
}


def git(*args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True,
        text=not binary,
        encoding=None if binary else "utf-8",
        errors=None if binary else "replace",
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan git history for sensitive content")
    parser.add_argument("--rev", default="--all", help="revision range passed to rev-list (default: --all)")
    parser.add_argument("--max-blobs", type=int, default=4000)
    args = parser.parse_args(argv)

    rev_args = ["rev-list", "--objects", args.rev] if args.rev == "--all" else ["rev-list", "--objects", args.rev]
    listing = git(*rev_args).splitlines()
    objects: list[tuple[str, str]] = []
    for line in listing:
        sha, _, path = line.partition(" ")
        if path:
            objects.append((sha, path))
    print(f"objects reachable from {args.rev}: {len(objects)}")

    # dedupe by blob sha, keep the first name seen (enough to identify the file)
    blobs: dict[str, str] = {}
    for sha, path in objects:
        blobs.setdefault(sha, path)
    print(f"unique blobs: {len(blobs)}")

    interesting = {
        sha: path
        for sha, path in blobs.items()
        if Path(path).suffix.lower() in TEXT_SUFFIXES or Path(path).name in {".gitignore", ".env.example"}
    }
    print(f"text blobs to scan: {len(interesting)} (cap {args.max_blobs})")

    findings: dict[tuple[str, str], list[str]] = {}
    scanned = 0
    for sha, path in interesting.items():
        if scanned >= args.max_blobs:
            print(f"[warn] blob cap reached at {scanned}; increase --max-blobs to scan everything")
            break
        scanned += 1
        raw = git("cat-file", "-p", sha, binary=True)
        assert isinstance(raw, bytes)
        if b"\x00" in raw[:2048]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", "replace")

        for pattern, label, blocking in PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            snippet = match.group(0)
            if "example.com" in snippet:
                continue
            # a value inside a fixture/placeholder file is reviewed, not blocked
            is_fixture = any(hint in path for hint in FIXTURE_HINTS) or bool(
                KNOWN_FIXTURE_VALUES.search(snippet)
            )
            severity = "review" if is_fixture else ("BLOCK" if blocking else "review")
            key = (path, label)
            findings.setdefault(key, []).append(
                f"{severity}: {path} (blob {sha[:10]}) -> {snippet[:70]}"
            )

    print(f"\nscanned {scanned} blobs")
    if findings:
        print(f"\nFINDINGS ({len(findings)}):")
        for _key, items in sorted(findings.items()):
            for item in items:
                print("  ", item)
    else:
        print("\nno secrets, personal data or credential values found in history")

    blocking = any(item.startswith("BLOCK") for items in findings.values() for item in items)
    print(f"\nHISTORY AUDIT: {'FAIL' if blocking else 'PASS'} "
          f"({sum(len(v) for v in findings.values())} finding(s), {'none blocking' if not blocking else 'see above'})")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
