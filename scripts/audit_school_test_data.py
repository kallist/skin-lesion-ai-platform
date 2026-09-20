"""School external-test data audit + staging (no training, no model changes).

Steps
-----
1. Recursively scan the school test directory (TEST_DATA_DIR) for images and label files.
2. Verify every image decodes with Pillow (count corrupted / unreadable).
3. Detect duplicate basenames across class folders (the evaluator matches by basename,
   so collisions must be neutralised by staging instead of touching the original data).
4. Compute SHA-256 for every test image and compare against the original train / val /
   internal-test manifests to detect exact-image leakage.
5. Build a FLAT staging directory (default ``artifacts/external_test/staging``) with
   class-prefixed filenames plus a ``labels.csv``, so the unmodified evaluator can run.
   The original TEST_DATA_DIR is only read, never modified.

Label source (priority B): the test directory itself is organised as
``benign/`` and ``malignant/``, so the directory name is the ground truth.

Usage:
    python scripts/audit_school_test_data.py --input "E:\\Ataidi\\验证数据\\验证数据"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = False

REPO = Path(__file__).resolve().parents[1]
SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
LABEL_FILE_HINTS = (
    "labels.csv", "label.csv", "test.csv", "ground_truth.csv",
    "groundtruth.csv", "metadata.csv", "labels.json", "annotations.json",
)
CLASS_DIR_ALIASES = {
    "benign": "benign", "0": "benign", "良性": "benign", "normal": "benign",
    "malignant": "malignant", "1": "malignant", "恶性": "malignant",
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="school test data directory (read-only)")
    parser.add_argument("--staging", default="artifacts/external_test/staging")
    args = parser.parse_args()

    root = Path(args.input).resolve()
    if not root.is_dir():
        raise SystemExit(f"TEST_DATA_DIR not found: {root}")

    staging = (REPO / args.staging).resolve()
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    print(f"[audit] test data dir : {root}")
    print(f"[audit] staging dir   : {staging}")

    # ---------------------------------------------------------------- scan
    images = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)
    label_files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.name.lower() in LABEL_FILE_HINTS
    )
    print(f"[audit] images found  : {len(images)}")
    print(f"[audit] label files   : {[str(p.relative_to(root)) for p in label_files] or 'none'}")

    dirs = sorted({p.parent for p in images})
    print("[audit] directories containing images:")
    for directory in dirs:
        print(f"         {directory.relative_to(root) if directory != root else '.'}  "
              f"({sum(1 for p in images if p.parent == directory)} images)")

    # ---------------------------------------------------------------- class from directory
    label_source = None
    per_image_class: dict[Path, str] = {}
    for path in images:
        rel_parts = path.relative_to(root).parts[:-1]
        found = None
        for part in reversed(rel_parts):
            key = part.strip().lower()
            if key in CLASS_DIR_ALIASES:
                found = CLASS_DIR_ALIASES[key]
                break
        if found is None:
            print(f"[audit] WARNING: cannot infer a class for {path.relative_to(root)}")
            continue
        per_image_class[path] = found
        label_source = label_source or "directory structure (benign/ malignant/)"

    counts = Counter(per_image_class.values())

    # ---------------------------------------------------------------- decode check
    corrupted: list[str] = []
    sizes: Counter = Counter()
    modes: Counter = Counter()
    for path in images:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                sizes[image.size] += 1
                modes[image.mode] += 1
        except Exception as exc:  # noqa: BLE001
            corrupted.append(f"{path.relative_to(root)}: {type(exc).__name__}")

    # ---------------------------------------------------------------- duplicate basenames
    by_name: dict[str, list[Path]] = defaultdict(list)
    for path in images:
        by_name[path.name].append(path)
    duplicates = {name: [str(p.relative_to(root)) for p in paths]
                  for name, paths in by_name.items() if len(paths) > 1}

    # ---------------------------------------------------------------- leakage check
    manifest_rows = []
    for split in ("train", "val", "test"):
        manifest = REPO / "data" / "manifests" / f"{split}.csv"
        if manifest.exists():
            frame = pd.read_csv(manifest)
            for _, row in frame.iterrows():
                manifest_rows.append((split, str(row["sha256"]), str(row["relative_path"])))
    internal_hashes: dict[str, set[str]] = {"train": set(), "val": set(), "test": set()}
    for split, sha, _ in manifest_rows:
        internal_hashes[split].add(sha)

    external_hashes: dict[Path, str] = {path: sha256_of(path) for path in images}
    external_sha_set = set(external_hashes.values())
    overlap = {split: sorted(external_sha_set & hashes) for split, hashes in internal_hashes.items()}

    # ---------------------------------------------------------------- staging
    rows = []
    for path in images:
        label = per_image_class.get(path)
        if label is None:
            continue
        staged_name = f"{label}__{path.name}"
        target = staging / staged_name
        if target.exists():
            stem, suffix = target.stem, target.suffix
            index = 2
            while (staging / f"{stem}_{index}{suffix}").exists():
                index += 1
            target = staging / f"{stem}_{index}{suffix}"
        shutil.copy2(path, target)
        rows.append({
            "filename": target.name,
            "label": label,
            "original_relative_path": str(path.relative_to(root)).replace("\\", "/"),
            "sha256": external_hashes[path],
            "source": "school_external_test",
        })

    labels_csv = staging / "labels.csv"
    pd.DataFrame(rows)[["filename", "label"]].to_csv(labels_csv, index=False, encoding="utf-8-sig")

    audit = {
        "test_data_dir": str(root),
        "label_source": label_source,
        "images_total": len(images),
        "by_extension": dict(Counter(p.suffix.lower() for p in images)),
        "by_class": dict(counts),
        "directories": [str(d.relative_to(root)) if d != root else "." for d in dirs],
        "label_files_found": [str(p.relative_to(root)) for p in label_files],
        "corrupted_images": corrupted,
        "image_sizes": {f"{w}x{h}": n for (w, h), n in sizes.most_common()},
        "image_modes": dict(modes),
        "duplicate_basenames": duplicates,
        "overlap_with_internal": {split: len(values) for split, values in overlap.items()},
        "overlap_examples": {split: values[:5] for split, values in overlap.items()},
        "staging_dir": str(staging),
        "labels_csv": str(labels_csv),
        "staged_images": len(rows),
    }
    out_dir = REPO / "artifacts" / "external_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out_dir / "sha256.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["relative_path", "filename", "class", "sha256"])
        for path in images:
            writer.writerow([str(path.relative_to(root)), path.name,
                             per_image_class.get(path, ""), external_hashes[path]])

    print()
    print("===== AUDIT SUMMARY =====")
    print(f"total images      : {len(images)}")
    print(f"extensions        : {audit['by_extension']}")
    print(f"benign            : {counts.get('benign', 0)}")
    print(f"malignant         : {counts.get('malignant', 0)}")
    print(f"corrupted         : {len(corrupted)}")
    print(f"image sizes       : {audit['image_sizes']}")
    print(f"image modes       : {audit['image_modes']}")
    print(f"duplicate basenames: {len(duplicates)} {list(duplicates)[:5]}")
    print(f"overlap vs train  : {len(overlap['train'])}")
    print(f"overlap vs val    : {len(overlap['val'])}")
    print(f"overlap vs test   : {len(overlap['test'])}")
    print(f"staged images     : {len(rows)} -> {staging}")
    print(f"labels csv        : {labels_csv}")
    print(f"audit json        : {out_dir / 'audit.json'}")
    if corrupted:
        for item in corrupted[:10]:
            print(f"  CORRUPTED {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
