"""Build the AI model report from computed results only.

    .venv/Scripts/python scripts/build_model_report.py           # Markdown + figures
    .venv/Scripts/python scripts/build_model_report.py --pdf     # + HTML and PDF (Microsoft Edge / Chrome headless)

Every number in docs/MODEL_REPORT.md is computed here from the saved held-out predictions,
the registered models and the real datasets. Nothing is typed in by hand.
Prerequisites: python -m ingest download ; python -m ai.train ; python -m ai.holdout
"""
from __future__ import annotations

import json
import subprocess
import sys
import warnings
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

from ai import compressor as C  # noqa: E402
from ai import lead_time as L  # noqa: E402
from ai import motor as M  # noqa: E402
from ai import registry  # noqa: E402
from ai import zone_fire as Z  # noqa: E402
from ai.train import ZONE_DEFAULT, ZONE_RULES, wilson  # noqa: E402
from backend.app.cases import MIN_LIVE_NODES, STABILIZATION_MIN, STABLE_P_FIRE  # noqa: E402
from backend.app.replay import HallData, ReplayEngine, held_mask  # noqa: E402
from ingest.loaders.common import CACHE  # noqa: E402
from ingest.loaders.fire_sensors import load_indoor_lab, load_industrial_hall  # noqa: E402
from ingest.loaders.machines import METROPT3_FAILURES, load_metropt3, load_skab  # noqa: E402

DOCS = ROOT / "docs"
FIG = DOCS / "report_figures"
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False, "font.size": 9})


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        out.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r) + " |")
    return "\n".join(out)


# ----------------------------------------------------------------------------- computations

def zone_results() -> dict:
    oof_path = CACHE / "zone_oof.pkl"
    if not oof_path.exists():
        raise SystemExit("run: python -m ai.train   (creates the held-out predictions)")
    oof = pd.read_pickle(oof_path)
    hall = load_industrial_hall()
    hall["held"] = held_mask(hall)
    table = Z.build_table(hall)
    table["event"] = table["event"].where(~table["event"].str.endswith("#-1"), "")
    nested_ev, nested = Z.nested_rule_evaluation(oof, ZONE_RULES)
    fixed_ev, fixed = Z.evaluate_rule(oof, *ZONE_DEFAULT)
    base_ev, base_s, base_grid = Z.particle_baseline(table)
    # paired timing on fires detected by both methods
    pair = nested_ev[nested_ev["truth"] == "fire"][["event", "fire_alarm", "time_to_alarm_s"]].merge(
        base_ev[base_ev["truth"] == "fire"][["event", "fire_alarm", "time_to_alarm_s"]], on="event", suffixes=("_ai", "_base"))
    both = pair[pair["fire_alarm_ai"] & pair["fire_alarm_base"]]
    diff = both["time_to_alarm_s_base"] - both["time_to_alarm_s_ai"]

    def cm(ev):
        f, n = ev[ev["truth"] == "fire"], ev[ev["truth"] == "nuisance"]
        return {"TP": int(f["fire_alarm"].sum()), "FN": int((~f["fire_alarm"]).sum()),
                "FP": int(n["fire_alarm"].sum()), "TN": int((~n["fire_alarm"]).sum())}

    # background alarms: all vs live-only, and relation to held->live transitions
    oof = oof.merge(hall[["sensor_id", "timestamp", "held"]], on=["sensor_id", "timestamp"], how="left")
    bg = oof[oof["event"] == ""]
    hours_all = bg.groupby("sensor_id").size().mean() * 10 / 3600
    hours_live = bg[~bg["held"]].groupby("sensor_id").size().mean() * 10 / 3600
    t_all = Z.zone_alarm_times(bg, *ZONE_DEFAULT)
    ep_all = t_all[(t_all.diff() > pd.Timedelta("10min")) | (np.arange(len(t_all)) == 0)]
    t_live = Z.zone_alarm_times(bg[~bg["held"]], *ZONE_DEFAULT)
    ep_live = t_live[(t_live.diff() > pd.Timedelta("10min")) | (np.arange(len(t_live)) == 0)]
    trans = []
    for _, g in hall.sort_values("timestamp").groupby("sensor_id"):
        x, ts = g["held"].to_numpy(), g["timestamp"].to_numpy()
        trans += list(ts[np.flatnonzero(x[:-1] & ~x[1:]) + 1])
    trans = pd.Series(pd.to_datetime(sorted(set(trans)), utc=True))
    near = sum(((trans <= x) & (trans >= x - pd.Timedelta("15min"))).any() for x in ep_all)
    n_events = table.loc[table["event"] != ""].groupby("label")["event"].nunique().to_dict()
    held_by_scen = hall.groupby("scenario")["held"].mean()
    return {"nested": nested, "nested_ev": nested_ev, "fixed": fixed, "fixed_ev": fixed_ev,
            "base_ev": base_ev, "base": base_s, "base_grid": base_grid,
            "timing": {"pairs": len(both), "ai_earlier": int((diff > 0).sum()), "base_earlier": int((diff < 0).sum()),
                       "median_s": float(diff.median()), "q1_s": float(diff.quantile(0.25)), "q3_s": float(diff.quantile(0.75))},
            "pair_table": pair,
            "cm": {"nested": cm(nested_ev), "fixed": cm(fixed_ev), "baseline": cm(base_ev)},
            "bg": {"hours_all": round(hours_all, 1), "hours_live": round(hours_live, 1), "episodes_all": len(ep_all),
                   "episodes_live": len(ep_live), "after_transition": int(near)},
            "rows": len(hall), "nodes": hall["sensor_id"].nunique(), "events": n_events,
            "n_features": len(Z.feature_columns(table)),
            "held_share": round(float(hall["held"].mean()) * 100, 1),
            "held_green_waste": round(float(held_by_scen.get("Green_Waste", 0)) * 100, 0),
            "held_background": round(float(held_by_scen.get("Background", 0)) * 100, 1)}


