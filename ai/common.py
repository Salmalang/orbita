"""Shared helpers for the AEROGUARD models."""
from __future__ import annotations

import numpy as np
import pandas as pd


def persistent(flags: np.ndarray, k: int) -> np.ndarray:
    """True at i when flags[i-k+1..i] are all True (alarm confirmation, avoids one-sample blips)."""
    flags = np.asarray(flags, dtype=bool)
    if k <= 1:
        return flags
    run = np.zeros(len(flags), dtype=int)
    c = 0
    for i, f in enumerate(flags):
        c = c + 1 if f else 0
        run[i] = c
    return run >= k


def first_true(index, flags) -> object | None:
    idx = np.flatnonzero(np.asarray(flags, dtype=bool))
    return None if len(idx) == 0 else index[idx[0]]


def robust_scale(x: pd.DataFrame, ref: pd.DataFrame, floor: pd.Series | float = 1e-6) -> pd.DataFrame:
    """(x - median(ref)) / (1.4826 * MAD(ref)), with a floor on the spread (sensor resolution)."""
    med = ref.median()
    mad = (ref - med).abs().median() * 1.4826
    mad = np.maximum(mad, floor)
    return (x - med) / mad
