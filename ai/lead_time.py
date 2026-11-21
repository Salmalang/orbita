"""Early warning vs the conventional smoke detector (Indoor Laboratory Fire Dataset, real).

Unsupervised and fixed in advance: each recording's first CALIBRATION_S seconds define the room's
normal state; afterwards a multi-gas robust z-score raises an AEROGUARD warning when at least
MIN_CHANNELS channels exceed Z_THRESHOLD for CONFIRM consecutive readings (2 s apart).
Nothing is tuned on the outcome; a sensitivity table shows other thresholds.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ai.common import persistent, robust_scale

CHANNELS = ["tvoc_ppb", "eco2_ppm", "mq139_raw", "temperature_c", "humidity_pct"]
# Smallest meaningful change per channel (sensor resolution / noise floor) so a flat baseline
# does not make every tiny change look huge.
FLOORS = pd.Series({"tvoc_ppb": 10.0, "eco2_ppm": 20.0, "mq139_raw": 3.0, "temperature_c": 0.3, "humidity_pct": 1.0})
CALIBRATION_S = 120
Z_THRESHOLD = 8.0
MIN_CHANNELS = 2
CONFIRM = 5                 # 5 readings = about 10 s


def score(exp: pd.DataFrame, z_threshold: float = Z_THRESHOLD, min_channels: int = MIN_CHANNELS) -> pd.DataFrame:
    ref = exp.loc[exp["t_s"] <= CALIBRATION_S, CHANNELS]
    z = robust_scale(exp[CHANNELS], ref, FLOORS)
    # only increases matter for gases/temperature; humidity can move either way
    up = z[["tvoc_ppb", "eco2_ppm", "mq139_raw", "temperature_c"]].clip(lower=0)
    zz = pd.concat([up, z[["humidity_pct"]].abs()], axis=1)
    n_high = (zz > z_threshold).sum(axis=1)
    warn = persistent((n_high >= min_channels).to_numpy() & (exp["t_s"] > CALIBRATION_S).to_numpy(), CONFIRM)
    return exp[["t_s", "stage", "detector_on"]].assign(n_high=n_high.to_numpy(), warning=warn,
                                                       top_channel=zz.idxmax(axis=1).to_numpy())


def evaluate(lab: pd.DataFrame, z_threshold: float = Z_THRESHOLD, min_channels: int = MIN_CHANNELS) -> pd.DataFrame:
    rows = []
    for exp_id, exp in lab.groupby("experiment", sort=False):
        s = score(exp.reset_index(drop=True), z_threshold, min_channels)
        det = s.loc[s["detector_on"], "t_s"]
        warn = s.loc[s["warning"], "t_s"]
        det_t = float(det.iloc[0]) if len(det) else np.nan
        warn_t = float(warn.iloc[0]) if len(warn) else np.nan
        # a warning while the authors mark "no fire" (stage 0) after calibration is a false warning
        false_warn = bool(s.loc[(s["stage"] == 0) & (s["t_s"] > CALIBRATION_S), "warning"].any())
        rows.append({
            "experiment": exp_id, "source": exp["source"].iloc[0],
            "detector_s": det_t, "aeroguard_s": warn_t,
            "lead_time_s": det_t - warn_t if np.isfinite(det_t) and np.isfinite(warn_t) else np.nan,
            "warned_before_detector": bool(np.isfinite(warn_t) and (not np.isfinite(det_t) or warn_t < det_t)),
            "false_warning_in_stage0": false_warn,
            "first_channel": s.loc[s["warning"], "top_channel"].iloc[0] if len(warn) else None,
            "detector_before_calibration_end": bool(np.isfinite(det_t) and det_t <= CALIBRATION_S),
        })
    return pd.DataFrame(rows)


def sensitivity(lab: pd.DataFrame, thresholds=(4, 6, 8, 12, 16), min_channels=(1, 2)) -> pd.DataFrame:
    out = []
    for m in min_channels:
        for zt in thresholds:
            r = evaluate(lab, zt, m)
            ok = r[~r["detector_before_calibration_end"]]
            elec = ok[ok["source"] == "electrical"]
            out.append({"z_threshold": zt, "min_channels": m,
                        "warned_before_detector": f"{int(ok['warned_before_detector'].sum())}/{len(ok)}",
                        "median_lead_time_min": round(ok["lead_time_s"].median() / 60, 1),
                        "electrical_median_lead_min": round(elec["lead_time_s"].median() / 60, 1),
                        "false_warnings_stage0": int(ok["false_warning_in_stage0"].sum())})
    return pd.DataFrame(out)
