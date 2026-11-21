"""Model registry with a traceable model card for every version.

Each version stores the model file (not committed; rebuilt by `python -m ai.train`) and a
card.json (committed) with: measured metrics, configuration, the SHA-256 of every training data
file (from data/raw/MANIFEST.json) and the SHA-256 of the model file. These hashes are what the
platform anchors on Hedera, so anyone can check which data produced which model.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "ai" / "registry"
MANIFEST = ROOT / "data" / "raw" / "MANIFEST.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dataset_fingerprints(dataset_ids: list[str]) -> dict[str, dict[str, str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    return {d: {f["file"]: f["sha256"] for f in manifest.get(d, {}).get("files", [])} for d in dataset_ids}


def training_data_hash(fingerprints: dict) -> str:
    return hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest()


def save(name: str, version: str, model, *, metrics: dict, config: dict, datasets: list[str],
         description: str) -> dict:
    folder = REGISTRY / name / version
    folder.mkdir(parents=True, exist_ok=True)
    model_path = folder / "model.joblib"
    joblib.dump(model, model_path)
    fps = dataset_fingerprints(datasets)
    card = {
        "name": name, "version": version, "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_sha256": _sha256(model_path),
        "training_data": fps, "training_data_sha256": training_data_hash(fps),
        "config": config, "metrics": metrics,
    }
    (folder / "card.json").write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")
    return card


def load(name: str, version: str | None = None):
    folder = REGISTRY / name
    version = version or sorted(p.name for p in folder.iterdir() if (p / "model.joblib").exists())[-1]
    card = json.loads((folder / version / "card.json").read_text(encoding="utf-8"))
    model_path = folder / version / "model.joblib"
    if _sha256(model_path) != card["model_sha256"]:
        raise RuntimeError(f"{name} {version}: model file does not match its card (tampered or rebuilt)")
    return joblib.load(model_path), card


def cards() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(REGISTRY.glob("*/*/card.json"))]
