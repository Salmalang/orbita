"""Physics-based thermal model fitted on real measurements (no generated data).

Lumped first-order energy balance of a machine (Joule heating + Newton cooling):

    C dT/dt = R_e I^2 - (T - T_amb) / R_th
    =>  T[k+1] - T[k] = a I[k]^2 - b (T[k] - T_amb[k])      (discretised, step = dt)

with a = R_e dt / C and b = dt / (R_th C) = dt / tau. Steady-state rise at current I is
dT_ss = (a / b) I^2 = R_e R_th I^2.

The model is identified by least squares on a period of normal operation, then used to
predict temperature from the *measured* current. The gap between measured and
physics-predicted temperature is a physics-informed anomaly signal for the AI.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def ambient_proxy(temp: pd.Series, window: str = "24h", q: float = 0.05) -> pd.Series:
    """Ambient temperature is not measured; use a rolling low quantile of the machine
    temperature (the machine cools towards ambient when idle)."""
    return temp.rolling(window, min_periods=60).quantile(q)


@dataclass
class FirstOrderThermalModel:
    a: float = np.nan  # K per step per A^2
    b: float = np.nan  # 1 / step
    dt_s: float = 60.0

    @property
    def tau_s(self) -> float:
        return self.dt_s / self.b

    def steady_rise(self, current_a: float) -> float:
        return self.a / self.b * current_a ** 2

    def fit(self, temp: np.ndarray, current: np.ndarray, ambient: np.ndarray) -> "FirstOrderThermalModel":
        dT = np.r_[temp[1:] - temp[:-1], np.nan]
        X = np.c_[current ** 2, -(temp - ambient)]
        ok = np.isfinite(X).all(axis=1) & np.isfinite(dT) & (np.abs(dT) < 5)
        if ok.sum() < 100:
            raise ValueError("not enough valid samples to identify the thermal model")
        (self.a, self.b), *_ = np.linalg.lstsq(X[ok], dT[ok], rcond=None)
        if not (self.a > 0 and 0 < self.b < 1):
            raise ValueError(f"identified parameters are not physical (a={self.a}, b={self.b})")
        return self

    def simulate(self, t0: float, current: np.ndarray, ambient: np.ndarray) -> np.ndarray:
        out = np.empty(len(current))
        T = t0
        for k in range(len(current)):
            out[k] = T
            if np.isfinite(current[k]) and np.isfinite(ambient[k]):
                T = T + self.a * current[k] ** 2 - self.b * (T - ambient[k])
        return out

    def predict_with_resets(self, temp: np.ndarray, current: np.ndarray, ambient: np.ndarray,
                            horizon: int = 60) -> np.ndarray:
        """Free-run prediction, re-initialised from the measured temperature every `horizon` steps."""
        pred = np.full(len(temp), np.nan)
        for start in range(0, len(temp), horizon):
            stop = min(start + horizon, len(temp))
            if np.isfinite(temp[start]):
                pred[start:stop] = self.simulate(temp[start], current[start:stop], ambient[start:stop])
        return pred


def r2(y: np.ndarray, yhat: np.ndarray) -> float:
    ok = np.isfinite(y) & np.isfinite(yhat)
    return float(1 - np.var(y[ok] - yhat[ok]) / np.var(y[ok]))
