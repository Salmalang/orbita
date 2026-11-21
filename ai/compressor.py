"""Compressor early warning on real failures (MetroPT-3, metro air compressor, Feb-Aug 2020).

Unsupervised: models learn normal operation from February-March 2020 (no reported failure) and
score 30-minute windows afterwards. Features combine operating behaviour (duty cycle, cycling,
pressures) with the physics residual (measured oil temperature - energy-balance prediction).
Evaluation against the 4 failures reported by the operator's maintenance records.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ai.common import persistent
from physics.thermal import FirstOrderThermalModel, ambient_proxy

WINDOW = "30min"
TRAIN_END = pd.Timestamp("2020-04-01")
LOOKBACK = pd.Timedelta("48h")       # an alarm up to 48 h before a failure counts as early warning
AFTER = pd.Timedelta("24h")          # windows right after a failure are not counted as false alarms
CONFIRM = 2                          # 2 consecutive windows = 1 h
QUANTILE = 0.995                     # threshold = 99.5th percentile of training scores
ON_A = 2.0                           # motor current above 2 A = compressor running


def window_features(m: pd.DataFrame) -> pd.DataFrame:
    """m: 1-minute frame indexed by timestamp (from load_metropt3)."""
    m = m.asfreq("1min")
    T, I = m["oil_temperature_c"].to_numpy(), m["motor_current_a"].to_numpy()
    Ta = ambient_proxy(m["oil_temperature_c"]).to_numpy()
    train = m.index < TRAIN_END
    phys = FirstOrderThermalModel().fit(T[train], I[train], Ta[train])
    resid = T - phys.predict_with_resets(T, I, Ta, horizon=60)
    on = (m["motor_current_a"] > ON_A).astype(float).where(m["motor_current_a"].notna())
    starts = (on.diff() == 1).astype(float)
    run_id = (on != on.shift()).cumsum()
    run_len = on.groupby(run_id).cumsum()            # minutes since the compressor switched on
    f = pd.DataFrame({
        "duty": on, "starts": starts, "longest_run_min": run_len.where(on == 1),
        "oil_temp_c": m["oil_temperature_c"], "phys_resid_c": pd.Series(resid, index=m.index),
        "current_on_a": m["motor_current_a"].where(on == 1),
        "tp2_bar": m["tp2_bar"], "reservoirs_bar": m["reservoirs_bar"], "h1_bar": m["h1_bar"],
        "dv_pressure_bar": m["dv_pressure_bar"],
    })
    agg = f.resample(WINDOW).agg({"duty": "mean", "starts": "sum", "longest_run_min": "max", "oil_temp_c": "mean",
                                  "phys_resid_c": "mean", "current_on_a": "mean", "tp2_bar": "mean",
                                  "reservoirs_bar": "min", "h1_bar": "mean", "dv_pressure_bar": "mean"})
    coverage = f["oil_temp_c"].notna().resample(WINDOW).mean()
    agg = agg[coverage >= 0.8]                       # skip windows with logging gaps
    agg["longest_run_min"] = agg["longest_run_min"].fillna(0)
    agg["current_on_a"] = agg["current_on_a"].fillna(0)
    return agg.dropna()


class AutoencoderScorer:
    """Small MLP autoencoder (scikit-learn): score = reconstruction error of standardised features."""

    def __init__(self, seed: int = 0):
        self.scaler = StandardScaler()
        self.net = MLPRegressor(hidden_layer_sizes=(16, 4, 16), activation="tanh", max_iter=2000,
                                alpha=1e-3, random_state=seed)

    def fit(self, X):
        Z = self.scaler.fit_transform(X)
        self.net.fit(Z, Z)
        return self

    def score(self, X) -> np.ndarray:
        Z = self.scaler.transform(X)
        return ((self.net.predict(Z) - Z) ** 2).mean(axis=1)


class IsolationForestScorer:
    def __init__(self, seed: int = 0):
        self.model = make_pipeline(StandardScaler(), IsolationForest(n_estimators=300, random_state=seed))

    def fit(self, X):
        self.model.fit(X)
        return self

    def score(self, X) -> np.ndarray:
        return -self.model.score_samples(X)


def evaluate(feats: pd.DataFrame, failures: pd.DataFrame, scorer) -> tuple[dict, pd.DataFrame]:
    train = feats[feats.index < TRAIN_END]
    test = feats[feats.index >= TRAIN_END]
    scorer.fit(train.to_numpy())
    thr = np.quantile(scorer.score(train.to_numpy()), QUANTILE)
    s = pd.Series(scorer.score(test.to_numpy()), index=test.index)
    # consecutive windows must also be consecutive in time (gaps break confirmation)
    contiguous = s.index.to_series().diff().le(pd.Timedelta(WINDOW)).to_numpy()
    raw = (s > thr).to_numpy()
    alarm = np.zeros(len(s), dtype=bool)
    run = 0
    for i in range(len(s)):
        run = run + 1 if raw[i] and (run == 0 or contiguous[i]) else (1 if raw[i] else 0)
        alarm[i] = run >= CONFIRM
    alarm = pd.Series(alarm, index=s.index)

    rows, excluded = [], pd.Series(False, index=s.index)
    for f in failures.itertuples():
        excluded |= (s.index >= f.start - LOOKBACK) & (s.index <= f.end + AFTER)
        win = alarm[(alarm.index >= f.start - LOOKBACK) & (alarm.index <= f.end)]
        first = win.index[win.to_numpy()][0] if win.any() else None
        rows.append({"failure": int(f.nr), "start": f.start, "detected": first is not None,
                     "first_alarm": first,
                     "lead_time_h": round((f.start - first).total_seconds() / 3600, 1) if first is not None else None})
    fa = alarm[~excluded]
    onsets = int((fa & ~fa.shift(1, fill_value=False)).sum())
    weeks = (~excluded).sum() * pd.Timedelta(WINDOW) / pd.Timedelta("7D")
    res = pd.DataFrame(rows)
    summary = {"failures": len(res), "detected": int(res["detected"].sum()),
               "detected_before_start": int((res["lead_time_h"].fillna(-1) > 0).sum()),
               "median_lead_time_h": float(res["lead_time_h"].median()) if res["detected"].any() else None,
               "false_alarm_episodes": onsets, "normal_weeks_evaluated": round(weeks, 1),
               "false_alarms_per_week": round(onsets / weeks, 2), "threshold": float(thr)}
    return summary, res