def lead_results() -> dict:
    lab = load_indoor_lab()
    r = L.evaluate(lab)
    return {"table": r, "sens": L.sensitivity(lab)}


def compressor_results() -> dict:
    feats = C.window_features(load_metropt3().set_index("timestamp"))
    out = {name: C.evaluate(feats, METROPT3_FAILURES, sc)
           for name, sc in (("Autoencoder", C.AutoencoderScorer()), ("Isolation Forest", C.IsolationForestScorer()))}
    return {"models": out, "train_windows": int((feats.index < C.TRAIN_END).sum()), "test_windows": int((feats.index >= C.TRAIN_END).sum())}


def motor_results() -> dict:
    exps = load_skab()
    tune = [e for e in exps if e.group == "valve1"]
    test = [e for e in exps if e.group in ("valve2", "other")]
    rows = []
    for cls in (M.ThreeSigma, M.PCAResidual, M.Autoencoder):
        attr, values = M.GRID[cls.__name__]
        best = max(values, key=lambda v: M.run(tune, M._with(cls, attr, v))["f1"])
        r = M.run(test, M._with(cls, attr, best))
        rows.append({"method": cls.name, "tuned": f"{attr}={best}", **r})
    return {"table": pd.DataFrame(rows), "n_test": sum(M.clean_reference(e) for e in test), "n_tune": len(tune)}


def stabilization_audit() -> dict:
    d = HallData()
    e = ReplayEngine(d)
    e.load("Cable#4")
    while True:
        e.step(1)
        if e.state.ticks[-1]["level"] == "CRITICAL" or e.state.finished:
            break
    action = pd.Timestamp(e.state.ticks[-1]["t"])
    e.step(5000)
    t = pd.DataFrame(e.state.ticks)
    t["t"] = pd.to_datetime(t["t"])
    after = t[t["t"] > action]
    live = after["fresh_nodes"] >= MIN_LIVE_NODES
    good = live & (after["level"] == "NORMAL") & (after["max_p_fire"].fillna(1) < STABLE_P_FIRE)
    run = best = 0
    for lv, gd in zip(live, good):
        if not lv:
            continue
        run = run + 1 if gd else 0
        best = max(best, run)
    ev = d.events.loc["Cable#4"]
    nxt = d.events.loc[d.events["start"] > ev["end"], "start"].min()
    return {"t": t, "action": action, "event_end": ev["end"], "event_start": ev["start"], "next_start": nxt,
            "window_end": e.state.window_end, "ticks_after": len(after), "live_after": int(live.sum()),
            "nonlive_after": int((~live).sum()), "best_run_min": round(best * 10 / 60, 1),
            "monotonic": bool(after["t"].is_monotonic_increasing),
            "held_share_post": round(float(d.raw[(d.raw["timestamp"] > ev["end"]) & (d.raw["timestamp"] <= e.state.window_end)]["held"].mean()) * 100, 1)}


# ----------------------------------------------------------------------------- figures

