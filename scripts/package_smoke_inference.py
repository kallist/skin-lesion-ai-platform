"""End-to-end inference check for the packaged copy.

Run with the package's own Python (temporarily linked to the development
environment during packaging).  It talks to the backend that the packaged
START.bat launched, performs one real detection with a real image, and prints a
verdict.  Nothing is written into the repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

API = "http://127.0.0.1:8000/api/v1"
PACKAGE = Path(__file__).resolve().parents[1]


def find_image() -> Path | None:
    manifest = PACKAGE / "data" / "manifests" / "test.csv"
    if not manifest.exists():
        return None
    for line in manifest.read_text(encoding="utf-8").splitlines()[1:]:
        candidate = Path(line.split(",")[0])
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    import time

    problems: list[str] = []
    with httpx.Client(base_url=API, timeout=60.0) as client:
        health = client.get("/health")
        if health.status_code != 200:
            print(f"[smoke] FAIL health: HTTP {health.status_code}")
            return 1
        body = health.json()
        print(f"[smoke] health: status={body['status']} database={body['database']} "
              f"model={body['model']} version={body['model_version']}")
        if not (body["database"] and body["model"]):
            problems.append("database or model not ready")

        info = client.get("/model/info").json()
        print(f"[smoke] model: {info['architecture']} {info['model_version']} "
              f"input={info['input_size']} calibration={info['calibration']}")
        if info["architecture"] != "resnet50":
            problems.append(f"unexpected architecture {info['architecture']}")
        if "stub" in str(info["model_version"]).lower():
            problems.append("the served model is the test stub, not the trained model")

        username = f"pkgcheck{int(time.time())}"
        register = client.post("/auth/register", json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "Pack!Check2026",
        })
        if register.status_code != 201:
            problems.append(f"register failed: HTTP {register.status_code}")
        csrf = client.cookies.get("csrf_token") or ""

        image = find_image()
        if image is None:
            problems.append("no test image available for the inference check")
        else:
            with image.open("rb") as handle:
                payload = handle.read()
            response = client.post(
                "/detections",
                files={"image": (image.name, payload, "image/jpeg")},
                data={"save_history": "true"},
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": f"pkgcheck-{username}"},
            )
            if response.status_code != 201:
                problems.append(f"detection failed: HTTP {response.status_code} {response.text[:120]}")
            else:
                result = response.json()
                probabilities = result["probabilities"]
                print(f"[smoke] inference: {image.name} -> {result['prediction']} "
                      f"confidence={result['confidence']:.4f} "
                      f"p(benign)={probabilities['benign']:.4f} p(malignant)={probabilities['malignant']:.4f}")
                if abs(sum(probabilities.values()) - 1.0) > 1e-4:
                    problems.append("probabilities do not sum to 1")
                if result["model_version"] != info["model_version"]:
                    problems.append("model version mismatch between /model/info and the detection")

    print()
    if problems:
        print("PACKAGE INFERENCE CHECK: FAIL")
        for problem in problems:
            print("  -", problem)
        return 1
    print("PACKAGE INFERENCE CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
