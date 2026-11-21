"""Loader for the ARIA industrial accident database (BARPI, France; data.gouv.fr extraction, 2020).

Used as real accident statistics until the Protection Civile (Tunisia) data arrives.
"""
from __future__ import annotations

import pandas as pd

from ingest.loaders.common import CACHE, RAW, require

ARIA_XLSX = RAW / "aria" / "aria.xlsx"
_ARIA_COLUMNS = {
    "Titre": "title", "Type de publication": "publication_type", "Date": "date", "Numéro ARIA": "aria_id",
    "Code NAF": "sector", "Pays": "country", "Département": "department", "Commune": "town",
    "Type d'accident": "accident_type", "Type évènement": "event_types", "Matière": "substances",
    "Equipements": "equipment", "Classe de danger CLP": "clp_hazard", "Causes profondes": "root_causes",
    "Causes premières": "primary_causes", "Conséquences": "consequences", "Echelle": "scale",
    "Adresse web": "url", "Contenu": "summary",
}


def load_aria(use_cache: bool = True) -> pd.DataFrame:
    cache = CACHE / "aria.pkl"
    if use_cache and cache.exists():
        return pd.read_pickle(cache)
    require("aria", ARIA_XLSX)
    df = pd.read_excel(ARIA_XLSX).rename(columns=_ARIA_COLUMNS)
    df["date"] = pd.to_datetime(df["date"], format="%d/%m/%Y", errors="coerce")
    for c in ("event_types", "equipment", "root_causes", "primary_causes", "consequences", "sector"):
        df[c] = df[c].fillna("").astype(str)
    df["is_fire"] = df["event_types"].str.contains("Incendie", case=False)
    df["is_explosion"] = df["event_types"].str.contains("Explosion", case=False)
    CACHE.mkdir(parents=True, exist_ok=True)
    df.to_pickle(cache)
    return df


def split_tags(series: pd.Series) -> pd.Series:
    """'A, B,C' -> one row per tag (stripped). Used for cause / equipment statistics."""
    return series.str.split(",").explode().str.strip().loc[lambda s: s.str.len() > 2]


def first_category(series: pd.Series) -> pd.Series:
    """ARIA flattens 'category, sub-category, ...' into one string. The first item is the
    top-level category, so counting it gives one cause per event (no double counting)."""
    s = series[series.str.len() > 0]
    return s.str.split(",").str[0].str.strip()


def fire_statistics(df: pd.DataFrame | None = None, top: int = 15) -> dict[str, pd.Series]:
    df = load_aria() if df is None else df
    fires = df[df["is_fire"]]
    return {
        "fires_per_year": fires["date"].dt.year.value_counts().sort_index(),
        "top_sectors": fires["sector"].replace("", pd.NA).dropna().value_counts().head(top),
        # one top-level category per fire event
        "top_primary_causes": first_category(fires["primary_causes"]).value_counts().head(top),
        "top_root_causes": first_category(fires["root_causes"]).value_counts().head(top),
        # tag counts (an event can contribute several tags)
        "primary_cause_tags": split_tags(fires["primary_causes"]).value_counts().head(top),
        "top_equipment": split_tags(fires["equipment"]).value_counts().head(top),
    }