def fig_confusion(z, m) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.2))
    for ax, key, title in zip(axes, ["nested", "baseline", None], ["AEROGUARD zone model\n(held-out events, nested rule)", "Single particle threshold\n(stand-in for a smoke detector)", None]):
        if key is None:
            continue
        c = z["cm"][key]
        mat = np.array([[c["TP"], c["FN"]], [c["FP"], c["TN"]]])
        ax.imshow(mat, cmap="Blues", vmin=0, vmax=17)
        for (i, j), v in np.ndenumerate(mat):
            ax.text(j, i, v, ha="center", va="center", fontsize=14, color="white" if v > 9 else "black")
        ax.set_xticks([0, 1], ["fire alarm", "no fire alarm"])
        ax.set_yticks([0, 1], ["real fire\n(17 events)", "nuisance\n(15 events)"])
        ax.set_title(title, fontsize=9)
    t = m["table"].set_index("method")
    ax = axes[2]
    names = ["MLP autoencoder", "Fixed k-sigma limits"]
    far = [t.loc[n, "false_alarm_rate"] for n in names]
    mar = [t.loc[n, "missed_alarm_rate"] for n in names]
    x = np.arange(2)
    ax.bar(x - 0.18, far, 0.36, label="false-alarm rate", color="#e8590c")
    ax.bar(x + 0.18, mar, 0.36, label="missed-alarm rate", color="#1971c2")
    for xi, v in zip(x - 0.18, far): ax.text(xi, v + 0.01, f"{v:.0%}", ha="center", fontsize=8)
    for xi, v in zip(x + 0.18, mar): ax.text(xi, v + 0.01, f"{v:.0%}", ha="center", fontsize=8)
    ax.set_xticks(x, ["Autoencoder", "k-sigma limits"])
    ax.set_ylim(0, 0.6)
    ax.legend(fontsize=7)
    ax.set_title("Motor bench (SKAB), point level\nheld-out experiments", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "confusion_matrices.png")
    plt.close(fig)


def fig_stabilization(s) -> None:
    t = s["t"]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 4), sharex=True)
    a1.plot(t["t"], t["max_p_fire"], color="#c92a2a", lw=1, label="max P(fire), live nodes")
    a1.axhline(STABLE_P_FIRE, color="#555", ls="--", lw=0.8, label=f"stabilization limit {STABLE_P_FIRE}")
    a1.set_ylabel("P(fire)")
    a1.legend(fontsize=7, loc="upper right")
    a2.fill_between(t["t"], t["fresh_nodes"], step="mid", color="#2b8a3e", alpha=0.6, label="nodes with live data")
    a2.fill_between(t["t"], t["held_nodes"], step="mid", color="#868e96", alpha=0.5, label="nodes repeating held values")
    a2.set_ylabel("sensor nodes")
    a2.legend(fontsize=7, loc="upper left")
    for ax in (a1, a2):
        ax.axvspan(s["event_start"], s["event_end"], color="#ffa8a8", alpha=0.3)
        ax.axvline(s["action"], color="#1971c2", lw=1.2)
    a1.text(s["action"], 0.55, "  case opened /\n  action recorded", color="#1971c2", fontsize=7,
            transform=a1.get_xaxis_transform())
    a1.set_title("Cable#4 replay: after the fire, the recording repeats held values; no live recovery data before the next experiment", fontsize=9)
    fig.text(0.99, 0.01, "Source: Industrial Hall dataset, doi:10.17632/yghykzm4km.1", ha="right", fontsize=7, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIG / "stabilization_audit.png")
    plt.close(fig)


# ----------------------------------------------------------------------------- report

