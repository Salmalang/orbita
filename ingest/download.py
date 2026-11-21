"""Download the registered datasets into data/raw/<id>/, verify hashes, unpack archives.

Usage:  .venv/Scripts/python -m ingest download [dataset_id ...]
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ingest.registry import DATASETS, Dataset, RemoteFile

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "MANIFEST.json"
USER_AGENT = "aeroguard-data-fetch/1.0"

# Windows 10+ ships bsdtar (libarchive), which unpacks zip, rar and 7z.
_TAR_CANDIDATES = [Path(r"C:\Windows\System32\tar.exe"), Path("/usr/bin/bsdtar")]


class IntegrityError(RuntimeError):
    pass


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)
    tmp.replace(dest)


def _extract(archive: Path, into: Path) -> None:
    tar = next((t for t in _TAR_CANDIDATES if t.exists()), None)
    if tar is None:
        raise RuntimeError("No archive tool found (need bsdtar / Windows tar.exe)")
    into.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(tar), "-xf", str(archive), "-C", str(into)], check=True)


def fetch_file(ds: Dataset, rf: RemoteFile) -> dict:
    folder = RAW / ds.id
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / rf.name
    if not dest.exists():
        print(f"  downloading {rf.name} ...", flush=True)
        _fetch(rf.url, dest)
    digest = sha256_of(dest)
    if rf.sha256 and digest != rf.sha256:
        dest.unlink()
        raise IntegrityError(f"{ds.id}/{rf.name}: sha256 {digest} != published {rf.sha256}")
    if rf.extract:
        target = folder / "extracted" / Path(rf.name).stem
        if not target.exists():
            _extract(dest, target)
    return {"file": rf.name, "bytes": dest.stat().st_size, "sha256": digest,
            "publisher_sha256_verified": bool(rf.sha256), "url": rf.url}


def download(ids: list[str] | None = None) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    for ds_id in ids or list(DATASETS):
        ds = DATASETS[ds_id]
        print(f"[{ds.id}] {ds.title}", flush=True)
        manifest[ds.id] = {
            "title": ds.title, "page": ds.page, "doi": ds.doi, "license": ds.license,
            "files": [fetch_file(ds, rf) for rf in ds.files],
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    download(sys.argv[1:] or None)
