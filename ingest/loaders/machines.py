"""Loaders for real machine condition-monitoring data: SKAB (pump + motor) and MetroPT-3 (compressor)."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ingest.loaders.common import CACHE, RAW, require

# --------------------------------------------------------------------------- SKAB

SKAB_DIR = RAW / "skab" / "extracted" / "skab" / "SKAB-master" / "data"
_SKAB_COLUMNS = {
    "Accelerometer1RMS": "accel1_rms_g", "Accelerometer2RMS": "accel2_rms_g", "Current": "current_a",
    "Pressure": "pressure_bar", "Temperature": "temperature_c", "Thermocouple": "fluid_temperature_c",
    "Voltage": "voltage_v", "Volume Flow RateRMS": "flow_rate_l_min", "anomaly": "anomaly", "changepoint": "changepoint",
}
SKAB_FEATURES = ["accel1_rms_g", "accel2_rms_g", "current_a", "pressure_bar", "temperature_c",
                 "fluid_temperature_c", "voltage_v", "flow_rate_l_min"]


@dataclass
class SkabExperiment:
    group: str          # anomaly-free | valve1 | valve2 | other
    name: str
    data: pd.DataFrame

    @property
    def id(self) -> str:
        return f"{self.group}/{self.name}"


def _read_skab(path) -> pd.DataFrame:
    d = pd.read_csv(path, sep=";").rename(columns=_SKAB_COLUMNS)
    d["timestamp"] = pd.to_datetime(d.pop("datetime"))
    for c in ("anomaly", "changepoint"):
        d[c] = d[c].fillna(0).astype(int) if c in d else 0
    return d


def load_skab() -> list[SkabExperiment]:
    """All 35 SKAB experiments. The `anomaly-free` run is the normal-behaviour reference."""
    require("skab", SKAB_DIR)
    out = []
    for group in ("anomaly-free", "valve1", "valve2", "other"):
        files = sorted((SKAB_DIR / group).glob("*.csv"), key=lambda p: (len(p.stem), p.stem))
        out += [SkabExperiment(group, f.stem, _read_skab(f)) for f in files]
    return out


# --------------------------------------------------------------------------- MetroPT-3

METROPT_CSV = RAW / "metropt3" / "extracted" / "metropt3" / "MetroPT3(AirCompressor).csv"
_METRO_COLUMNS = {
    "TP2": "tp2_bar", "TP3": "tp3_bar", "H1": "h1_bar", "DV_pressure": "dv_pressure_bar",
    "Reservoirs": "reservoirs_bar", "Oil_temperature": "oil_temperature_c", "Motor_current": "motor_current_a",
    "COMP": "comp", "DV_eletric": "dv_electric", "Towers": "towers", "MPG": "mpg", "LPS": "lps",
    "Pressure_switch": "pressure_switch", "Oil_level": "oil_level", "Caudal_impulses": "caudal_impulses",
}
METRO_ANALOG = ["tp2_bar", "tp3_bar", "h1_bar", "dv_pressure_bar", "reservoirs_bar", "oil_temperature_c", "motor_current_a"]

# Failure reports exactly as published in the dataset's "Data Description_Metro.pdf" (UCI, MetroPT-3).
# The PDF numbers two rows "#1"; we keep the published order and times. Times are local (Porto).
METROPT3_FAILURES = pd.DataFrame([
    {"nr": 1, "start": "2020-04-18 00:00", "end": "2020-04-18 23:59", "failure": "Air leak", "severity": "High stress", "report": ""},
    {"nr": 2, "start": "2020-05-29 23:30", "end": "2020-05-30 06:00", "failure": "Air leak", "severity": "High stress", "report": "Maintenance on 30Apr at 12:00"},
    {"nr": 3, "start": "2020-06-05 10:00", "end": "2020-06-07 14:30", "failure": "Air leak", "severity": "High stress", "report": "Maintenance on 8Jun at 16:00"},
    {"nr": 4, "start": "2020-07-15 14:30", "end": "2020-07-15 19:00", "failure": "Air leak", "severity": "High stress", "report": "Maintenance on 16Jul at 00:00"},
]).assign(start=lambda d: pd.to_datetime(d["start"]), end=lambda d: pd.to_datetime(d["end"]))


def load_metropt3(resample: str | None = "1min", use_cache: bool = True) -> pd.DataFrame:
    """Air compressor of a Porto metro train, Feb-Aug 2020 (1.5 M rows at ~10 s).

    `resample` averages analog signals (and takes the max of digital ones) to keep training fast.
    Adds `failure` (bool) for rows inside a reported failure window.
    """
    cache = CACHE / f"metropt3_{resample or 'raw'}.pkl"
    if use_cache and cache.exists():
        return pd.read_pickle(cache)
    require("metropt3", METROPT_CSV)
    df = pd.read_csv(METROPT_CSV, usecols=["timestamp", *_METRO_COLUMNS]).rename(columns=_METRO_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    if resample:
        digital = [c for c in df.columns if c not in METRO_ANALOG]
        df = pd.concat([df[METRO_ANALOG].resample(resample).mean(), df[digital].resample(resample).max()], axis=1)
        df = df.dropna(how="all")
    df["failure"] = False
    for f in METROPT3_FAILURES.itertuples():
        df.loc[f.start:f.end, "failure"] = True
    df = df.reset_index()
    CACHE.mkdir(parents=True, exist_ok=True)
    df.to_pickle(cache)
    return df