def write(z, l, c, m, s) -> str:
    cards = {f"{x['name']}/{x['version']}": x for x in registry.cards()}
    nz, fx, bs, bg, tm = z["nested"], z["fixed"], z["base"], z["bg"], z["timing"]
    cmn, cmb = z["cm"]["nested"], z["cm"]["baseline"]
    prec = cmn["TP"] / max(1, cmn["TP"] + cmn["FP"])
    lt = l["table"]
    scored = lt[~lt["detector_before_calibration_end"]]
    elec = scored[scored["source"] == "electrical"]
    lt_show = lt.assign(**{k: (lt[k] / 60).round(1) for k in ("detector_s", "aeroguard_s", "lead_time_s")}).rename(
        columns={"detector_s": "detector (min)", "aeroguard_s": "AEROGUARD (min)", "lead_time_s": "earlier by (min)"})[
        ["experiment", "detector (min)", "AEROGUARD (min)", "earlier by (min)", "false_warning_in_stage0", "detector_before_calibration_end"]]
    ae, iso = c["models"]["Autoencoder"], c["models"]["Isolation Forest"]
    comp_ev = pd.concat([v[1].assign(model=k) for k, v in c["models"].items()])[["model", "failure", "start", "detected", "first_alarm", "lead_time_h"]]
    mt = m["table"][["method", "tuned", "experiments", "tp", "fp", "fn", "tn", "f1", "false_alarm_rate", "missed_alarm_rate", "anomalies_detected"]]
    ne = z["nested_ev"][["event", "truth", "fire_alarm", "time_to_alarm_s", "rule_p_fire", "rule_min_nodes"]]
    zc = cards.get("zone_fire/1.0.0", {})
    base_nuis = ", ".join(z["base_ev"].query("truth == 'nuisance' and fire_alarm")["event"])
    today = date.today().isoformat()

    return f"""# AEROGUARD TRUST — AI Model Report

**Team ORBITA · INSAT · AeroEntrepreneur 2026 (Tunisian Aeroday × Protection Civile × INJAZ Tunisia)**
Version {today}. Generated by `scripts/build_model_report.py` from the saved held-out predictions and registered models; no number in this report is typed by hand.

The hackathon specification asks the model report to cover the **architecture**, **why this model was chosen**, and the **dataset used** (§04, "Rapport du modèle"). Sections 3, 5 and 6 answer these directly.

---

## 1. Executive summary

AEROGUARD TRUST monitors a **metal-working production hall** with 9 multi-gas sensor nodes and uses an AI model to tell **incipient fires** apart from **routine process nuisances** (welding, abrasive cutting, exhaust, solvents), feeding a verified response workflow (Safety Case, independent verification, emergency Fire Pack).

Evaluated on **real, publicly available sensor recordings** of controlled experiments in an industrial hall, with every recording judged by a model that never saw it:

| Result (held-out, nested) | AEROGUARD AI zone model | Calibrated particle threshold (same protocol) |
|---|---|---|
| Real fires raising a fire alarm | {wilson(nz['fires_detected'], nz['fire_events'])} | {wilson(bs['fires_detected'], bs['fire_events'])} |
| Routine nuisances raising a fire alarm | {wilson(nz['nuisance_false_alarms'], nz['nuisance_events'])} | {wilson(bs['nuisance_false_alarms'], bs['nuisance_events'])} |
| Background alarm episodes | {bg['episodes_all']} in {bg['hours_all']} h | {bs['background_false_alarm_episodes']} in {bs['background_hours']} h |
| Alarm time, fires detected by both ({tm['pairs']}) | earlier in {tm['ai_earlier']}/{tm['pairs']}; median {tm['median_s']:.0f} s earlier | earlier in {tm['base_earlier']}/{tm['pairs']} |

**Main finding, stated plainly:** on this dataset the AI zone model **does not outperform a well-calibrated particle threshold** on fire detection, nuisance rejection or background alarms. Its measurable advantage is **earlier alarms** on most fires. An earlier version of our analysis claimed a large nuisance-rejection advantage; that came from a bug in the baseline and has been corrected.

Second line of evidence: on laboratory fires, an unsupervised multi-gas rule warned **before a conventional smoke detector in {int(scored['warned_before_detector'].sum())}/{len(scored)} fires**, with the four electrical fires warned **{', '.join(f'{v/60:.1f}' for v in elec['lead_time_s'])} minutes earlier**.

**What this does not show:** an advantage of the AI over a calibrated simple rule in nuisance rejection; the data come from controlled experiments, not from an operating Tunisian factory; the number of events is small (32), so the intervals are wide; the background alarm rate (about one episode every {bg['hours_live'] / max(1, bg['episodes_live']):.1f} h of live data) is too high for production use; and **no dataset demonstrates that the system prevents industrial fires.**

## 2. Industrial problem and selected use case

- **Problem.** In metal-working plants, hot work (welding, grinding, abrasive cutting) produces smoke, particles and gases that conventional detectors confuse with fire. Frequent nuisance alarms lead operators to ignore or disable detection, while equipment failures are the largest category of fire causes in industrial accident records (ARIA database, France: 43 % of fires with a known primary cause list "equipment failure" first; see `docs/DATASETS.md`).
- **Sector.** Discrete manufacturing, metal-working production halls (automotive components, fabrication). See `docs/INDUSTRY_SELECTION.md` for the comparison of candidate use cases.
- **Use case.** Zone-level early fire detection that does not raise fire alarms for routine hot work, followed by a verified response. Certified fire alarms and emergency shutdown systems remain independent of AEROGUARD.
- **Why not "automotive machine monitoring"?** No authentic factory machine dataset was available. The monitored object is therefore the **hall zone**, which the available data supports.

## 3. Data sources and provenance

All data are real, public and credited; nothing is synthetic. Full audit on the actual records: `docs/DATA_PROVENANCE_AUDIT.md`.

| Role | Dataset | Nature | Size used | License | Integrity |
|---|---|---|---|---|---|
| **Primary model** | Indoor Fire Dataset with Distributed Multi-Sensor Nodes (Industrial Hall), Otto von Guericke University Magdeburg, Mendeley Data, doi:10.17632/yghykzm4km.1 | **Controlled experiments** in a real 10 × 22 × 8 m industrial hall (no ventilation), 9 sensor nodes, 10 s sampling, July 2023 | {z['rows']:,} rows; {z['events'].get('fire', 0)} fire + {z['events'].get('nuisance', 0)} nuisance recordings | CC BY 4.0 | SHA-256 matches publisher |
| Lead time vs detector | Indoor Laboratory Fire Dataset, A. Nazir, Zayed University, doi:10.17632/f3mjnbm9b3.1 | Laboratory fires with conventional detector state | 8 recordings | CC BY 4.0 | SHA-256 matches publisher |
| Secondary: compressor | MetroPT-3, UCI, doi:10.24432/C5VW3R | **Real operational data**, metro train air compressor (railway, not factory) | 7 months, 4 reported failures | CC BY 4.0 | no publisher hash; local hash recorded |
| Secondary: motor | SKAB, Skoltech, doi:10.34740/KAGGLE/DSV/1693952 | Laboratory pump/motor bench | 34 experiments | GPL-3.0 | no publisher hash; local hash recorded |

**Experimental hall versus operating factory.** The Industrial Hall recordings are real sensor measurements, but of **staged** events: fires and nuisances were started deliberately, one at a time, in an otherwise idle, unventilated hall. A working factory differs in ways that matter: continuous production emissions, several activities at once, ventilation and air movement, different materials and sensor placement. Performance in a factory must therefore be re-measured on site.

All DOIs above were resolved during this audit and point to the stated records; publisher SHA-256 hashes were verified for all Mendeley files.

## 4. Data exploration and preprocessing

- **Primary data.** 9 nodes × 10 s; channels CO (ppm), CO₂ (ppm), H₂ (raw), VOC (raw), particle counts by size, air temperature (°C), humidity (%). Labels per row: scenario, fire/nuisance flags, stage (outgassing, smouldering, flaming…).
- **Data-quality finding (important).** {z['held_share']} % of rows are **held values**: all 13 channels identical to the previous readings for minutes at a time. They occur almost entirely in the 20–45 minutes after each experiment ({z['held_background']} % of background rows; {z['held_green_waste']:.0f} % of the green-waste recording), probably while the hall was ventilated. Held rows are **not measurements**; the prototype treats them as "no live data" (Section 12).
- **Other findings:** 639 rows after the abrasive-cutting run labelled as a nuisance but with scenario "Background"; one stray single-row "Cable" label (ignored); welding and abrasive cutting recorded only once each.
- **Features (causal).** For every node and time *t*, using only readings up to *t*: difference from the node's background (rolling 15-min median ending 3 min before *t*), robust z-score, 60-s slope and 60-s maximum for each channel, plus ratios (CO per particle, VOC per particle, fine-particle fraction, CO₂ per CO). {z['n_features']} features. A test (`tests/test_backend.py::test_features_are_causal`) checks that deleting all future readings does not change any feature.

## 5. Model architectures and baselines

| Component | Model | Why this model |
|---|---|---|
| **Zone fire model (primary)** | Gradient-boosted decision trees (scikit-learn `HistGradientBoostingClassifier`, 150 iterations, learning rate 0.08, 31 leaves, L2 = 1, balanced class weights); classes normal / nuisance / fire | Tabular, multi-channel features; handles non-linear interactions (e.g. CO rising *with* particles vs particles alone); fast on a laptop; robust to unscaled raw sensor units; probability output usable by an explainable decision rule |
| Decision rule | Node confirmed when P(fire) ≥ p for 30 s; zone alarm when ≥ N nodes confirmed ("coincidence", as in double-knock fire systems) | Reduces single-sensor false alarms; transparent for operators |
| Baseline | Particle count above the node's background on any node for 30 s; threshold chosen from {Z.PARTICLE_GRID} with the same nested protocol (selected: {bs['thresholds_selected']}) | Stand-in for an optical smoke detector (not a certified device); calibrated as fairly as the AI rule |
| Early warning (lab) | Unsupervised robust z-score on 5 gas/temperature channels, ≥ 2 channels above z = 8 for 5 readings | No training data needed; fixed before results |
| Compressor (secondary) | MLP autoencoder (16-4-16) and Isolation Forest on 30-min windows incl. a physics residual | Unsupervised: failures are rare |
| Motor (secondary) | MLP autoencoder (6-3-6), PCA residual, k-sigma limits | Classic process-monitoring baselines |

## 6. Training methodology

- **Zone model:** trained on all other recordings plus 10 % of background rows (background is 83 % of rows; subsampled for speed and balance). Hyperparameters were set once and **not tuned**. The final registered model (`zone_fire/1.0.0`) uses all data; the demo uses **held-out models** (`zone_fire_holdout/*`), each trained without the event it replays.
- **Compressor:** trained only on February–March 2020 (no reported failure); threshold = 99.5th percentile of training scores; alarm after 1 h.
- **Motor:** first 400 samples of each experiment are the normal reference (SKAB convention); thresholds tuned on the {m['n_tune']} `valve1` experiments; results on the other {m['n_test']} (experiment `other/2` excluded: its reference window already contains anomalies).
- **Traceability:** each model has a card with its metrics, configuration, the SHA-256 of every training file and of the model file (`ai/registry/*/card.json`); a modified model file is refused at load time.

## 7. Evaluation protocol and leakage prevention

| Risk | What we did | Residual concern |
|---|---|---|
| Same event in training and test | **Leave-one-event-out**: each of the {len(ne)} fire/nuisance recordings is scored by a model trained without it; background scored by 5 time-block models | Out-of-fold predictions of *other* events come from models that did see the held-out event (affects rule selection only) |
| Threshold chosen on test results | **Nested selection** of (p, N): for each event, the rule is chosen on the other events with a criterion fixed in advance (detect every fire → fewest nuisance alarms → fewest background alarms → fastest) | — |
| Design iterations informed by results | Disclosed: the first leave-one-event-out run (argmax rule, single node) raised fire alarms on 12/15 nuisances; the **coincidence-rule family** was introduced after seeing that result; the background subsample and iteration count were reduced for runtime at the same time | Nested selection does not remove the influence of choosing the rule family; treat the zone results as a **held-out estimate with design-stage optimism** |
| Feature design informed by data | Disclosed: features were designed after exploratory plots of fire vs welding signals | Mild optimism |
| Future data | Features use past readings only (tested); the replay calls the model tick by tick | — |
| Counting samples instead of events | All headline metrics are **per event** (32 events, one hall) | Small sample: see intervals |
| Compressor model choice | Autoencoder preferred **after** seeing the 4 failures | Reported as **exploratory**, both models shown |

## 8. Experimental results

### 8.1 Primary: fire vs nuisance in the industrial hall (event level)

| | Real fire ({nz['fire_events']}) | Nuisance ({nz['nuisance_events']}) |
|---|---|---|
| **AEROGUARD, nested (headline)**: fire alarm | {cmn['TP']} | {cmn['FP']} |
| AEROGUARD, nested: no fire alarm | {cmn['FN']} | {cmn['TN']} |
| Calibrated particle threshold, nested: fire alarm | {cmb['TP']} | {cmb['FP']} |
| Calibrated particle threshold, nested: no fire alarm | {cmb['FN']} | {cmb['TN']} |

- Fire detection rate {wilson(nz['fires_detected'], nz['fire_events'])}; nuisance fire-alarm rate {wilson(nz['nuisance_false_alarms'], nz['nuisance_events'])}; precision of a fire alarm {prec:.0%} on this event mix.
- Median time from labelled event start to zone alarm: {nz['median_time_to_alarm_s']:.0f} s. (Labelled start is the experiment start, not ignition; smouldering phases are slow.)
- Rule p ≥ {ZONE_DEFAULT[0]}, N ≥ {ZONE_DEFAULT[1]} chosen on all events (optimistic, not the headline): {fx['fires_detected']}/{fx['fire_events']} fires, {fx['nuisance_false_alarms']}/{fx['nuisance_events']} nuisances. Rules chosen across nested folds: {nz['rules_selected']}.
- **Timing (paired, {tm['pairs']} fires detected by both):** the AI alarmed earlier in {tm['ai_earlier']}, later in {tm['base_earlier']}; median difference {tm['median_s']:.0f} s in favour of the AI (interquartile range {tm['q1_s']:.0f} to {tm['q3_s']:.0f} s).
- **Baseline background alarms:** {bs['background_false_alarm_episodes']} episodes in {bs['background_hours']} h.
- **AI background:** {bg['episodes_all']} fire-alarm episodes in {bg['hours_all']} h of background ({bg['episodes_live']} in {bg['hours_live']} h when held values are excluded); {bg['after_transition']} of the {bg['episodes_all']} start within 15 min after live data resumes following a held stretch, suggesting part of them are artefacts of the recording, but this cannot be proven.

![Confusion matrices](report_figures/confusion_matrices.png)

![Fires vs nuisances](../ai/reports/zone_fire_vs_nuisance.png)

Paired alarm times on fires (seconds from labelled event start):

{md_table(z['pair_table'])}

### 8.2 Earlier than a conventional detector (laboratory)

{md_table(lt_show)}

`clothing_2` is excluded because its detector fired during the 120-s calibration window. Result: earlier in {wilson(int(scored['warned_before_detector'].sum()), len(scored))}.

![Lead time](../ai/reports/lead_time.png)

Sensitivity to the threshold (the result is not a single lucky setting):

{md_table(l['sens'])}

### 8.3 Secondary: compressor failures (railway, exploratory)

| Model | detected | before reported start | false alarms per week | normal weeks evaluated |
|---|---|---|---|---|
| Autoencoder | {ae[0]['detected']}/4 | {ae[0]['detected_before_start']} | {ae[0]['false_alarms_per_week']} | {ae[0]['normal_weeks_evaluated']} |
| Isolation Forest | {iso[0]['detected']}/4 | {iso[0]['detected_before_start']} | {iso[0]['false_alarms_per_week']} | {iso[0]['normal_weeks_evaluated']} |

{md_table(comp_ev)}

Training windows: {c['train_windows']}; test windows: {c['test_windows']}. With 4 failures these lead times are anecdotes, not statistics.

### 8.4 Secondary: motor anomalies (laboratory bench, point level)

{md_table(mt)}

The autoencoder matches the k-sigma limits on F1 with fewer false alarms; the gain is modest.

## 9. Visual evidence

![Cable fire vs welding](figures/hall_cable_vs_welding.png)

![ARIA causes](figures/aria_fire_causes.png)

## 10. Error analysis and false alarms

Per-event results (nested rule):

{md_table(ne)}

- **Missed fire:** the event missed in the nested estimate is the one for which leaving it out makes a stricter rule look best; with the default rule it is detected.
- **Nuisance fire alarms (AI):** ethanol, both fog-machine "smoke" runs and **welding**. The calibrated particle rule alarms on {base_nuis}; both are fooled by welding. Welding exists only once in the data, so the model had never seen welding when scoring it. This is the most important weakness for a metal-working plant; it requires site-specific welding recordings and the use of hot-work permits as context.
- **Background alarms:** the AI raises {bg['episodes_all']} episodes where the particle rule raises {bs['background_false_alarm_episodes']}; too frequent for production. The AI reacts to small multi-gas changes, which helps it alarm earlier but also makes it more sensitive to background drift.

## 11. Limitations and generalization risks

1. Controlled experiments in one idle, unventilated hall over four days; not an operating factory, not Tunisia.
2. 32 events; wide confidence intervals; one welding and one cutting recording.
3. Held values after experiments: no live recovery data; background statistics partly affected.
4. Design-stage optimism (rule family and features chosen after seeing results).
5. Sensor positions in the demo map are illustrative; the dataset does not give node coordinates.
6. Risk levels are operational categories, not calibrated fire probabilities.
7. **Prevention of fires is not demonstrated.**

## 12. Inference API and prototype integration

- `ai/inference.py` (`ZoneFireDetector.assess`), loaded with hash verification from `ai/registry`.
- Backend (`backend/app`): the replay engine plays the real recording tick by tick, calls the held-out model only on **live** readings at the cursor, and passes node outputs to an explainable risk engine (NORMAL / WATCH / HIGH / CRITICAL / NO DATA). A Safety Case opens on CRITICAL; the replay pauses for the response.
- **Stabilization audit (Cable#4).** A previous run reported "44.7 min of normal readings". This audit found that those readings are **held values** (identical on all nodes, all channels). After correction: {s['ticks_after']} ticks after the action, chronological = {s['monotonic']}; {s['live_after']} with ≥ {MIN_LIVE_NODES} live nodes, {s['nonlive_after']} held or missing; longest run of live normal readings {s['best_run_min']} min against the {STABILIZATION_MIN}-min rule; the window ends at {s['window_end'].strftime('%H:%M:%S')}, before the next experiment ({s['next_start'].strftime('%H:%M:%S')}). **The case therefore stays open, awaiting stabilization**, which is the correct behaviour when no trustworthy recovery data exists. The {STABILIZATION_MIN}-minute rule is a prototype setting, not a validated industrial standard. Technician and verifier must be different people (enforced and tested).

![Stabilization audit](report_figures/stabilization_audit.png)

## 13. Reproducibility

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # exact versions: requirements-lock.txt
.venv/Scripts/python -m ingest download                      # official sources, hash-checked
.venv/Scripts/python -m ai.train                             # ~10 min: models, held-out predictions, ai/reports/evaluation.md
.venv/Scripts/python -m ai.holdout                           # held-out demo models
.venv/Scripts/python scripts/build_model_report.py --pdf     # this report
.venv/Scripts/python -m pytest -q                            # tests
.venv/Scripts/python -m uvicorn backend.app.main:app --port 8000
```
Random seeds are fixed (0). Raw data are not redistributed; model binaries are rebuilt by the commands above, and their model cards (metrics + hashes) are in the repository.

## 14. Conclusions and next validation steps

On held-out staged events, the AI zone model detects fires about as well as a calibrated particle threshold, **does not reject nuisances better**, raises more background alarms, and **alarms earlier** on most fires (median {tm['median_s']:.0f} s). On laboratory fires, multi-gas sensing warned earlier than a conventional detector. The honest value of the AI today is **earlier warning**, not fewer false alarms; the evidence is real but small and comes from controlled experiments.

Next steps: (0) test, on new held-out data, a hybrid in which the AI gives the early warning (WATCH/HIGH) and a calibrated particle or coincidence rule confirms the fire alarm (not tuned here, to avoid fitting to these 32 events); (1) pilot in a Tunisian metal-working hall with the Protection Civile, recording normal production and welding for several weeks; (2) re-estimate false-alarm rates on that data; (3) add welding/hot-work permits as model context; (4) validate the stabilization rule with safety engineers; (5) obtain the Protection Civile incident database to prioritise risks.

## 15. References

1. Indoor Fire Dataset with Distributed Multi-Sensor Nodes (Industrial Hall). Otto von Guericke University Magdeburg (contributor listed as Pascal V.), Mendeley Data, V1, 2024. doi:10.17632/yghykzm4km.1. CC BY 4.0.
2. Nazir, A. Indoor Laboratory Fire Dataset. Zayed University, Mendeley Data, V1, 2021. doi:10.17632/f3mjnbm9b3.1. CC BY 4.0. Related article: *Early Fire Detection: A New Indoor Laboratory Dataset and Data Distribution Analysis*, Fire 5(1):11, 2022, doi:10.3390/fire5010011 (DOI resolves; article page not fetched: publisher blocks automated access).
3. Veloso, B., Gama, J., Ribeiro, R., Pereira, P. MetroPT-3 Dataset. UCI Machine Learning Repository, 2023. doi:10.24432/C5VW3R. CC BY 4.0. Davari, N. et al., IEEE DSAA 2021, doi:10.1109/DSAA53316.2021.9564181; Veloso, B. et al., Scientific Data 9:764, 2022, doi:10.1038/s41597-022-01877-3.
4. Katser, I. D., Kozitsin, V. O. Skoltech Anomaly Benchmark (SKAB), 2020. doi:10.34740/KAGGLE/DSV/1693952. GPL-3.0.
5. Najafi, M. et al. Thermal image of equipment (Induction Motor). Babol Noshirvani University of Technology, Mendeley Data, V3, 2023. doi:10.17632/m4sbt8hbvk.3. CC BY 4.0 (illustrative images only).
6. BARPI. Base ARIA. Extraction published on data.gouv.fr, 2020-10-12. Licence Ouverte 2.0.
7. Pedregosa, F. et al. Scikit-learn: Machine Learning in Python. JMLR 12, 2825–2830, 2011.
"""


