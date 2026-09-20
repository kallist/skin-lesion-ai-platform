"""Public-release audit: credentials, personal data, private paths, tracked artefacts.

Run before publishing the repository.  It inspects the *tracked* files (what a
public clone would contain) plus a few working-tree paths that must never be
tracked, and reports findings by severity.

Usage (repository root):
    .\\.venv\\Scripts\\python.exe -X utf8 scripts\\audit_public_release.py
Exit code 0 = no blocking finding, 1 = at least one blocking finding.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# --- patterns that must never appear in a tracked text file -------------------
SECRET_PATTERNS = [
    (re.compile(r"SESSION_SECRET\s*=\s*[A-Za-z0-9_\-]{16,}"), "session secret value"),
    (re.compile(r"IMAGE_ENCRYPTION_KEY\s*=\s*[A-Za-z0-9_\-=+/]{20,}"), "image encryption key value"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "OpenAI-style API key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"(?i)\bpassword\s*=\s*['\"][^'\"]{6,}['\"]"), "hard-coded password literal"),
]

# --- filesystem paths that must not be published ------------------------------
# Absolute Windows paths leak the author's machine layout; they are replaced by
# portable placeholders in generated artifacts.
LOCAL_PATH_PATTERNS = [
    (re.compile(r"[A-Za-z]:\\\\?(?:Ataidi|Users|Projects|dev)\b"), "absolute local path"),
    (re.compile(r"[A-Za-z]:\\"), "absolute Windows path"),
]

# --- personal data ------------------------------------------------------------
PII_PATTERNS = [
    (re.compile(r"\b1[3-9]\d{9}\b"), "mainland mobile number"),
    # a bare 18-digit run is usually a float in a JSON artifact, so require an
    # ID-like context (label, or the trailing X checksum)
    (re.compile(r"(?i)(?:id|身份证|学号)\D{0,4}\d{17}[\dXx]"), "national ID number"),
    (re.compile(r"\b\d{17}X\b"), "national ID number (X checksum)"),
    (re.compile(r"\b\d{8,12}@(?:qq|163|126|gmail|outlook)\.com\b"), "personal-looking e-mail"),
    (re.compile(
        r"(?<![\w.+-])[\w.+-]+@(?!example\.com|example\.org)"
        # npm registry maintainer addresses that appear in package-lock.json
        r"(?!izs\.me|feross\.org|sindresorhus\.com|jprichardson\.com|npmjs\.com)"
        r"[\w-]+\.[A-Za-z]{2,}"
    ), "non-example e-mail address"),
]

# Files that must never be tracked
FORBIDDEN_TRACKED = {
    "backend/.env",
    ".env",
    "backend/data/app.sqlite3",
    "data/external_test",
}

# Runtime state that must stay untracked (informational, not blocking)
EXPECTED_UNTRACKED_GLOBS = [
    "backend/.env",
    "backend/data/*.sqlite3*",
    "backend/data/encrypted_uploads/*",
    "models/*.pt",
    "data/raw/*",
    "logs/*",
]

TEXT_SUFFIXES = {
    ".md", ".txt", ".json", ".csv", ".py", ".ps1", ".bat", ".ts", ".tsx", ".js", ".mjs",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".example", ".html", ".css", ".gitignore",
}

# Files where an absolute path is expected to remain (historical evidence of where
# external data lived, or migration records) and is therefore reported as a review
# item rather than a blocker.
PATH_REVIEW_ALLOWLIST = {
    "scripts/migrate_docs_layout.py",
    "docs/archive/project-origin/METRICS_SOURCE.md",
    "docs/archive/project-origin/EXTERNAL_TEST_REPORT.md",
    "docs/archive/project-origin/04_学校任务书验收对照表.md",
    "docs/archive/project-origin/02_皮肤癌图像检测系统_项目总结报告.md",
    "scripts/audit_school_test_data.py",
    "scripts/test_python_discovery.ps1",
    "scripts/build_school_package.ps1",
    "scripts/make_training_data_zip.ps1",
    "scripts/_run_package_e2e.ps1",
    "scripts/check_metrics_consistency.py",
    "scripts/audit_public_release.py",
    "scripts/audit_history.py",
    "scripts/make_manifests_portable.py",
    "scripts/make_artifacts_portable.py",
    "docs/testing/TEST_REPORT.md",
    # test fixtures intentionally assert on Windows-style input
    "backend/tests/test_security.py",
    # third-party package metadata (maintainer e-mails published on the npm registry)
    "frontend/package-lock.json",
}

SECRET_ALLOWLIST_HINTS = (
    "generate_secrets.py",        # documents the variable names, no values
    ".env.example",               # placeholders only
    "audit_public_release.py",    # this file contains the patterns
    "audit_history.py",           # the history scanner contains the same patterns
    "docs/engineering/SECURITY.md",
    "test_",                      # test fixtures use fake credentials
    "conftest.py",
)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return result.stdout


def tracked_files() -> list[str]:
    return [line for line in git("ls-files").splitlines() if line]


def is_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    return path.name in {".env.example", ".gitignore", "requirements.txt"}


def scan_file(rel: str, blockers: list[str], reviews: list[str]) -> None:
    path = REPO / rel
    if not path.is_file() or not is_text(path):
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return

    # A documentation line may legitimately quote a variable name together with a
    # placeholder.  Mark it explicitly instead of allowlisting the whole file:
    #   <!-- audit-allow-secret: placeholder example -->
    quoted = "audit-allow-secret" in text

    for pattern, label in SECRET_PATTERNS:
        if pattern.search(text):
            if quoted or any(hint in rel for hint in SECRET_ALLOWLIST_HINTS):
                reviews.append(f"{rel}: possible {label} (allowlisted context — verify manually)")
            else:
                blockers.append(f"{rel}: possible {label}")

    for pattern, label in LOCAL_PATH_PATTERNS:
        if pattern.search(text):
            if rel in PATH_REVIEW_ALLOWLIST:
                reviews.append(f"{rel}: {label} retained for provenance")
            else:
                blockers.append(f"{rel}: {label}")

    for pattern, label in PII_PATTERNS:
        for match in pattern.finditer(text):
            snippet = match.group(0)
            if "example.com" in snippet or "example.org" in snippet:
                continue
            if any(hint in rel for hint in ("test_", "conftest.py")):
                reviews.append(f"{rel}: {label} in test fixture ({snippet})")
                break
            blockers.append(f"{rel}: {label} ({snippet})")
            break


def main() -> int:
    files = tracked_files()
    blockers: list[str] = []
    reviews: list[str] = []
    info: list[str] = []

    print(f"tracked files: {len(files)}")

    for rel in files:
        scan_file(rel, blockers, reviews)

    # forbidden tracked paths
    for forbidden in FORBIDDEN_TRACKED:
        hits = [rel for rel in files if rel == forbidden or rel.startswith(forbidden + "/")]
        if hits:
            blockers.append(f"forbidden path tracked: {forbidden} ({len(hits)} file(s))")

    # files that look like runtime data
    for rel in files:
        lowered = rel.lower()
        if lowered.endswith((".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".enc")):
            blockers.append(f"runtime data file tracked: {rel}")
        if lowered.endswith((".pt", ".pth", ".onnx", ".ckpt")):
            info.append(f"model binary tracked: {rel} (large; consider removing before publishing)")

    # untracked runtime state that should stay untracked
    status = git("status", "--porcelain", "--ignored")
    ignored = {line[3:].strip() for line in status.splitlines() if line.startswith("!!")}
    for expected in EXPECTED_UNTRACKED_GLOBS:
        root = expected.split("*")[0].rstrip("/")
        if not any(entry.startswith(root) for entry in ignored):
            info.append(f"expected untracked path not reported as ignored: {expected}")

    # runtime state in the working tree that must never be committed
    runtime_dirs = [
        REPO / "backend" / "data",
        REPO / "backend" / "data" / "encrypted_uploads",
        REPO / "logs",
        REPO / ".runtime",
    ]
    for directory in runtime_dirs:
        if not directory.is_dir():
            continue
        entries = [p for p in directory.rglob("*") if p.is_file()]
        if entries:
            info.append(
                f"local runtime state present (untracked, must stay untracked): "
                f"{directory.relative_to(REPO).as_posix()} ({len(entries)} file(s))"
            )

    # large tracked files
    for rel in files:
        path = REPO / rel
        if path.is_file() and path.stat().st_size > 2_000_000:
            info.append(f"large tracked file: {rel} ({path.stat().st_size / 1_048_576:.1f} MB)")

    # dataset presence in git history is out of scope, but report working tree state
    data_dirs = [p for p in (REPO / "data" / "raw", REPO / "数据") if p.exists()]
    for directory in data_dirs:
        count = sum(1 for _ in directory.rglob("*") if _.is_file())
        info.append(f"local-only dataset directory present (untracked): {directory.relative_to(REPO)} ({count} files)")

    print("\n--- BLOCKING ---")
    if blockers:
        for item in blockers:
            print(f"  [BLOCK] {item}")
    else:
        print("  none")

    print("\n--- REVIEW ---")
    if reviews:
        for item in sorted(set(reviews))[:40]:
            print(f"  [review] {item}")
        if len(set(reviews)) > 40:
            print(f"  ... and {len(set(reviews)) - 40} more")
    else:
        print("  none")

    print("\n--- INFO ---")
    for item in info:
        print(f"  [info] {item}")

    verdict = "FAIL" if blockers else "PASS"
    print(f"\nAUDIT: {verdict} ({len(blockers)} blocking, {len(set(reviews))} review, {len(info)} info)")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
