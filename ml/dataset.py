"""Dataset auditing, manifest building and leakage-safe splitting.

Responsibilities
----------------
1. ``audit_dataset``  – scan the raw tree, hash every image, detect broken /
   duplicate / cross-class-duplicate images and produce a JSON + Markdown
   report.
2. ``build_manifests`` – create deterministic ``train/val/test`` manifests with
   duplicate-group-aware, group-safe splitting.
3. ``SkinLesionDataset`` – a torch ``Dataset`` reading a manifest CSV.

Splitting policy
----------------
The shipped dataset has no ``patient_id`` / ``lesion_id`` column, therefore the
split is *image level and stratified by class*.  To avoid leakage every image
with an identical SHA-256 (or an identical perceptual hash) is assigned to the
same split via a shared "group key", and manifests are verified afterwards so
that ``train ∩ val = train ∩ test = val ∩ test = ∅`` by filename, SHA-256 and
perceptual hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from PIL import Image

from .config import (
    ARTIFACTS_DIR,
    CLASS_NAMES,
    CLASS_TO_IDX,
    DATA_DIR,
    DATASET_REPORT_PATH,
    DEFAULT_TEST_FRACTION,
    DEFAULT_VAL_FRACTION,
    DOCS_DIR,
    IMAGE_SIZE,
    MANIFEST_DIR,
    PROJECT_ROOT,
    RAW_CLASS_DIRS,
    RAW_DIR,
    SEED,
)

# Guard against decompression bombs while auditing untrusted images.
Image.MAX_IMAGE_PIXELS = 64_000_000

LOGGER = logging.getLogger("ml.dataset")
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class ImageRecord:
    path: str
    relative_path: str
    filename: str
    label: str
    label_idx: int
    size_bytes: int
    width: int
    height: int
    mode: str
    sha256: str
    phash: str
    broken: bool = False
    error: str = ""

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DatasetAudit:
    root: str
    total_images: int = 0
    per_class: dict[str, int] = field(default_factory=dict)
    extensions: dict[str, int] = field(default_factory=dict)
    broken_images: list[dict[str, str]] = field(default_factory=list)
    unique_sha256: int = 0
    duplicate_groups: int = 0
    duplicate_images: int = 0
    cross_class_duplicate_groups: int = 0
    cross_class_duplicate_images: int = 0
    perceptual_duplicate_groups: int = 0
    perceptual_duplicate_images: int = 0
    width_stats: dict[str, float] = field(default_factory=dict)
    height_stats: dict[str, float] = field(default_factory=dict)
    color_modes: dict[str, int] = field(default_factory=dict)
    label_source: str = ""
    has_patient_id: bool = False
    has_lesion_id: bool = False
    has_metadata: bool = False
    metadata_files: list[str] = field(default_factory=list)
    existing_split: bool = False
    class_balance: dict[str, float] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)
    duplicate_map: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload.pop("records", None)  # keep the summary file small
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------
def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def perceptual_hash(path: str | Path, hash_size: int = 8) -> str:
    """Difference hash (dHash) of the greyscale image.

    dHash compares each pixel with its right neighbour, which is far more
    discriminative than a plain average-hash for same-sized lesion photos.
    A 64-bit hash is returned as a string of '0'/'1'.
    """
    try:
        with Image.open(path) as im:
            small = im.convert("L").resize((hash_size + 1, hash_size), Image.BILINEAR)
            pixels = np.asarray(small, dtype=np.int16)
            bits = pixels[:, 1:] > pixels[:, :-1]
            return "".join("1" if b else "0" for b in bits.reshape(-1))
    except Exception:  # noqa: BLE001
        return ""


def average_hash(path: str | Path, hash_size: int = 8) -> str:
    """Average hash (aHash), kept for reporting next to the dHash."""
    try:
        with Image.open(path) as im:
            small = im.convert("L").resize((hash_size, hash_size), Image.BILINEAR)
            pixels = np.asarray(small, dtype=np.float32).reshape(-1)
            bits = pixels > pixels.mean()
            return "".join("1" if b else "0" for b in bits)
    except Exception:  # noqa: BLE001
        return ""


def hamming(a: str, b: str) -> int:
    if not a or not b or len(a) != len(b):
        return 64
    return sum(1 for x, y in zip(a, b) if x != y)


# ---------------------------------------------------------------------------
# Raw tree discovery
# ---------------------------------------------------------------------------
def discover_raw_root(explicit: str | Path | None = None) -> Path:
    """Locate the directory that contains the class folders.

    Search order: explicit argument, ``DATASET_ROOT`` environment variable,
    ``data/raw`` (staged), then a few conventional locations.  The shipped
    archive nests the tree as ``数据/数据/训练数据/{benign,malignant}``, so a
    couple of levels are probed instead of assuming a fixed layout.
    """
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    env_root = os.environ.get("DATASET_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates += [
        RAW_DIR,
        RAW_DIR / "数据" / "训练数据",
        RAW_DIR / "训练数据",
        PROJECT_ROOT / "数据" / "数据" / "训练数据",
        PROJECT_ROOT / "数据",
    ]
    for cand in candidates:
        if not cand.is_dir():
            continue
        subdirs = {p.name.lower() for p in cand.iterdir() if p.is_dir()}
        if {"benign", "malignant"} & subdirs:
            return cand
        # search one level deeper
        for sub in cand.iterdir():
            if not sub.is_dir():
                continue
            inner = {p.name.lower() for p in sub.iterdir() if p.is_dir()}
            if {"benign", "malignant"} & inner:
                return sub
            for sub2 in sub.iterdir():
                if not sub2.is_dir():
                    continue
                inner2 = {p.name.lower() for p in sub2.iterdir() if p.is_dir()}
                if {"benign", "malignant"} & inner2:
                    return sub2
    raise FileNotFoundError(
        "Could not locate a dataset root containing 'benign' and 'malignant' folders. "
        f"Searched: {[str(c) for c in candidates]}"
    )


def _iter_images(root: Path) -> Iterable[tuple[Path, str]]:
    """Yield ``(path, raw_class_dir_name)`` for every supported image."""
    for cls_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        raw_name = cls_dir.name
        key = raw_name.strip().lower()
        if key not in RAW_CLASS_DIRS:
            LOGGER.warning("Skipping unrecognised class folder: %s", raw_name)
            continue
        for img in sorted(cls_dir.rglob("*")):
            if img.is_file() and img.suffix.lower() in SUPPORTED_EXTS:
                yield img, key


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
def audit_dataset(root: str | Path | None = None, *, compute_phash: bool = True) -> DatasetAudit:
    root_path = discover_raw_root(root)
    LOGGER.info("Auditing dataset root: %s", root_path)
    audit = DatasetAudit(root=str(root_path))

    records: list[ImageRecord] = []
    for path, raw_class in _iter_images(root_path):
        label = RAW_CLASS_DIRS[raw_class]
        rel = str(path.relative_to(root_path))
        rec = ImageRecord(
            path=str(path),
            relative_path=rel,
            filename=path.name,
            label=label,
            label_idx=CLASS_TO_IDX[label],
            size_bytes=path.stat().st_size,
            width=0,
            height=0,
            mode="",
            sha256=sha256_file(path),
            phash="",
        )
        try:
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                rec.width, rec.height = im.size
                rec.mode = im.mode
            if compute_phash:
                rec.phash = perceptual_hash(path)
        except Exception as exc:  # noqa: BLE001
            rec.broken = True
            rec.error = f"{type(exc).__name__}: {exc}"
            audit.broken_images.append({"path": str(path), "error": rec.error})
        records.append(rec)

    audit.total_images = len(records)
    audit.per_class = dict(Counter(r.label for r in records))
    audit.extensions = dict(Counter(Path(r.filename).suffix.lower() for r in records))
    audit.color_modes = dict(Counter(r.mode for r in records if r.mode))

    healthy = [r for r in records if not r.broken]
    if healthy:
        widths = np.array([r.width for r in healthy], dtype=float)
        heights = np.array([r.height for r in healthy], dtype=float)
        audit.width_stats = _stats(widths)
        audit.height_stats = _stats(heights)

    # --- exact duplicates -------------------------------------------------
    by_sha: dict[str, list[ImageRecord]] = defaultdict(list)
    for rec in records:
        by_sha[rec.sha256].append(rec)
    dup_groups = {k: v for k, v in by_sha.items() if len(v) > 1}
    audit.unique_sha256 = len(by_sha)
    audit.duplicate_groups = len(dup_groups)
    audit.duplicate_images = sum(len(v) for v in dup_groups.values())
    audit.duplicate_map = {
        h: [f"{r.label}/{r.filename}" for r in v] for h, v in dup_groups.items()
    }
    cross = [v for v in dup_groups.values() if len({r.label for r in v}) > 1]
    audit.cross_class_duplicate_groups = len(cross)
    audit.cross_class_duplicate_images = sum(len(v) for v in cross)

    # --- perceptual near duplicates ---------------------------------------
    # Computed **per class**: two different classes are never merged into one
    # leakage group, and near-duplicate detection must not depend on the class
    # balance of the dataset.
    if compute_phash:
        ph_groups: dict[tuple[str, str], list[ImageRecord]] = defaultdict(list)
        for rec in healthy:
            if rec.phash:
                ph_groups[(rec.label, rec.phash)].append(rec)
        per_class_clusters: dict[str, list[list[ImageRecord]]] = defaultdict(list)
        for label in CLASS_NAMES:
            hashes = sorted({h for (lab, h) in ph_groups if lab == label})
            used: set[str] = set()
            for h in hashes:
                if h in used:
                    continue
                cluster = list(ph_groups[(label, h)])
                used.add(h)
                for other in hashes:
                    if other in used:
                        continue
                    if hamming(h, other) <= 2:
                        cluster.extend(ph_groups[(label, other)])
                        used.add(other)
                if len(cluster) > 1:
                    per_class_clusters[label].append(cluster)
        merged = [c for clusters in per_class_clusters.values() for c in clusters]
        audit.perceptual_duplicate_groups = len(merged)
        audit.perceptual_duplicate_images = sum(len(c) for c in merged)

    # --- labels / metadata discovery --------------------------------------
    audit.label_source = (
        "folder-name (benign / malignant class directories shipped with the dataset)"
    )
    meta_files: list[str] = []
    for pattern in ("*.csv", "*.json", "*.txt", "*.md", "*.xlsx"):
        meta_files += [str(p.relative_to(root_path)) for p in root_path.rglob(pattern)]
    audit.metadata_files = meta_files[:50]
    audit.has_metadata = bool(meta_files)
    joined = " ".join(meta_files).lower()
    audit.has_patient_id = "patient" in joined
    audit.has_lesion_id = "lesion" in joined
    audit.existing_split = any(
        token in joined for token in ("train", "val", "test", "split")
    )

    total = audit.total_images or 1
    audit.class_balance = {k: round(v / total, 4) for k, v in audit.per_class.items()}
    audit.records = [r.to_row() for r in records]

    if audit.cross_class_duplicate_images:
        audit.notes.append(
            "CRITICAL: identical images appear in both classes; they are grouped "
            "into a single split to prevent leakage."
        )
    if audit.perceptual_duplicate_images:
        audit.notes.append(
            f"{audit.perceptual_duplicate_images} images belong to near-duplicate "
            "clusters (aHash distance <= 2); clusters are kept inside one split."
        )
    if not audit.has_patient_id and not audit.has_lesion_id:
        audit.notes.append(
            "No patient_id / lesion_id available: image-level stratified split "
            "with duplicate-group awareness is used instead of a patient-level split."
        )
    return audit


def _stats(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        return {}
    return {
        "min": float(values.min()),
        "p25": float(np.percentile(values, 25)),
        "median": float(np.median(values)),
        "p75": float(np.percentile(values, 75)),
        "max": float(values.max()),
        "mean": float(values.mean()),
    }


# ---------------------------------------------------------------------------
# Manifests / splitting
# ---------------------------------------------------------------------------
def _group_key(record: dict[str, Any], dup_groups: dict[str, str]) -> str:
    """Return the leakage group key of a record."""
    sha = record["sha256"]
    if sha in dup_groups:
        return dup_groups[sha]
    return f"single:{sha}"


def build_manifests(
    audit: DatasetAudit,
    *,
    out_dir: str | Path = MANIFEST_DIR,
    val_fraction: float = DEFAULT_VAL_FRACTION,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    seed: int = SEED,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    """Create train/val/test manifests from an audit, group-safe and stratified.

    The published ``path`` column is written relative to the repository root
    (``data/raw/<class>/<file>``) so that manifests are portable and contain no
    absolute paths; readers resolve them through ``SkinLesionDataset._resolve``.
    Absolute paths still resolve if an older manifest is used locally.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records = [r for r in audit.records if not r["broken"]]

    # Union-find over duplicates.  Exact duplicates are grouped by content
    # hash regardless of class (identical pixels in two classes is a labelling
    # problem that must be surfaced); perceptual near-duplicates are only
    # merged **inside the same class** so that distinct lesions are never
    # forced into one split.
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for rec in records:
        find(f"sha:{rec['sha256']}")
        if rec.get("phash"):
            find(f"ph:{rec['label']}:{rec['phash']}")
            union(f"sha:{rec['sha256']}", f"ph:{rec['label']}:{rec['phash']}")

    # Merge perceptual clusters within hamming distance 2 (same class only).
    ph_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        if rec.get("phash"):
            ph_by_key[(rec["label"], rec["phash"])].append(rec)
    for label in CLASS_NAMES:
        hashes = sorted({h for (lab, h) in ph_by_key if lab == label})
        for i, h1 in enumerate(hashes):
            for h2 in hashes[i + 1 :]:
                if hamming(h1, h2) <= 2:
                    union(f"ph:{label}:{h1}", f"ph:{label}:{h2}")

    # A group's label: if a group mixes classes it is dropped from training
    # entirely (ambiguous / mislabeled) - recorded explicitly.
    group_members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        group_members[find(f"sha:{rec['sha256']}")].append(rec)

    dropped_groups: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    for key, members in group_members.items():
        labels = {m["label"] for m in members}
        if len(labels) > 1:
            dropped_groups.append(
                {"group": key, "labels": sorted(labels), "files": [m["filename"] for m in members]}
            )
            continue
        groups.append({"key": key, "label": members[0]["label"], "members": members})

    rng = np.random.default_rng(seed)
    assignment: dict[str, str] = {}
    for label in CLASS_NAMES:
        subset = [g for g in groups if g["label"] == label]
        # deterministic order before shuffling keeps runs reproducible
        subset.sort(key=lambda g: g["key"])
        idx = rng.permutation(len(subset))
        subset = [subset[i] for i in idx]
        n = len(subset)
        n_test = int(round(n * test_fraction))
        n_val = int(round(n * val_fraction))
        if n >= 10:
            n_test = max(1, n_test)
            n_val = max(1, n_val)
        for i, g in enumerate(subset):
            if i < n_test:
                assignment[g["key"]] = "test"
            elif i < n_test + n_val:
                assignment[g["key"]] = "val"
            else:
                assignment[g["key"]] = "train"

    rows: dict[str, list[dict[str, Any]]] = {"train": [], "val": [], "test": []}

    root_for_rel = Path(data_root) if data_root else Path(audit.root if audit.root else RAW_DIR)

    def relative_to_repo(record: dict[str, Any]) -> str:
        """Portable path for the manifest.

        Paths under this repository's dataset directory become
        ``data/raw/<class>/<file>``; paths under another dataset root (e.g. a
        caller's temporary directory) are stored relative to that root
        (``<class>/<file>``), so no manifest ever carries an absolute path.
        """
        absolute = Path(record["path"])
        if not absolute.is_absolute():
            return absolute.as_posix()
        try:
            return f"data/raw/{absolute.relative_to(RAW_DIR).as_posix()}"
        except ValueError:
            pass
        for base in (root_for_rel, PROJECT_ROOT):
            if not base:
                continue
            try:
                return absolute.relative_to(base).as_posix()
            except ValueError:
                continue
        return absolute.as_posix()

    for g in groups:
        split = assignment[g["key"]]
        for m in g["members"]:
            rows[split].append(
                {
                    "path": relative_to_repo(m),
                    "relative_path": m["relative_path"],
                    "filename": m["filename"],
                    "label": m["label"],
                    "label_idx": m["label_idx"],
                    "sha256": m["sha256"],
                    "phash": m["phash"],
                    "group": g["key"],
                    "split": split,
                }
            )

    for split, items in rows.items():
        items.sort(key=lambda r: r["relative_path"])
        df = pd.DataFrame(items)
        df.to_csv(out_dir / f"{split}.csv", index=False, encoding="utf-8")

    all_df = pd.concat([pd.DataFrame(rows[s]) for s in ("train", "val", "test")], ignore_index=True)
    all_df.to_csv(out_dir / "all.csv", index=False, encoding="utf-8")

    verification = verify_split_integrity(rows)
    summary = {
        "seed": seed,
        "val_fraction": val_fraction,
        "test_fraction": test_fraction,
        "counts": {k: len(v) for k, v in rows.items()},
        "per_class": {
            split: dict(Counter(r["label"] for r in items)) for split, items in rows.items()
        },
        "groups": {split: len({r["group"] for r in items}) for split, items in rows.items()},
        "dropped_ambiguous_groups": dropped_groups,
        "integrity": verification,
        "split_strategy": (
            "group-aware stratified image-level split (no patient_id in dataset); "
            "exact-SHA and aHash<=2 near-duplicate clusters are never split across sets"
        ),
    }
    with (out_dir / "split_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    return summary


def verify_split_integrity(rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Assert that no image leaks across splits.

    Overlap is checked on SHA-256 (content identity), on the leakage group and
    on ``(label, filename)`` - filenames alone are **not** unique in this
    dataset (benign/953.jpg and malignant/953.jpg are different images), so a
    bare filename comparison would produce false positives.
    """
    result: dict[str, Any] = {"checks": {}, "passed": True}

    def overlap(a: list[dict[str, Any]], b: list[dict[str, Any]], key) -> int:
        if callable(key):
            sa = {key(r) for r in a}
            sb = {key(r) for r in b}
        else:
            sa = {r[key] for r in a}
            sb = {r[key] for r in b}
        return len(sa & sb)

    checks = (
        ("sha256", lambda r: r["sha256"]),
        ("group", lambda r: r["group"]),
        ("label_filename", lambda r: f"{r['label']}/{r['filename']}"),
    )
    for name, key in checks:
        for s1, s2 in (("train", "val"), ("train", "test"), ("val", "test")):
            n = overlap(rows[s1], rows[s2], key)
            label = f"{s1}_vs_{s2}_by_{name}"
            result["checks"][label] = n
            if n:
                result["passed"] = False

    total = sum(len(v) for v in rows.values())
    unique = len({r["sha256"] for split in rows.values() for r in split})
    result["checks"]["total_rows"] = total
    result["checks"]["unique_sha256"] = unique
    result["checks"]["distinct_content_every_row"] = total == unique
    result["checks"]["note"] = (
        "total_rows may legitimately exceed unique_sha256 when the raw dataset "
        "contains byte-identical images; those are grouped into one split."
    )
    return result


# ---------------------------------------------------------------------------
# torch Dataset
# ---------------------------------------------------------------------------
try:  # torch is optional for the audit-only helpers
    from torch.utils.data import Dataset as _TorchDataset
except Exception:  # pragma: no cover - torch always present in this project
    _TorchDataset = object  # type: ignore[assignment,misc]


class SkinLesionDataset(_TorchDataset):  # type: ignore[misc,valid-type]
    """Manifest-backed dataset.

    Defined at module level (not built dynamically) because Windows
    ``DataLoader`` workers pickle the dataset class to spawn subprocesses.
    """

    def __init__(
        self,
        manifest: str | Path | pd.DataFrame,
        transform=None,
        *,
        root: str | Path | None = None,
        check_images: bool = False,
    ) -> None:
        if isinstance(manifest, pd.DataFrame):
            self.frame = manifest.reset_index(drop=True)
        else:
            self.frame = pd.read_csv(manifest)
        if self.frame.empty:
            raise ValueError(f"Manifest is empty: {manifest}")
        self.transform = transform
        self.root = Path(root) if root else None
        self.check_images = check_images
        self._manifest_dir = Path(manifest).parent if isinstance(manifest, (str, Path)) else None
        self._paths = [self._resolve(p) for p in self.frame["path"].tolist()]

    def _candidate_bases(self) -> list[Path]:
        bases: list[Path] = []
        if self.root is not None:
            bases.append(self.root)
        if self._manifest_dir is not None:
            bases.append(self._manifest_dir)
        bases += [PROJECT_ROOT, RAW_DIR, DATA_DIR]
        return bases

    def _resolve(self, path: str) -> str:
        """Resolve a manifest entry to a real file.

        Published manifests store repository-relative paths (``data/raw/<class>/<file>``),
        so resolution accepts both that form and a plain dataset-relative form
        (``<class>/<file>``) against several bases: the explicit ``root``, the
        manifest directory, the project root and the dataset directories.
        Absolute entries from older manifests still resolve unchanged.
        """
        candidate = Path(path)
        if candidate.is_absolute():
            return str(candidate)

        relative = PurePosixPath(str(path).replace("\\", "/"))
        variants = [relative]
        if relative.parts[:2] == ("data", "raw"):
            variants.append(PurePosixPath(*relative.parts[2:]))
        else:
            variants.append(PurePosixPath("data", "raw", *relative.parts))

        bases = self._candidate_bases()
        for variant in variants:
            variant_str = variant.as_posix()
            for base in bases:
                resolved = base / variant_str
                if resolved.exists():
                    return str(resolved)
        return str(candidate)

    def __len__(self) -> int:
        return len(self.frame)

    def __getitem__(self, index: int):
        import torch  # noqa: F401  (keeps torch import local to the worker)
        from PIL import Image as PILImage

        path = self._paths[index]
        label = int(self.frame.iloc[index]["label_idx"])
        try:
            with PILImage.open(path) as im:
                image = im.convert("RGB")
        except Exception as exc:  # noqa: BLE001
            if self.check_images:
                raise
            LOGGER.warning("Unreadable image %s (%s) - substituting blank image", path, exc)
            image = PILImage.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), (0, 0, 0))
        if self.transform is not None:
            image = self.transform(image)
        return image, label, path


def make_dataset(*args, **kwargs) -> SkinLesionDataset:
    """Factory returning a torch-compatible dataset instance."""
    return SkinLesionDataset(*args, **kwargs)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _display_root(root: str | None) -> str:
    """Machine-independent rendering of the dataset root for generated reports.

    A report that is published must not leak the author's absolute paths, so a
    root inside the repository is shown relative to it and anything else is
    shown as an explicit placeholder.
    """
    if not root:
        return "<unset>"
    path = Path(root)
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return "<external to this repository>"


def render_audit_markdown(audit: DatasetAudit, split_summary: dict[str, Any] | None = None) -> str:
    p = audit.per_class
    total = audit.total_images or 1
    lines: list[str] = []
    lines.append("# DATASET REPORT — 皮肤病变图像数据集审计报告\n")
    lines.append("> 自动生成：`python ml/dataset.py audit`。所有数字均来自真实扫描，未做任何人工修饰。\n")
    lines.append("## 1. 数据集来源\n")
    lines.append(f"- 数据集根目录：`{_display_root(audit.root)}`")
    lines.append(f"- 标签来源：{audit.label_source}")
    lines.append(f"- 是否包含 metadata 文件：{'是' if audit.has_metadata else '否'}")
    if audit.metadata_files:
        lines.append(f"- metadata 文件：{', '.join(f'`{m}`' for m in audit.metadata_files[:10])}")
    lines.append(f"- 是否存在 patient_id：{'是' if audit.has_patient_id else '否'}")
    lines.append(f"- 是否存在 lesion_id：{'是' if audit.has_lesion_id else '否'}")
    lines.append(f"- 是否已存在 train/val/test 划分：{'是' if audit.existing_split else '否'}")
    lines.append("")
    lines.append("## 2. 数据规模与类别分布\n")
    lines.append("| 类别 | 图片数 | 占比 |")
    lines.append("| --- | ---: | ---: |")
    for cls in CLASS_NAMES:
        n = p.get(cls, 0)
        lines.append(f"| {cls} | {n} | {n / total:.2%} |")
    lines.append(f"| **合计** | **{audit.total_images}** | 100% |")
    lines.append("")
    lines.append("## 3. 图片格式与尺寸\n")
    lines.append(f"- 扩展名分布：{audit.extensions}")
    lines.append(f"- 色彩模式分布：{audit.color_modes}")
    if audit.width_stats:
        ws, hs = audit.width_stats, audit.height_stats
        lines.append(
            f"- 宽度：min={ws['min']:.0f} p25={ws['p25']:.0f} median={ws['median']:.0f} "
            f"p75={ws['p75']:.0f} max={ws['max']:.0f}"
        )
        lines.append(
            f"- 高度：min={hs['min']:.0f} p25={hs['p25']:.0f} median={hs['median']:.0f} "
            f"p75={hs['p75']:.0f} max={hs['max']:.0f}"
        )
    lines.append("")
    lines.append("## 4. 数据质量检查\n")
    lines.append(f"- 损坏 / 无法解码图片：**{len(audit.broken_images)}**")
    lines.append(f"- 唯一 SHA-256 数量：{audit.unique_sha256}")
    lines.append(f"- 完全重复分组数：{audit.duplicate_groups}（涉及 {audit.duplicate_images} 张）")
    lines.append(
        f"- **跨类别**完全重复分组数：**{audit.cross_class_duplicate_groups}**"
        f"（涉及 {audit.cross_class_duplicate_images} 张）"
    )
    lines.append(
        f"- 近似重复（dHash 距离 ≤ 2，同类别内检测）分组数：{audit.perceptual_duplicate_groups}"
        f"（涉及 {audit.perceptual_duplicate_images} 张）"
    )
    if audit.duplicate_map:
        lines.append("")
        lines.append("重复明细：\n")
        lines.append("| SHA-256 (前12位) | 文件 |")
        lines.append("| --- | --- |")
        for h, files in list(audit.duplicate_map.items())[:20]:
            lines.append(f"| `{h[:12]}` | {', '.join(files)} |")
    lines.append("")
    lines.append("## 5. 标签规则\n")
    lines.append(
        "数据集自带 `benign` / `malignant` 两个目录，属于 LABEL RULE A（数据已明确给出良性/恶性标签），"
        "因此直接使用目录名作为标签，无需任何医学语义推断。"
    )
    lines.append("")
    lines.append("## 6. 划分方案\n")
    if split_summary:
        lines.append(f"- 策略：{split_summary['split_strategy']}")
        lines.append(f"- 随机种子：{split_summary['seed']}")
        lines.append("")
        lines.append("| Split | 图片数 | benign | malignant | 分组数 |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for split in ("train", "val", "test"):
            pc = split_summary["per_class"][split]
            lines.append(
                f"| {split} | {split_summary['counts'][split]} | {pc.get('benign', 0)} | "
                f"{pc.get('malignant', 0)} | {split_summary['groups'][split]} |"
            )
        lines.append("")
        integrity = split_summary["integrity"]
        lines.append(
            f"- 泄漏检查：{'**PASS**' if integrity['passed'] else '**FAIL**'}"
            f"（SHA-256 / 分组 / 类别内文件名 三重交集均为 0）"
        )
        lines.append(f"- 校验明细：`{json.dumps(integrity['checks'], ensure_ascii=False)}`")
        if split_summary.get("dropped_ambiguous_groups"):
            lines.append(
                f"- 因同组内标签冲突被排除的组：{len(split_summary['dropped_ambiguous_groups'])}"
            )
    lines.append("")
    lines.append("## 7. 审计结论\n")
    for note in audit.notes:
        lines.append(f"- {note}")
    lines.append("")
    lines.append(
        "> 本报告由脚本生成，未对数据做任何主观修改。若后续更换数据集，请重新运行 "
        "`python ml/dataset.py audit --build-splits` 覆盖本文件。"
    )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dataset audit / manifest builder")
    parser.add_argument("command", choices=["audit", "split"], nargs="?", default="audit")
    parser.add_argument("--data", default=None, help="dataset root (auto-detected when omitted)")
    parser.add_argument("--out", default=str(DATASET_REPORT_PATH))
    parser.add_argument("--manifest-dir", default=str(MANIFEST_DIR))
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--val-fraction", type=float, default=DEFAULT_VAL_FRACTION)
    parser.add_argument("--test-fraction", type=float, default=DEFAULT_TEST_FRACTION)
    parser.add_argument("--build-splits", action="store_true", help="also build manifests")
    parser.add_argument("--no-phash", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    audit = audit_dataset(args.data, compute_phash=not args.no_phash)
    audit.to_json(ARTIFACTS_DIR / "dataset_audit.json")
    print(
        f"audited {audit.total_images} images | benign={audit.per_class.get('benign', 0)} "
        f"malignant={audit.per_class.get('malignant', 0)} | broken={len(audit.broken_images)} "
        f"| dup_groups={audit.duplicate_groups} | cross_class_dup={audit.cross_class_duplicate_groups}"
    )

    split_summary = None
    if args.command == "split" or args.build_splits:
        split_summary = build_manifests(
            audit,
            out_dir=args.manifest_dir,
            val_fraction=args.val_fraction,
            test_fraction=args.test_fraction,
            seed=args.seed,
        )
        print(f"splits: {split_summary['counts']} | integrity_passed={split_summary['integrity']['passed']}")

    md = render_audit_markdown(audit, split_summary)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
