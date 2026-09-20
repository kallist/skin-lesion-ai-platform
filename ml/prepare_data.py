"""Stage the raw dataset into ``data/raw`` and build train/val/test manifests.

Usage
-----
python ml/prepare_data.py                 # auto-detect the raw dataset
python ml/prepare_data.py --data <path-to-raw-dataset>

The raw dataset is copied (not moved) so the original source directory stays
untouched.  A hardlink is used when possible to avoid duplicating ~90 MB.

The generated manifests store repository-relative paths (``data/raw/<class>/<file>``),
so no absolute paths from the author's machine end up in the repository.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from pathlib import Path

from .config import CLASS_NAMES, DATASET_REPORT_PATH, MANIFEST_DIR, RAW_DIR, SEED
from .dataset import audit_dataset, build_manifests, discover_raw_root, render_audit_markdown

LOGGER = logging.getLogger("ml.prepare_data")


def stage_raw(source: Path, dest: Path, *, copy: bool = True) -> dict[str, int]:
    """Copy/link the class folders of ``source`` into ``dest``."""
    dest.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for cls in CLASS_NAMES:
        src_dir = source / cls
        if not src_dir.is_dir():
            # tolerate differently-cased folder names
            matches = [p for p in source.iterdir() if p.is_dir() and p.name.lower() == cls]
            if not matches:
                raise FileNotFoundError(f"Missing class folder '{cls}' in {source}")
            src_dir = matches[0]
        dst_dir = dest / cls
        dst_dir.mkdir(parents=True, exist_ok=True)
        n = 0
        for img in sorted(src_dir.rglob("*")):
            if not img.is_file():
                continue
            target = dst_dir / img.name
            if target.exists():
                n += 1
                continue
            if copy:
                try:
                    os.link(img, target)  # hardlink: zero extra bytes
                except OSError:
                    shutil.copy2(img, target)
            else:
                shutil.copy2(img, target)
            n += 1
        counts[cls] = n
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Stage dataset + build manifests")
    parser.add_argument("--data", default=None, help="raw dataset root (auto-detected if omitted)")
    parser.add_argument("--dest", default=str(RAW_DIR))
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--test-fraction", type=float, default=0.15)
    parser.add_argument("--no-stage", action="store_true", help="audit only, do not copy files")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    source = discover_raw_root(args.data)
    print(f"[prepare_data] raw dataset root: {source}")

    dest = Path(args.dest)
    if not args.no_stage:
        counts = stage_raw(source, dest)
        print(f"[prepare_data] staged into {dest}: {counts}")

    audit = audit_dataset(source)
    print(
        f"[prepare_data] audit: total={audit.total_images} "
        f"benign={audit.per_class.get('benign', 0)} malignant={audit.per_class.get('malignant', 0)} "
        f"broken={len(audit.broken_images)} dup_groups={audit.duplicate_groups} "
        f"cross_class_dup={audit.cross_class_duplicate_groups}"
    )
    DATASET_REPORT_PATH.write_text(render_audit_markdown(audit), encoding="utf-8")

    summary = build_manifests(
        audit,
        out_dir=MANIFEST_DIR,
        val_fraction=args.val_fraction,
        test_fraction=args.test_fraction,
        seed=args.seed,
    )
    DATASET_REPORT_PATH.write_text(
        render_audit_markdown(audit, summary), encoding="utf-8"
    )
    print(f"[prepare_data] splits: {summary['counts']}")
    print(f"[prepare_data] integrity passed: {summary['integrity']['passed']}")
    print(json.dumps(summary["per_class"], ensure_ascii=False))
    print(f"[prepare_data] manifests -> {MANIFEST_DIR}")
    print(f"[prepare_data] report    -> {DATASET_REPORT_PATH}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