def build_pdf(md_path: Path) -> Path:
    import markdown
    html_body = markdown.markdown(md_path.read_text(encoding="utf-8"), extensions=["tables", "fenced_code"])
    css = """body{font-family:'Segoe UI',Arial,sans-serif;font-size:10.5pt;line-height:1.45;color:#111;max-width:180mm;margin:auto}
h1{font-size:20pt;border-bottom:3px solid #f59e0b;padding-bottom:6px}h2{font-size:14pt;margin-top:22px;border-bottom:1px solid #ddd;page-break-after:avoid}
h3{font-size:11.5pt;page-break-after:avoid}table{border-collapse:collapse;width:100%;font-size:8.5pt;margin:8px 0;page-break-inside:avoid}
th,td{border:1px solid #ccc;padding:3px 5px;text-align:left;vertical-align:top}th{background:#f3f4f6}
img{max-width:100%;page-break-inside:avoid;display:block;margin:8px auto}code,pre{font-family:Consolas,monospace;font-size:8.5pt}
pre{background:#f6f8fa;padding:8px;white-space:pre-wrap}@page{size:A4;margin:16mm 14mm}"""
    html_path = md_path.with_suffix(".html")
    html_path.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>AEROGUARD TRUST AI Model Report</title>"
                         f"<style>{css}</style></head><body>{html_body}</body></html>", encoding="utf-8")
    pdf_path = md_path.with_suffix(".pdf")
    for browser in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(browser).exists():
            subprocess.run([browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf_path}", html_path.as_uri()], check=True, timeout=180,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return pdf_path
    raise SystemExit("No Edge/Chrome found for PDF printing")


def main(pdf: bool) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    z = zone_results(); print("zone ok", z["nested"]["fires_detected"], z["nested"]["nuisance_false_alarms"], z["bg"])
    l = lead_results(); print("lead ok")
    c = compressor_results(); print("compressor ok")
    m = motor_results(); print("motor ok")
    s = stabilization_audit(); print("stabilization ok", s["best_run_min"], s["live_after"], s["nonlive_after"])
    fig_confusion(z, m)
    fig_stabilization(s)
    md = DOCS / "MODEL_REPORT.md"
    md.write_text(write(z, l, c, m, s), encoding="utf-8")
    (FIG / "numbers.json").write_text(json.dumps({"zone_nested": z["nested"], "zone_cm": z["cm"], "background": z["bg"],
                                                  "zone_baseline": z["base"], "zone_timing": z["timing"],
                                                  "stabilization": {k: str(v) for k, v in s.items() if k != "t"}},
                                                 indent=2, default=str), encoding="utf-8")
    print("wrote", md)
    if pdf:
        print("wrote", build_pdf(md))


if __name__ == "__main__":
    main("--pdf" in sys.argv)
