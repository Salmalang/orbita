"""Load and validate the demo site definition."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from backend.app.schemas import Site

SITE_PATH = Path(__file__).parent / "data" / "site.json"


def load_site(path: Path = SITE_PATH) -> Site:
    return Site.model_validate_json(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def get_site() -> Site:
    return load_site()
