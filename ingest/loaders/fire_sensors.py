"""Loaders for the three real fire-experiment sensor datasets.

All return pandas DataFrames with harmonised snake_case columns and units in the names.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ingest.loaders.common import RAW, require

# --------------------------------------------------------------------------- industrial hall

_HALL_COLUMNS = {
    "Sensor_ID": "sensor_id", "CO2_Room": "co2_ppm", "CO_Room": "co_ppm", "H2_Room": "h2_raw",
    "VOC_Room_RAW": "voc_raw", "PM05_Room": "pm05", "PM10_Room": "pm10", "PM25_Room": "pm25",
    "PM40_Room": "pm40", "PM100_Room": "pm100", "PM_Total_Room": "pm_total",
    "PM_Room_Typical_Size": "pm_typical_size_um", "Temperature_Room": "temperature_c",
    "Humidity_Room": "humidity_pct", "scenario_label": "scenario", "progress_label": "stage",
    "experiment_number": "experiment", "fire": "is_fire", "nuisance": "is_nuisance",
    "anomaly_label": "is_anomaly", "Valid_Experiment": "valid",
}
HALL_FEATURES = ["co2_ppm", "co_ppm", "h2_raw", "voc_raw", "pm05", "pm10", "pm25", "pm40", "pm100",
                 "pm_total", "pm_typical_size_um", "temperature_c", "humidity_pct"]
FIRE_SCENARIOS = ["Wood", "Candles", "Cable", "Lunts"]
NUISANCE_SCENARIOS = ["Smoke", "Deodorant", "Ethanol", "CO", "Exhaust", "Green_Waste", "Welding", "Abrasive_Cutting"]


def load_industrial_hall() -> pd.DataFrame:
    """10 x 22 x 8 m industrial hall, 9 sensor nodes, fires + industrial nuisances (welding, cutting...)."""
    path = require("industrial_hall_fire", RAW / "industrial_hall_fire" / "industrial_hall.csv")
    df = pd.read_csv(path, usecols=["Date", *_HALL_COLUMNS]).rename(columns=_HALL_COLUMNS)
    df["timestamp"] = pd.to_datetime(df.pop("Date"), utc=True, format="ISO8601")
    for c in ("is_fire", "is_nuisance", "is_anomaly", "valid"):
        df[c] = df[c].fillna(0).astype(int).astype(bool)
    return df.sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)


# --------------------------------------------------------------------------- small test chamber

def load_test_chamber() -> pd.DataFrame:
    """2 x 0.8 x 0.6 m chamber, 4 nodes, fires escalating through intensity stages 1-6."""
    path = require("test_chamber_fire", RAW / "test_chamber_fire" / "test_chamber.csv")
    df = pd.read_csv(path).drop(columns=["Unnamed: 0"], errors="ignore")
    df = df.rename(columns={"Sensor_ID": "sensor_id", "scenario_label": "scenario", "intensity_label": "intensity",
                            "number_label": "repetition", "Interval_label": "interval",
                            **{k: v for k, v in _HALL_COLUMNS.items() if k not in ("Sensor_ID", "scenario_label")}})
    df = df.rename(columns={"VOC_Room": "voc_index", "UV_Room": "uv", "Date": "time_index"})
    df.columns = [re.sub(r"_room", "", c.lower()) if c.endswith("_Trend") else c for c in df.columns]
    return df


# --------------------------------------------------------------------------- indoor laboratory (Zayed University)

_LAB_NAMES = {"time": "time", "reading id": "reading", "humidity": "humidity_pct", "temperature": "temperature_c",
              "mq139": "mq139_raw", "tvoc": "tvoc_ppb", "eco2": "eco2_ppm", "detector": "detector_on", "status": "stage"}


def _clean_col(c: str) -> str:
    key = re.sub(r"[#%]", "", c).strip().lower()
    return _LAB_NAMES.get(key, key)


def _clock_to_seconds(series: pd.Series) -> np.ndarray:
    parts = series.astype(str).str.strip().str.split(":", expand=True).astype(int)
    secs = (parts[0] * 3600 + parts[1] * 60 + parts[2]).to_numpy()
    secs = secs - secs[0]
    secs[secs < 0] += 24 * 3600  # recording crossed midnight
    return secs


def load_indoor_lab() -> pd.DataFrame:
    """8 controlled fires (4 electrical, 2 carton, 2 clothing), one reading every 2 s, plus the
    conventional smoke detector state (`detector_on`) used as the baseline to beat."""
    frames = []
    for source in ("electrical", "carton", "clothing"):
        for i in range(1, 5):
            path = RAW / "indoor_lab_fire" / f"{source}_{i}.csv"
            if not path.exists():
                if source == "electrical" or i <= 2:
                    require("indoor_lab_fire", path)
                continue
            d = pd.read_csv(path)
            d.columns = [_clean_col(c) for c in d.columns]
            d["t_s"] = _clock_to_seconds(d.pop("time"))
            d["detector_on"] = d["detector_on"].astype(str).str.strip().str.upper().eq("ON")
            d["source"] = source
            d["experiment"] = f"{source}_{i}"
            frames.append(d)
    return pd.concat(frames, ignore_index=True)
