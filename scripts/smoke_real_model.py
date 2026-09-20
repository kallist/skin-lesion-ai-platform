"""Real-model smoke test: API -> preprocessing -> PyTorch -> response.

Runs against a live backend (no mocks) using real dataset images, and verifies
the served probabilities match a direct in-process forward pass with the same
preprocessing contract.

Usage
-----
python scripts/smoke_real_model.py [--base-url http://127.0.0.1:8000] [--samples 12]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

API = "/api/v1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Real model end-to-end smoke test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--split", default="test")
    parser.add_argument("--model", default=str(PROJECT_ROOT / "models" / "best_model.pt"))
    args = parser.parse_args()

    manifest = PROJECT_ROOT / "data" / "manifests" / f"{args.split}.csv"
    if not manifest.exists():
        print(f"FAIL: manifest not found: {manifest}")
        return 2
    frame = pd.read_csv(manifest)
    # deterministic sample: first N rows after sorting by filename
    frame = frame.sort_values("relative_path").head(args.samples)
    print(f"[smoke] {len(frame)} real images from {manifest.name}")

    from ml.infer import SkinLesionPredictor

    predictor = SkinLesionPredictor(args.model)
    print(f"[smoke] local model: {predictor.architecture} {predictor.model_version} on {predictor.device}")

    failures: list[str] = []
    checked = 0
    latencies: list[float] = []
    correct = 0

    with httpx.Client(base_url=args.base_url, timeout=60.0) as client:
        health = client.get(f"{API}/health")
        if health.status_code != 200 or not health.json().get("model"):
            print(f"FAIL: backend not healthy: {health.text}")
            return 2
        print(f"[smoke] backend healthy, model={health.json()['model_version']}")

        # register a throwaway account
        username = f"smoke{int(time.time())}"
        register = client.post(
            f"{API}/auth/register",
            json={
                "email": f"{username}@example.com",
                "username": username,
                "password": "Sm0keTest!pass",
            },
        )
        if register.status_code != 201:
            print(f"FAIL: register failed: {register.status_code} {register.text}")
            return 2
        print(f"[smoke] registered {username}")

        csrf = client.cookies.get("csrf_token") or ""

        for _, row in frame.iterrows():
            path = Path(row["path"])
            if not path.exists():
                failures.append(f"missing file {path}")
                continue
            with path.open("rb") as fh:
                payload = fh.read()
            started = time.perf_counter()
            response = client.post(
                f"{API}/detections",
                files={"image": (path.name, payload, "image/jpeg")},
                data={"save_history": "true"},
                headers={
                    "Idempotency-Key": f"smoke-{row['sha256'][:16]}",
                    "X-CSRF-Token": csrf,
                },
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if response.status_code != 201:
                failures.append(f"{path.name}: HTTP {response.status_code} {response.text[:120]}")
                continue
            body = response.json()
            latencies.append(elapsed_ms)

            # ---- independent local forward pass with the same preprocessing ----
            from PIL import Image

            with Image.open(path) as im:
                local = predictor.predict_image(im.convert("RGB"))

            api_mal = body["probabilities"]["malignant"]
            local_mal = local["probabilities"]["malignant"]
            drift = abs(api_mal - local_mal)
            disclaimer_text = f"{body.get('disclaimer', '')}{body.get('advice', '')}"
            ok = (
                body["prediction"] == local["prediction"]
                and drift < 1e-4
                and abs(body["probabilities"]["benign"] + api_mal - 1.0) < 1e-4
                and body["model_version"] == predictor.model_version
                and ("不构成医学诊断" in disclaimer_text or "不能替代专业医生诊断" in disclaimer_text)
            )
            truth = row["label"]
            if body["prediction"] == truth:
                correct += 1
            mark = "ok " if ok else "BAD"
            print(
                f"[smoke] {mark} {path.name:14s} true={truth:9s} api={body['prediction']:9s} "
                f"p(mal)={api_mal:.4f} local={local_mal:.4f} drift={drift:.2e} "
                f"http={elapsed_ms:.0f}ms infer={body.get('inference_latency_ms', '?')}ms"
            )
            if not ok:
                failures.append(
                    f"{path.name}: api={body['prediction']}({api_mal:.4f}) "
                    f"local={local['prediction']}({local_mal:.4f}) drift={drift:.2e}"
                )
            checked += 1

        # history + image round trip
        listing = client.get(f"{API}/detections", params={"page": 1, "page_size": 5})
        if listing.status_code != 200 or listing.json()["total"] != checked:
            failures.append(f"history listing mismatch: {listing.text[:200]}")
        else:
            print(f"[smoke] history: {listing.json()['total']} records")
            first_id = listing.json()["items"][0]["id"]
            image = client.get(f"{API}/detections/{first_id}/image")
            if image.status_code != 200 or not image.content.startswith(b"\x89PNG"):
                failures.append(f"history image decrypt failed: {image.status_code}")
            else:
                print(f"[smoke] decrypted history image: {len(image.content)} bytes PNG")

            csv = client.get(f"{API}/detections/export")
            header = csv.text.splitlines()[0] if csv.status_code == 200 else ""
            if "malignant_probability" not in header:
                failures.append(f"CSV export invalid: {csv.status_code} {header[:80]}")
            else:
                print(f"[smoke] CSV export columns: {header}")

    if latencies:
        latencies.sort()
        print(
            f"[smoke] API latency: min={latencies[0]:.0f}ms median={latencies[len(latencies)//2]:.0f}ms "
            f"max={latencies[-1]:.0f}ms (n={len(latencies)})"
        )

    # Sanity floor: a consistent-but-broken model would pass the agreement check
    # above, so also require that the predictions are not worse than chance on
    # this small real sample (12 images -> chance = 0.5).
    sample_accuracy = correct / checked if checked else 0.0
    print(f"[smoke] sample accuracy on {checked} real images: {sample_accuracy:.3f} ({correct}/{checked})")
    if checked and sample_accuracy < 0.5:
        failures.append(
            f"sample accuracy {sample_accuracy:.3f} below the 0.5 sanity floor "
            f"({correct}/{checked} correct) - the served model looks broken"
        )

    report = {
        "checked": checked,
        "correct": correct,
        "sample_accuracy": round(sample_accuracy, 4),
        "failures": failures,
        "model_version": predictor.model_version,
        "architecture": predictor.architecture,
        "api_latency_ms": {
            "min": min(latencies) if latencies else None,
            "median": latencies[len(latencies) // 2] if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "verdict": "PASS" if not failures else "FAIL",
    }
    out = PROJECT_ROOT / "artifacts" / "real_model_smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[smoke] report -> {out}")

    if failures:
        print(f"\nSMOKE TEST FAILED ({len(failures)} issue(s)):")
        for item in failures:
            print("  -", item)
        return 1
    print("\nREAL MODEL SMOKE TEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
