"""Data quality audit on the actual records. Writes docs/audit/data_checks.json.

Run: .venv/Scripts/python scripts/audit_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ingest.download import MANIFEST, sha256_of  # noqa: E402
from ingest.loaders.accidents import load_aria  # noqa: E402
from ingest.loaders.fire_sensors import load_indoor_lab, load_industrial_hall, load_test_chamber  # noqa: E402
from ingest.loaders.machines import METROPT3_FAILURES, load_metropt3, load_skab  # noqa: E402
from ingest.loaders.thermal import list_motor_thermal_images, read_image  # noqa: E402
from ingest.registry import DATASETS  # noqa: E402


def interval_stats(ts: pd.Series) -> dict:
    d = ts.sort_values().diff().dt.total_seconds().dropna()
    return {"median_s": float(d.median()), "p95_s": float(d.quantile(0.95)), "max_gap_s": float(d.max()),
            "gaps_over_10x_median": int((d > 10 * d.median()).sum())}


def missing(df: pd.DataFrame, cols) -> dict:
    return {c: int(df[c].isna().sum()) for c in cols if df[c].isna().any()}


def main() -> dict:
    out = {}
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out["integrity"] = {}
    for ds_id, entry in manifest.items():
        published = {f.name: f.sha256 for f in DATASETS[ds_id].files}
        rows = []
        for f in entry["files"]:
            local = sha256_of(ROOT / "data" / "raw" / ds_id / f["file"])
            pub = published.get(f["file"])
            rows.append({"file": f["file"], "matches_publisher_sha256": (local == pub) if pub else None,
                         "publisher_hash_available": bool(pub)})
        out["integrity"][ds_id] = rows

    h = load_industrial_hall()
    num = [c for c in h.columns if h[c].dtype.kind == "f"]
    per_node = {sid: interval_stats(g["timestamp"]) for sid, g in h.groupby("sensor_id")}
    out["industrial_hall_fire"] = {
        "rows": len(h), "nodes": h["sensor_id"].nunique(),
        "start": str(h["timestamp"].min()), "end": str(h["timestamp"].max()),
        "duplicate_rows": int(h.duplicated().sum()),
        "duplicate_node_timestamp": int(h.duplicated(["sensor_id", "timestamp"]).sum()),
        "sampling_per_node_median_s": sorted({v["median_s"] for v in per_node.values()}),
        "max_gap_s_any_node": max(v["max_gap_s"] for v in per_node.values()),
        "missing_values": missing(h, num),
        "negative_values": {c: int((h[c] < 0).sum()) for c in num if (h[c] < 0).any()},
        "valid_flag_false_rows": int((~h["valid"]).sum()),
        "event_rows_with_scenario_but_no_experiment": int(((h["scenario"] != "Background") & h["experiment"].isna()).sum()),
        "label_consistency": {
            "fire_rows_in_nuisance_scenarios": int((h["is_fire"] & h["scenario"].isin(["Welding", "Smoke", "Ethanol", "CO", "Deodorant", "Exhaust", "Green_Waste", "Abrasive_Cutting"])).sum()),
            "anomaly_rows_in_background": int((h["is_anomaly"] & (h["scenario"] == "Background")).sum()),
            "single_row_events": h[h["scenario"] != "Background"].groupby(["scenario", "experiment"]).size().loc[lambda s: s < 10].to_dict(),
        },
        "co_ppm_range": [float(h["co_ppm"].min()), float(h["co_ppm"].max())],
        "temperature_c_range": [float(h["temperature_c"].min()), float(h["temperature_c"].max())],
    }
    out["industrial_hall_fire"]["label_consistency"]["single_row_events"] = {
        f"{k[0]}#{k[1]}": int(v) for k, v in out["industrial_hall_fire"]["label_consistency"]["single_row_events"].items()}

    lab = load_indoor_lab()
    out["indoor_lab_fire"] = {
        "rows": len(lab), "experiments": int(lab["experiment"].nunique()),
        "sampling_median_s": {e: float(g["t_s"].diff().median()) for e, g in lab.groupby("experiment")},
        "max_gap_s": {e: float(g["t_s"].diff().max()) for e, g in lab.groupby("experiment")},
        "duplicate_rows": int(lab.duplicated().sum()),
        "missing_values": missing(lab, ["humidity_pct", "temperature_c", "mq139_raw", "tvoc_ppb", "eco2_ppm"]),
        "note": "timestamps are relative per experiment (no absolute date)",
    }

    ch = load_test_chamber()
    out["test_chamber_fire"] = {"rows": len(ch), "intensity_range": [int(ch["intensity"].min()), int(ch["intensity"].max())],
                                "scenarios": sorted(ch["scenario"].unique().tolist()),
                                "negative_co_ppm_rows": int((ch["co_ppm"] < 0).sum())}

    sk = load_skab()
    out["skab"] = {
        "experiments": len(sk),
        "sampling_median_s": sorted({float(e.data["timestamp"].diff().dt.total_seconds().median()) for e in sk}),
        "anomaly_share_in_labelled": round(float(np.mean([e.data["anomaly"].mean() for e in sk if e.group != "anomaly-free"])), 3),
        "anomaly_in_first_400_rows": {e.id: int(e.data["anomaly"].iloc[:400].sum()) for e in sk if e.data["anomaly"].iloc[:400].sum() > 0},
        "duplicate_timestamps": {e.id: int(e.data["timestamp"].duplicated().sum()) for e in sk if e.data["timestamp"].duplicated().any()},
        "missing_values_total": int(sum(e.data.isna().sum().sum() for e in sk)),
    }

    m = load_metropt3(resample=None, use_cache=False)
    ts = m["timestamp"]
    d = ts.diff().dt.total_seconds()
    out["metropt3"] = {
        "rows": len(m), "start": str(ts.min()), "end": str(ts.max()),
        "timestamps_monotonic": bool(ts.is_monotonic_increasing),
        "duplicate_timestamps": int(ts.duplicated().sum()),
        "sampling_median_s": float(d.median()),
        "gaps_over_1h": int((d > 3600).sum()), "longest_gap_h": round(float(d.max()) / 3600, 1),
        "note_on_rate": "the UCI page says 1 Hz; the published CSV is sampled about every 10 s",
        "failures_reported": len(METROPT3_FAILURES),
        "data_after_last_failure_days": round((ts.max() - METROPT3_FAILURES["end"].max()).total_seconds() / 86400, 1),
        "missing_values": missing(m, [c for c in m.columns if c != "timestamp"]),
    }

    imgs = list_motor_thermal_images()
    shapes = {str(read_image(p).shape) for p in imgs["path"].iloc[::10]}
    out["motor_thermal"] = {"images": len(imgs), "classes": imgs["folder"].nunique(), "shapes_sampled": sorted(shapes),
                            "note": "8-bit pseudo-colour BMP renderings; no radiometric temperature values"}

    a = load_aria()
    out["aria"] = {"rows": len(a), "fires": int(a["is_fire"].sum()),
                   "duplicate_aria_ids": int(a["aria_id"].duplicated().sum()),
                   "date_range": [str(a["date"].min().date()), str(a["date"].max().date())],
                   "fires_with_primary_cause": int((a["is_fire"] & (a["primary_causes"].str.len() > 0)).sum()),
                   "countries_top": a["country"].value_counts().head(3).to_dict()}
    return out


if __name__ == "__main__":
    res = main()
    path = ROOT / "docs" / "audit" / "data_checks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str))
