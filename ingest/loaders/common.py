from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
CACHE = ROOT / "data" / "cache"


class DatasetMissing(FileNotFoundError):
    def __init__(self, dataset_id: str, path: Path):
        super().__init__(f"{path} not found. Run: .venv/Scripts/python -m ingest download {dataset_id}")
        self.dataset_id = dataset_id


def require(dataset_id: str, path: Path) -> Path:
    if not path.exists():
        raise DatasetMissing(dataset_id, path)
    return path
