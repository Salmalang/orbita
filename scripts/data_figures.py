"""Build the data figures used in the docs, the model report and the pitch (real data only).

Run: .venv/Scripts/python scripts/data_figures.py   -> docs/figures/*.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "figures"

from ingest.loaders.accidents import fire_statistics, first_category, load_aria  # noqa: E402
from ingest.loaders.fire_sensors import load_indoor_lab, load_industrial_hall  # noqa: E402
from ingest.loaders.machines import METROPT3_FAILURES, load_metropt3  # noqa: E402
from ingest.loaders.thermal import list_motor_thermal_images, read_image  # noqa: E402
from physics.thermal import FirstOrderThermalModel, ambient_proxy  # noqa: E402

plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False, "font.size": 9})
SRC = dict(fontsize=7, color="#666", ha="right", va="bottom")


def _save(fig, name: str, source: str) -> None:
    fig.text(0.99, 0.005, f"Source: {source}", **SRC)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT / name)
    plt.close(fig)
    print("wrote", name)


def hall_cable_vs_welding() -> None:
    df = load_industrial_hall()
    node = df["sensor_id"].value_counts().index[0]
    fig, axes = plt.subplots(3, 2, figsize=(9, 6), sharex="col")
    for col, scen in enumerate(["Cable", "Welding"]):
        ev = df[(df["sensor_id"] == node) & (df["scenario"] == scen)]
        first = ev["experiment"].dropna().iloc[0]
        ev = ev[ev["experiment"] == first]
        t = (ev["timestamp"] - ev["timestamp"].iloc[0]).dt.total_seconds() / 60
        for row, (c, label) in enumerate([("co_ppm", "CO (ppm)"), ("voc_raw", "VOC (raw)"), ("pm_total", "Particles (total)")]):
            axes[row, col].plot(t, ev[c], color="#d9480f" if scen == "Cable" else "#1c7ed6", lw=1.2)
            axes[row, col].set_ylabel(label)
        axes[0, col].set_title(f"{'Cable fire (real fire)' if scen == 'Cable' else 'Welding (nuisance, no fire)'}")
        axes[-1, col].set_xlabel("minutes since scenario start")
    _save(fig, "hall_cable_vs_welding.png", "Indoor Fire Dataset, Industrial Hall, doi:10.17632/yghykzm4km.1 (CC BY 4.0)")


def lab_electrical_detector() -> None:
    df = load_indoor_lab()
    fig, axes = plt.subplots(2, 2, figsize=(9, 5))
    for ax, exp in zip(axes.flat, [f"electrical_{i}" for i in range(1, 5)]):
        d = df[df["experiment"] == exp]
        t = d["t_s"] / 60
        ax.plot(t, d["tvoc_ppb"], label="TVOC (ppb)", color="#5f3dc4")
        ax.plot(t, d["eco2_ppm"], label="eCO2 (ppm)", color="#2b8a3e")
        on = d.loc[d["detector_on"], "t_s"]
        if len(on):
            ax.axvline(on.iloc[0] / 60, color="#e03131", ls="--", label="conventional detector ON")
        ax.set_title(exp.replace("_", " ").capitalize() + " fire")
        ax.set_xlabel("minutes")
    axes[0, 0].legend(fontsize=7)
    _save(fig, "lab_electrical_detector.png", "Indoor Laboratory Fire Dataset, doi:10.17632/f3mjnbm9b3.1 (CC BY 4.0)")


def metropt_physics() -> None:
    m = load_metropt3().set_index("timestamp").asfreq("1min")
    T, I = m["oil_temperature_c"].to_numpy(), m["motor_current_a"].to_numpy()
    Ta = ambient_proxy(m["oil_temperature_c"]).to_numpy()
    train = m.index < "2020-04-01"
    model = FirstOrderThermalModel().fit(T[train], I[train], Ta[train])
    pred = model.predict_with_resets(T, I, Ta, horizon=60)
    f = METROPT3_FAILURES.iloc[3]
    win = (m.index >= f.start - pd.Timedelta("2D")) & (m.index <= f.end + pd.Timedelta("1D"))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5), sharex=True)
    a1.plot(m.index[win], T[win], color="#212529", lw=0.8, label="measured oil temperature")
    a1.plot(m.index[win], pred[win], color="#f08c00", lw=0.8, label="physics model (from measured current)")
    a1.set_ylabel("°C")
    a1.legend(fontsize=7)
    a1.set_title(f"Air compressor, real failure #{f.nr} ({f.failure}); tau = {model.tau_s / 60:.0f} min")
    a2.plot(m.index[win], I[win], color="#1971c2", lw=0.6)
    a2.set_ylabel("motor current (A)")
    for ax in (a1, a2):
        ax.axvspan(f.start, f.end, color="#ffa8a8", alpha=0.4, label="reported failure")
    _save(fig, "metropt_physics_failure.png", "MetroPT-3, UCI, doi:10.24432/C5VW3R (CC BY 4.0)")


def thermal_samples() -> None:
    imgs = list_motor_thermal_images()
    picks = ["Noload", "Fan", "Rotor-0", "A&C&B30"]
    fig, axes = plt.subplots(1, 4, figsize=(10, 2.6))
    for ax, folder in zip(axes, picks):
        row = imgs[imgs["folder"] == folder].iloc[len(imgs[imgs["folder"] == folder]) // 2]
        ax.imshow(read_image(row["path"]))
        ax.set_title(row["description"], fontsize=8)
        ax.axis("off")
    _save(fig, "motor_thermal_samples.png", "Najafi et al., Thermal image of equipment (Induction Motor), doi:10.17632/m4sbt8hbvk.3 (CC BY 4.0)")


def aria_fire_causes() -> None:
    aria = load_aria()
    n_known = first_category(aria.loc[aria["is_fire"], "primary_causes"]).size
    s = fire_statistics(aria, top=8)["top_primary_causes"]
    share = s / n_known
    s, share = s[::-1], share[::-1]
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.barh(s.index, s.values, color=["#c92a2a" if i == len(s) - 1 else "#868e96" for i in range(len(s))])
    for b, p in zip(bars, share.values):
        ax.text(b.get_width() + 30, b.get_y() + b.get_height() / 2, f"{p:.0%}", va="center", fontsize=8)
    ax.set_xlabel("fire events (first-listed primary cause category; fires with a known cause only)")
    ax.set_title("What starts industrial fires? ARIA database, France")
    _save(fig, "aria_fire_causes.png", "BARPI, base ARIA via data.gouv.fr, extraction 2020-10-12 (Licence Ouverte 2.0)")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (hall_cable_vs_welding, lab_electrical_detector, metropt_physics, thermal_samples, aria_fire_causes):
        fn()
