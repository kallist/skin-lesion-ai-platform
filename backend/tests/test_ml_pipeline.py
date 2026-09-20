"""ML pipeline tests: transforms, dataset, split integrity, model, metrics.

These tests never download a dataset; they build tiny synthetic images in a
temporary directory and exercise the real code paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

torch = pytest.importorskip("torch", reason="torch is required for ML tests")

from ml.config import CLASS_TO_IDX, IMAGE_SIZE, ModelMeta  # noqa: E402
from ml.dataset import (  # noqa: E402
    audit_dataset,
    build_manifests,
    make_dataset,
    perceptual_hash,
    sha256_file,
    verify_split_integrity,
)
from ml.metrics import binary_metrics, expected_calibration_error, roc_curve_points  # noqa: E402
from ml.model import build_model, load_checkpoint, save_checkpoint  # noqa: E402
from ml.transforms import build_eval_transform, build_train_transform  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def tiny_dataset(tmp_path: Path) -> Path:
    """A miniature benign/malignant dataset (12 + 10 images)."""
    root = tmp_path / "raw"
    rng = np.random.default_rng(0)
    for label, count in (("benign", 12), ("malignant", 10)):
        folder = root / label
        folder.mkdir(parents=True)
        for index in range(count):
            array = rng.integers(0, 255, size=(64, 64, 3), dtype=np.uint8)
            Image.fromarray(array, mode="RGB").save(folder / f"{label}_{index}.jpg")
    # one corrupted file that must be detected and excluded
    (root / "benign" / "broken.jpg").write_bytes(b"\xff\xd8\xff\xe0not-a-real-jpeg")
    # an exact duplicate inside the benign class
    duplicate = root / "benign" / "benign_0.jpg"
    (root / "benign" / "benign_0_copy.jpg").write_bytes(duplicate.read_bytes())
    return root


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------
def test_train_transform_shape_and_range():
    transform = build_train_transform()
    tensor = transform(Image.new("RGB", (300, 220), (120, 80, 60)))
    assert tuple(tensor.shape) == (3, IMAGE_SIZE, IMAGE_SIZE)
    assert tensor.dtype == torch.float32
    assert tensor.min() > -6 and tensor.max() < 6  # normalised range


def test_eval_transform_shape_is_deterministic():
    transform = build_eval_transform()
    image = Image.new("RGB", (500, 300), (200, 150, 100))
    first = transform(image)
    second = transform(image)
    assert tuple(first.shape) == (3, IMAGE_SIZE, IMAGE_SIZE)
    assert torch.allclose(first, second)


def test_eval_transform_handles_non_square_and_grayscale():
    transform = build_eval_transform()
    grey = Image.new("L", (100, 400), 128).convert("RGB")
    assert tuple(transform(grey).shape) == (3, IMAGE_SIZE, IMAGE_SIZE)


def test_eval_transform_normalisation_matches_imagenet():
    from ml.config import IMAGENET_MEAN, IMAGENET_STD

    transform = build_eval_transform()
    tensor = transform(Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), (255, 255, 255)))
    expected = (1.0 - IMAGENET_MEAN[0]) / IMAGENET_STD[0]
    assert float(tensor[0, 0, 0]) == pytest.approx(expected, abs=1e-4)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
def test_audit_detects_broken_and_duplicate_images(tiny_dataset):
    audit = audit_dataset(tiny_dataset, compute_phash=True)
    # 12 benign + 10 malignant + 1 corrupted + 1 byte-identical copy
    assert audit.total_images == 24
    assert audit.per_class == {"benign": 14, "malignant": 10}
    assert len(audit.broken_images) == 1
    assert audit.duplicate_groups >= 1
    assert audit.unique_sha256 < audit.total_images


def test_audit_reports_label_source_and_metadata_flags(tiny_dataset):
    audit = audit_dataset(tiny_dataset, compute_phash=False)
    assert "folder-name" in audit.label_source
    assert audit.has_patient_id is False
    assert audit.has_lesion_id is False


def test_sha256_and_phash_are_stable(tiny_dataset):
    path = tiny_dataset / "benign" / "benign_0.jpg"
    assert sha256_file(path) == sha256_file(path)
    assert len(sha256_file(path)) == 64
    phash = perceptual_hash(path)
    assert len(phash) == 64
    assert phash == perceptual_hash(path)


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------
def test_split_has_no_leakage_and_covers_every_image(tiny_dataset, tmp_path):
    audit = audit_dataset(tiny_dataset, compute_phash=True)
    summary = build_manifests(audit, out_dir=tmp_path / "manifests", seed=42)
    assert summary["integrity"]["passed"] is True

    import pandas as pd

    frames = {
        split: pd.read_csv(tmp_path / "manifests" / f"{split}.csv")
        for split in ("train", "val", "test")
    }
    total = sum(len(frame) for frame in frames.values())
    assert total == audit.total_images - len(audit.broken_images)

    for key in ("filename", "sha256", "group"):
        for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
            assert not set(frames[a][key]) & set(frames[b][key]), f"{key} leaked {a}/{b}"


def test_split_is_deterministic_for_fixed_seed(tiny_dataset, tmp_path):
    audit = audit_dataset(tiny_dataset, compute_phash=False)
    first = build_manifests(audit, out_dir=tmp_path / "a", seed=7)
    second = build_manifests(audit, out_dir=tmp_path / "b", seed=7)
    assert first["counts"] == second["counts"]
    assert (tmp_path / "a" / "train.csv").read_text() == (tmp_path / "b" / "train.csv").read_text()


def test_verify_split_integrity_flags_overlap():
    rows = {
        "train": [{"filename": "a.jpg", "sha256": "x", "group": "g1", "label": "benign"}],
        "val": [{"filename": "a.jpg", "sha256": "x", "group": "g1", "label": "benign"}],
        "test": [],
    }
    result = verify_split_integrity(rows)
    assert result["passed"] is False
    assert result["checks"]["train_vs_val_by_sha256"] == 1
    assert result["checks"]["train_vs_val_by_label_filename"] == 1


def test_verify_split_integrity_accepts_same_filename_in_different_classes():
    """benign/953.jpg and malignant/953.jpg are different images."""
    rows = {
        "train": [{"filename": "953.jpg", "sha256": "a", "group": "g1", "label": "benign"}],
        "val": [{"filename": "953.jpg", "sha256": "b", "group": "g2", "label": "malignant"}],
        "test": [],
    }
    result = verify_split_integrity(rows)
    assert result["checks"]["train_vs_val_by_label_filename"] == 0
    assert result["passed"] is True


def test_manifest_has_expected_columns(tiny_dataset, tmp_path):
    import pandas as pd

    audit = audit_dataset(tiny_dataset, compute_phash=False)
    build_manifests(audit, out_dir=tmp_path / "m", seed=1)
    frame = pd.read_csv(tmp_path / "m" / "train.csv")
    for column in ("path", "label", "label_idx", "sha256", "split"):
        assert column in frame.columns
    assert set(frame["label_idx"].unique()) <= {0, 1}


# ---------------------------------------------------------------------------
# Dataset object
# ---------------------------------------------------------------------------
def test_dataset_returns_normalised_tensor_and_label(tiny_dataset, tmp_path):
    import pandas as pd

    audit = audit_dataset(tiny_dataset, compute_phash=False)
    build_manifests(audit, out_dir=tmp_path / "m", seed=1)
    frame = pd.read_csv(tmp_path / "m" / "train.csv")
    # manifests store dataset-relative paths; the reader gets the dataset root
    assert not any(str(entry).startswith(("C:", "D:", "E:")) for entry in frame["path"])
    dataset = make_dataset(frame, transform=build_eval_transform(), root=tiny_dataset)
    assert len(dataset) == len(frame)
    image, label, path = dataset[0]
    assert tuple(image.shape) == (3, IMAGE_SIZE, IMAGE_SIZE)
    assert label in (0, 1)
    assert Path(path).exists()


def test_dataset_rejects_empty_manifest(tmp_path):
    import pandas as pd

    frame = pd.DataFrame(columns=["path", "label_idx"])
    with pytest.raises(ValueError):
        make_dataset(frame, transform=build_eval_transform())


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def test_model_forward_shape_and_probabilities():
    model = build_model("resnet18", 2, pretrained=False)
    model.eval()
    with torch.no_grad():
        logits = model(torch.zeros(2, 3, IMAGE_SIZE, IMAGE_SIZE))
    assert tuple(logits.shape) == (2, 2)
    probs = torch.softmax(logits, dim=1)
    assert torch.allclose(probs.sum(dim=1), torch.ones(2), atol=1e-5)
    assert probs.min() >= 0


def test_checkpoint_roundtrip_preserves_outputs(tmp_path):
    model = build_model("resnet18", 2, pretrained=False)
    meta = ModelMeta(architecture="resnet18", model_version="test-1.0")
    path = tmp_path / "model.pt"
    save_checkpoint(path, model, meta)

    loaded, payload = load_checkpoint(path)
    assert payload["class_mapping"] == CLASS_TO_IDX
    assert payload["input_size"] == IMAGE_SIZE
    assert payload["model_version"] == "test-1.0"

    model.eval()
    loaded.eval()
    batch = torch.randn(1, 3, IMAGE_SIZE, IMAGE_SIZE)
    with torch.no_grad():
        assert torch.allclose(model(batch), loaded(batch), atol=1e-5)


def test_load_checkpoint_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_checkpoint(tmp_path / "nope.pt")


def test_load_checkpoint_corrupted_file(tmp_path):
    path = tmp_path / "broken.pt"
    path.write_bytes(b"not a torch checkpoint")
    with pytest.raises(RuntimeError):
        load_checkpoint(path)


def test_model_meta_roundtrip(tmp_path):
    meta = ModelMeta(architecture="resnet50", best_val_metric={"accuracy": 0.9})
    path = tmp_path / "meta.json"
    meta.to_json(path)
    restored = ModelMeta.from_json(path)
    assert restored.architecture == "resnet50"
    assert restored.best_val_metric["accuracy"] == pytest.approx(0.9)
    assert json.loads(path.read_text())["class_names"] == ["benign", "malignant"]


def test_unsupported_architecture_is_rejected():
    with pytest.raises(ValueError):
        build_model("vgg16", 2, pretrained=False)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def test_binary_metrics_perfect_predictions():
    metrics = binary_metrics([0, 0, 1, 1], [0, 0, 1, 1], [0.1, 0.2, 0.9, 0.8])
    assert metrics["accuracy"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert metrics["malignant_recall"] == 1.0
    assert metrics["confusion_matrix"] == {"tp": 2, "tn": 2, "fp": 0, "fn": 0}


def test_binary_metrics_handles_missed_malignancy():
    metrics = binary_metrics([0, 0, 1, 1], [0, 0, 0, 0], [0.1, 0.2, 0.4, 0.45])
    assert metrics["malignant_recall"] == 0.0
    assert metrics["specificity"] == 1.0
    assert metrics["confusion_matrix"]["fn"] == 2


def test_metrics_never_exceed_one():
    rng = np.random.default_rng(3)
    y_true = rng.integers(0, 2, 200)
    y_prob = rng.random(200)
    y_pred = (y_prob >= 0.5).astype(int)
    metrics = binary_metrics(y_true, y_pred, y_prob)
    for key in ("accuracy", "precision", "recall_sensitivity", "specificity", "f1", "roc_auc"):
        assert 0.0 <= metrics[key] <= 1.0


def test_roc_curve_starts_at_origin_and_ends_at_one():
    y_true = [0, 0, 1, 1]
    y_prob = [0.1, 0.4, 0.35, 0.8]
    fpr, tpr, _ = roc_curve_points(y_true, y_prob)
    assert fpr[0] == pytest.approx(0.0)
    assert tpr[-1] == pytest.approx(1.0)


def test_ece_is_zero_for_perfectly_calibrated_predictions():
    y_true = np.array([0, 0, 1, 1])
    y_prob = np.array([0.0, 0.0, 1.0, 1.0])
    assert expected_calibration_error(y_true, y_prob) == pytest.approx(0.0, abs=1e-6)


def test_metrics_do_not_crash_on_single_class():
    metrics = binary_metrics([0, 0], [0, 0], [0.1, 0.2])
    assert metrics["n"] == 2
    assert np.isnan(metrics["roc_auc"])
