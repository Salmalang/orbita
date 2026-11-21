"""Motor / pump anomaly detection on SKAB (real test bench, 34 labelled experiments).

SKAB convention: the first 400 samples of each experiment are anomaly-free and used for
training; the rest is used for testing. Compared methods:
  * fixed 3-sigma limits per channel (classic control-chart alarm, the conventional baseline)
  * PCA residual (Q / SPE statistic), a standard multivariate process-monitoring method
  * MLP autoencoder (reconstruction error)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.metrics import f1_score
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from ai.common import persistent
from ingest.loaders.machines import SKAB_FEATURES

N_TRAIN = 400
QUANTILE = 0.99
CONFIRM = 3


class ThreeSigma:
    name = "Fixed k-sigma limits"
    k = 3.0

    def fit(self, X):
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        return self

    def score(self, X):
        return (np.abs(X - self.mu) / self.sd).max(1)

    def threshold(self, X):
        return self.k


class PCAResidual:
    name = "PCA residual (Q statistic)"
    margin = 1.0

    def fit(self, X):
        self.sc = StandardScaler().fit(X)
        self.pca = PCA(n_components=0.9, svd_solver="full").fit(self.sc.transform(X))
        return self

    def score(self, X):
        Z = self.sc.transform(X)
        return ((Z - self.pca.inverse_transform(self.pca.transform(Z))) ** 2).sum(1)

    def threshold(self, X):
        return np.quantile(self.score(X), QUANTILE) * self.margin


class Autoencoder:
    name = "MLP autoencoder"
    margin = 1.0

    def __init__(self, seed: int = 0):
        self.seed = seed

    def fit(self, X):
        self.sc = StandardScaler().fit(X)
        Z = self.sc.transform(X)
        self.net = MLPRegressor(hidden_layer_sizes=(6, 3, 6), activation="tanh", max_iter=3000,
                                alpha=1e-3, random_state=self.seed).fit(Z, Z)
        return self

    def score(self, X):
        Z = self.sc.transform(X)
        return ((self.net.predict(Z) - Z) ** 2).mean(1)

    def threshold(self, X):
        return np.quantile(self.score(X), QUANTILE) * self.margin


def run(experiments, make) -> dict:
    y_true, y_pred, delays = [], [], []
    for e in experiments:
        X = e.data[SKAB_FEATURES].to_numpy(float)
        y = e.data["anomaly"].to_numpy(int)
        tr, te, yte = X[:N_TRAIN], X[N_TRAIN:], y[N_TRAIN:]
        m = make().fit(tr)
        pred = persistent(m.score(te) > m.threshold(tr), CONFIRM).astype(int)
        y_true.append(yte)
        y_pred.append(pred)
        onset = np.flatnonzero(yte)
        if len(onset):
            hits = np.flatnonzero(pred[onset[0]:])
            delays.append(hits[0] if len(hits) else np.nan)  # samples (~1 s) from anomaly start
    yt, yp = np.concatenate(y_true), np.concatenate(y_pred)
    normal, anom = yt == 0, yt == 1
    return {"f1": round(f1_score(yt, yp), 3),
            "false_alarm_rate": round(yp[normal].mean(), 3),
            "missed_alarm_rate": round(1 - yp[anom].mean(), 3),
            "anomalies_detected": f"{int(np.sum(np.isfinite(delays)))}/{len(delays)}",
            "median_detection_delay_s": float(np.nanmedian(delays)) if np.isfinite(delays).any() else None}


GRID = {"ThreeSigma": ("k", [2.0, 2.5, 3.0, 4.0, 5.0, 6.0]),
        "PCAResidual": ("margin", [0.8, 1.0, 1.5, 2.0, 3.0, 5.0]),
        "Autoencoder": ("margin", [0.8, 1.0, 1.5, 2.0, 3.0, 5.0])}


def _with(cls, attr, value):
    return type(cls.__name__, (cls,), {attr: value})


def compare(experiments) -> pd.DataFrame:
    """Tune each method's threshold on the valve1 experiments (F1), then test on valve2 + other."""
    tune = [e for e in experiments if e.group == "valve1"]
    test = [e for e in experiments if e.group in ("valve2", "other")]
    rows = []
    for cls in (ThreeSigma, PCAResidual, Autoencoder):
        attr, values = GRID[cls.__name__]
        best = max(values, key=lambda v: run(tune, _with(cls, attr, v))["f1"])
        r = run(test, _with(cls, attr, best))
        rows.append({"method": cls.name, "tuned": f"{attr}={best}", **r})
    return pd.DataFrame(rows)
