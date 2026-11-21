"""Runtime API used by the backend. Loads registered models (hash-checked) and scores live data."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from ai import compressor as C
from ai import lead_time as L
from ai import registry
from ai import zone_fire as Z


@lru_cache(maxsize=None)
def _load(name: str):
    return registry.load(name)


class ZoneFireDetector:
    """Feed the recent history (>= 20 min) of every sensor node of a zone; get P(fire) per node
    and the zone decision with the registered coincidence rule."""

    def __init__(self):
        bundle, self.card = _load("zone_fire")
        self.model, self.features = bundle["model"], bundle["features"]
        self.p_fire = self.card["config"]["p_fire"]
        self.min_nodes = self.card["config"]["min_nodes"]

    def node_probabilities(self, history: pd.DataFrame) -> pd.DataFrame:
        out = []
        for sid, node in history.groupby("sensor_id"):
            f = Z.node_features(node.sort_values("timestamp"))
            proba = self.model.predict_proba(f[self.features])
            classes = list(self.model.classes_)
            out.append(pd.DataFrame({"timestamp": f["timestamp"], "sensor_id": sid,
                                     "p_fire": proba[:, classes.index("fire")],
                                     "p_nuisance": proba[:, classes.index("nuisance")]}))
        return pd.concat(out, ignore_index=True)

    def assess(self, history: pd.DataFrame) -> dict:
        probs = self.node_probabilities(history)
        alarms = Z.zone_alarm_times(probs, self.p_fire, self.min_nodes)
        latest = probs.sort_values("timestamp").groupby("sensor_id").tail(1)
        return {"fire_alarm": len(alarms) > 0,
                "first_alarm": alarms.iloc[0] if len(alarms) else None,
                "max_p_fire_now": float(latest["p_fire"].max()),
                "max_p_nuisance_now": float(latest["p_nuisance"].max()),
                "model_version": self.card["version"]}


def early_warning(readings: pd.DataFrame) -> dict:
    """readings: columns t_s + L.CHANNELS (+ stage/detector_on if known), first 120 s = calibration."""
    df = readings.copy()
    for c in ("stage", "detector_on"):
        if c not in df:
            df[c] = 0 if c == "stage" else False
    s = L.score(df.reset_index(drop=True))
    warn = s.loc[s["warning"], "t_s"]
    return {"warning": bool(len(warn)), "first_warning_s": float(warn.iloc[0]) if len(warn) else None,
            "channels_high_now": int(s["n_high"].iloc[-1])}


class CompressorMonitor:
    def __init__(self):
        bundle, self.card = _load("compressor")
        self.scorer, self.features = bundle["scorer"], bundle["features"]
        self.threshold = self.card["metrics"]["Autoencoder"]["threshold"]

    def score(self, windows: pd.DataFrame) -> pd.DataFrame:
        s = self.scorer.score(windows[self.features].to_numpy())
        return pd.DataFrame({"score": s, "above_threshold": s > self.threshold}, index=windows.index)
