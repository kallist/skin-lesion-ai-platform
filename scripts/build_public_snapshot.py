"""Build a clean, single-commit snapshot of the repository for public release.

Why: the repository history contains material that has since been moved out of the
working tree (for example the project requirement PDF), so publishing the existing
history would republish it.  This script copies the *current* working tree into a
fresh repository with exactly one commit, so the published history starts clean.

What is in the snapshot: everything in the working tree except `.git`, minus
whatever `.gitignore` already excludes (datasets, model weights, the real `.env`,
runtime database/uploads/logs).  Nothing is deleted from the original repository.

Usage (repository root):
    .\\.venv\\Scripts\\python.exe -X utf8 scripts\\build_public_snapshot.py
        [--workspace <dir>]      # default: ~/portfolio-release   (working copy)
        [--bare <dir.git>]       # default: ~/portfolio-release.git
        [--message "<commit subject>"]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKIP_TOP_LEVEL = {".git", ".runtime", "logs", ".venv", "venv"}

DEFAULT_SUBJECT = "Skin Lesion AI Platform: portfolio snapshot"
DEFAULT_BODY = """Clean single-commit snapshot of the finished project.

The development history contained material that is no longer part of the working
tree; this snapshot starts a fresh history containing only the current state.
See private-release-exclusions.md for what is excluded and what still needs a
rights decision before the repository is made public.
"""

# Project-origin material (the requirement document, the school/enterprise delivery
# package and its Word/PDF exports).  Their publication rights have not been
# confirmed, so they are excluded from the public snapshot by default.  Nothing is
# deleted from the working repository: pass --keep-origin-material to include them
# once the rights question is settled.
ORIGIN_MATERIAL = [
    "皮肤癌图像检测系统项目任务书V1.0.0.pdf",
    "deliverables/docs",
    "docs/archive/project-origin",
]


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {cwd}:\n{result.stdout}\n{result.stderr}")
    return result.stdout


def remove_tree(target: Path) -> None:
    """Delete a directory tree, clearing read-only attributes (Windows git objects)."""
    if not target.exists():
        return

    def on_error(function, path, exc_info):
        import os
        import stat

        try:
            os.chmod(path, stat.S_IWRITE)
            function(path)
        except OSError:
            raise exc_info[1]

    shutil.rmtree(target, onerror=on_error)


def copy_working_tree(target: Path) -> int:
    remove_tree(target)
    target.mkdir(parents=True)

    copied = 0
    for entry in REPO.iterdir():
        if entry.name in SKIP_TOP_LEVEL:
            continue
        destination = target / entry.name
        if entry.is_dir():
            # ignore_dangling_symlinks + ignore the same heavy/ignored directories
            def ignore(directory, names, _root=REPO):
                ignored = set()
                for name in names:
                    candidate = Path(directory) / name
                    try:
                        relative = candidate.relative_to(REPO).as_posix()
                    except ValueError:
                        continue
                    if name in {"node_modules", "__pycache__", "dist", "test-results",
                                "playwright-report", ".pytest_cache", ".venv"}:
                        ignored.add(name)
                    elif relative in {"data/raw", "data/external_test", "数据"}:
                        ignored.add(name)
                return ignored

            shutil.copytree(entry, destination, ignore=ignore)
        else:
            shutil.copy2(entry, destination)
        copied += 1

    # Heavy local-only artifacts are never published and must not be copied either:
    # the dataset (git-ignored), the model binaries and the local runtime state.
    for relative in ("data/raw", "data/external_test", "data/uploads", "data/encrypted_uploads",
                     "data/tmp", "数据", "logs", ".runtime", "backend/data"):
        remove_tree(target / relative)
    for pattern in ("*.pt", "*.pth", "*.onnx", "*.ckpt", "*.sqlite3", "*.sqlite3-wal",
                    "*.sqlite3-shm", "*.enc", "*.log"):
        for path in target.rglob(pattern):
            if path.is_file():
                path.unlink()
    for name in ("backend/.env", ".env"):
        env_file = target / name
        if env_file.is_file():
            env_file.unlink()

    return copied


def resolve_identity() -> tuple[str, str]:
    """Reuse the identity already used by this repository's commits.

    The snapshot repository has no configuration of its own, and silently falling
    back to a global identity (or failing) would either leak an unrelated account
    or break the build, so the existing local identity is copied over.
    """
    def read(key: str, fallback: str) -> str:
        try:
            value = run("config", "--local", key, cwd=REPO).strip()
        except SystemExit:
            value = ""
        return value or fallback

    return read("user.name", "Skin Lesion AI Platform"), read("user.email", "noreply@example.com")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a clean public snapshot repository")
    # default destinations live outside the repository; pass absolute paths to override
    parser.add_argument("--workspace", default="~/portfolio-release")
    parser.add_argument("--bare", default="~/portfolio-release.git")
    parser.add_argument("--message", default=DEFAULT_SUBJECT)
    parser.add_argument("--keep-bare", action="store_true", help="do not recreate the bare mirror")
    parser.add_argument(
        "--keep-origin-material",
        action="store_true",
        help="include the project-origin documents (only after their publication rights are confirmed)",
    )
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).expanduser().resolve()
    bare = Path(args.bare).expanduser().resolve()

    print(f"[1/6] copying working tree -> {workspace}")
    entries = copy_working_tree(workspace)
    print(f"      copied {entries} top-level entries")

    if not args.keep_origin_material:
        keep = {"docs/archive/project-origin/README.md"}
        for relative in ORIGIN_MATERIAL:
            target = workspace / relative
            if target.is_dir():
                removed = 0
                for child in sorted(target.rglob("*"), reverse=True):
                    child_rel = f"{relative}/{child.relative_to(target).as_posix()}"
                    if child_rel in keep:
                        continue
                    if child.is_file():
                        child.unlink()
                        removed += 1
                    elif child.is_dir() and not any(child.iterdir()):
                        child.rmdir()
                print(f"      excluded (rights not confirmed): {relative}/ ({removed} files)")
            elif target.is_file():
                target.unlink()
                print(f"      excluded (rights not confirmed): {relative}")
        # the placeholder that tells a public reader why the archive is not here is
        # tracked in the working repository but must be present in the snapshot too
        placeholder = REPO / "docs" / "archive" / "README.md"
        if placeholder.is_file():
            destination = workspace / "docs" / "archive" / "README.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(placeholder, destination)
            print("      kept: docs/archive/README.md (explains the exclusion)")
    else:
        print("      keeping project-origin material (--keep-origin-material)")

    print("[2/6] initialising a fresh repository")
    run("init", "--initial-branch=main", cwd=workspace)
    name, email = resolve_identity()
    run("config", "--local", "user.name", name, cwd=workspace)
    run("config", "--local", "user.email", email, cwd=workspace)
    print(f"      commit identity: {name} <{email}>")
    run("add", "-A", cwd=workspace)

    staged = run("diff", "--cached", "--name-only", cwd=workspace).splitlines()
    print(f"      staged files: {len(staged)}")

    forbidden = [
        name
        for name in staged
        if name.endswith((".pt", ".pth", ".onnx", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".enc"))
        or name.startswith(("data/raw/", "data/external_test/", "鏁版嵁/"))
        or name in {"backend/.env", ".env"}
    ]
    if forbidden:
        print("[FAIL] the snapshot would contain files that must never be published:")
        for name in forbidden[:20]:
            print("   -", name)
        return 1
    print("      no model weights, datasets, database or secrets staged")

    print("[3/6] committing")
    run("commit", "--quiet", "-m", args.message, "-m", DEFAULT_BODY, cwd=workspace)
    head = run("rev-parse", "HEAD", cwd=workspace).strip()
    subject = run("log", "--oneline", "-1", cwd=workspace).strip()
    print(f"      {subject}")

    if not args.keep_bare:
        print(f"[4/6] recreating bare mirror -> {bare}")
        remove_tree(bare)
        bare.parent.mkdir(parents=True, exist_ok=True)
        run("init", "--bare", "--initial-branch=main", str(bare), cwd=bare.parent)
        run("push", str(bare), "main", "--quiet", cwd=workspace)
    else:
        print("[4/6] keeping the existing bare mirror")

    print("[5/6] verifying the snapshot")
    count = run("rev-list", "--count", "HEAD", cwd=workspace).strip()
    files = run("ls-files", cwd=workspace).splitlines()
    print(f"      commits: {count}")
    print(f"      tracked files: {len(files)}")
    if count != "1":
        print("[FAIL] the snapshot must contain exactly one commit")
        return 1
    print(f"\n[ok] snapshot ready: {workspace}")
    print(f"     bare mirror:    {bare}")
    print(f"     HEAD:           {head}")
    print("\nPublish (choose one):")
    print(f'  git -C "{workspace}" remote add origin https://github.com/<user>/skin-lesion-ai-platform.git')
    print(f'  git -C "{workspace}" push -u origin main')
    return 0


if __name__ == "__main__":
    sys.exit(main())
