"""CLI: python -m ingest download [ids...] | python -m ingest list"""
import sys

from ingest.download import download
from ingest.registry import DATASETS

if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["list"]
    if cmd == "download":
        download(args or None)
    elif cmd == "list":
        for d in DATASETS.values():
            print(f"{d.id:22} {d.license:12} {d.page}")
    else:
        sys.exit(f"unknown command {cmd!r}; use 'download' or 'list'")
