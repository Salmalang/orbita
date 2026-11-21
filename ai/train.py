"""Train, evaluate and register every AEROGUARD model on the real datasets.

    .venv/Scripts/python -m ai.train            # full run (zone cross-validation takes ~10 min)
    .venv/Scripts/python -m ai.train --fast     # reuse cached zone cross-validation results

Writes ai/registry/<model>/<version>/card.json and ai/reports/evaluation.md (+ figures).
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ai import compressor as C
from ai import lead_time as L
from ai import motor as M
from ai import registry
from ai import zone_fire as Z
from ingest.loaders.common import CACHE
from ingest.loaders.fire_sensors import load_indoor_lab, load_industrial_hall
from ingest.loaders.machines import METROPT3_FAILURES, load_metropt3, load_skab

VERSION = "1.0.0"
REPORTS = Path(__file__).resolve().parent / "reports"
ZONE_RULES = [(p, n) for n in (1, 2, 3) for p in (0.5, 0.7, 0.8, 0.9, 0.95)]
# Chosen by a criterion fixed in advance: detect every fire, then fewest nuisance alarms,
# then fewest background alarms (see report section 1).
ZONE_DEFAULT = (0.95, 2)


def zone(fast: bool) -> dict:
    hall = load_industrial_hall()
    table = Z.build_table(hall)
    table["event"] = table["event"].where(~table["event"].str.endswith("#-1"), "")
    oof_path = CACHE / "zone_oof.pkl"
    if fast and oof_path.exists():
        oof = pd.read_pickle(oof_path)
    else:
        oof = Z.out_of_fold_probabilities(table)
        oof.to_pickle(oof_path)
    grid = pd.DataFrame([Z.evaluate_rule(oof, p, n)[1] for p, n in ZONE_RULES])
    events, chosen = Z.evaluate_rule(oof, *ZONE_DEFAULT)
    baseline = Z.particle_threshold_baseline(table, threshold=float(
        table.loc[table["label"] == "fire"].groupby("event")["pm_total_delta"].max().min() * 0.5))
    base_summary = Z.summarize(baseline)
    # final model on all data
    cols = Z.feature_columns(table)
    train = Z._training_rows(table, np.random.default_rng(0))
    model = Z.make_model().fit(train[cols], train["label"])
    card = registry.save("zone_fire", VERSION, {"model": model, "features": cols}, metrics={
        "evaluation": "leave-one-event-out (each fire/nuisance recording unseen during training)",
        "chosen_rule": chosen, "particle_threshold_baseline": base_summary},
        config={"p_fire": ZONE_DEFAULT[0], "min_nodes": ZONE_DEFAULT[1], "confirm_samples": Z.CONFIRM,
                "baseline_window": Z.BASELINE, "baseline_gap": Z.BASELINE_GAP},
        datasets=["industrial_hall_fire"],
        description="Real fire vs industrial nuisance vs normal, per zone, with 2-node coincidence.")
    return {"grid": grid, "events": events, "chosen": chosen, "baseline": base_summary,
            "baseline_events": baseline, "card": card}


def lead() -> dict:
    lab = load_indoor_lab()
    res = L.evaluate(lab)
    sens = L.sensitivity(lab)
    cfg = {"channels": L.CHANNELS, "floors": L.FLOORS.to_dict(), "calibration_s": L.CALIBRATION_S,
           "z_threshold": L.Z_THRESHOLD, "min_channels": L.MIN_CHANNELS, "confirm_samples": L.CONFIRM}
    scored = res[~res["detector_before_calibration_end"]]
    metrics = {"experiments_scored": len(scored),
               "warned_before_detector": int(scored["warned_before_detector"].sum()),
               "electrical_lead_time_min": (scored.loc[scored["source"] == "electrical", "lead_time_s"] / 60).round(1).tolist(),
               "median_lead_time_min_all": round(scored["lead_time_s"].median() / 60, 1),
               "false_warnings_stage0": int(scored["false_warning_in_stage0"].sum())}
    card = registry.save("early_warning", VERSION, cfg, metrics=metrics, config=cfg, datasets=["indoor_lab_fire"],
                         description="Unsupervised multi-gas early warning, fixed rule, vs conventional detector.")
    return {"results": res, "sensitivity": sens, "metrics": metrics, "card": card}


def compressor() -> dict:
    feats = C.window_features(load_metropt3().set_index("timestamp"))
    out = {}
    for name, scorer in (("Autoencoder", C.AutoencoderScorer()), ("Isolation Forest", C.IsolationForestScorer())):
        out[name] = C.evaluate(feats, METROPT3_FAILURES, scorer)
    ae = C.AutoencoderScorer().fit(feats[feats.index < C.TRAIN_END].to_numpy())
    card = registry.save("compressor", VERSION, {"scorer": ae, "features": list(feats.columns)},
                         metrics={k: v[0] for k, v in out.items()},
                         config={"window": C.WINDOW, "train_end": str(C.TRAIN_END.date()), "quantile": C.QUANTILE,
                                 "confirm_windows": C.CONFIRM, "lookback_h": C.LOOKBACK / pd.Timedelta("1h")},
                         datasets=["metropt3"],
                         description="Unsupervised compressor monitoring with physics residual; evaluated on 4 real failures.")
    return {"models": out, "features": feats, "card": card}


def motor() -> dict:
    table = M.compare(load_skab())
    cfg = {"train_samples": M.N_TRAIN, "quantile": M.QUANTILE, "confirm_samples": M.CONFIRM,
           "tuning": "threshold tuned on valve1, tested on valve2 + other"}
    card = registry.save("motor", VERSION, cfg, metrics={"comparison": table.to_dict(orient="records")}, config=cfg,
                         datasets=["skab"], description="Per-asset motor/pump anomaly detection (autoencoder).")
    return {"table": table, "card": card}


# ------------------------------------------------------------------------------- report

def _md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r) + " |"
              for r in df.itertuples(index=False)]
    return "\n".join(lines)


def figures(z, l, c) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    # lead time bars
    r = l["results"][~l["results"]["detector_before_calibration_end"]]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    colors = ["#2b8a3e" if v > 0 else "#c92a2a" for v in r["lead_time_s"]]
    ax.bar(r["experiment"].str.replace("_", " "), r["lead_time_s"] / 60, color=colors)
    ax.axhline(0, color="#333", lw=0.8)
    ax.set_ylabel("minutes earlier than the\nconventional detector")
    ax.set_title("AEROGUARD early warning vs conventional smoke detector (real fires)")
    for i, v in enumerate(r["lead_time_s"] / 60):
        ax.text(i, v + (0.3 if v >= 0 else -0.9), f"{v:+.1f}", ha="center", fontsize=8)
    fig.text(0.99, 0.01, "Source: Indoor Laboratory Fire Dataset, doi:10.17632/f3mjnbm9b3.1", ha="right", fontsize=7, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(REPORTS / "lead_time.png", dpi=130); plt.close(fig)

    # zone: AI vs particle rule
    ev, base = z["events"], z["baseline_events"]
    labels = ["Fires detected", "Nuisances raising a fire alarm"]
    ai_vals = [ev.loc[ev.truth == "fire", "fire_alarm"].mean(), ev.loc[ev.truth == "nuisance", "fire_alarm"].mean()]
    b_vals = [base.loc[base.truth == "fire", "fire_alarm"].mean(), base.loc[base.truth == "nuisance", "fire_alarm"].mean()]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    x = np.arange(2)
    ax.bar(x - 0.2, b_vals, 0.4, label="single particle threshold", color="#868e96")
    ax.bar(x + 0.2, ai_vals, 0.4, label="AEROGUARD zone model", color="#1971c2")
    for xi, v in zip(x - 0.2, b_vals): ax.text(xi, v + 0.02, f"{v:.0%}", ha="center", fontsize=8)
    for xi, v in zip(x + 0.2, ai_vals): ax.text(xi, v + 0.02, f"{v:.0%}", ha="center", fontsize=8)
    ax.set_xticks(x, labels); ax.set_ylim(0, 1.15); ax.legend(fontsize=8)
    ax.set_title("Industrial hall: real fires vs nuisances (welding, cutting, exhaust...)")
    fig.text(0.99, 0.01, "Source: Indoor Fire Dataset, Industrial Hall, doi:10.17632/yghykzm4km.1", ha="right", fontsize=7, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(REPORTS / "zone_fire_vs_nuisance.png", dpi=130); plt.close(fig)


def write_report(z, l, c, m) -> None:
    ch, b = z["chosen"], z["baseline"]
    grid = z["grid"][["p_fire", "min_nodes", "fires_detected", "fire_events", "nuisance_false_alarms",
                      "nuisance_events", "bg_alarms_quiet", "bg_alarms_post_event", "bg_alarms_warmup",
                      "median_time_to_alarm_s"]]
    ev = z["events"][["event", "truth", "fire_alarm", "time_to_alarm_s"]]
    lr = l["results"].copy()
    for col in ("detector_s", "aeroguard_s", "lead_time_s"):
        lr[col] = (lr[col] / 60).round(1)
    lr = lr.rename(columns={"detector_s": "detector_min", "aeroguard_s": "aeroguard_min", "lead_time_s": "lead_min"})
    comp = pd.DataFrame([{"model": k, **v[0]} for k, v in c["models"].items()]).drop(columns="threshold")
    comp_ev = pd.concat([v[1].assign(model=k) for k, v in c["models"].items()])[["model", "failure", "start", "detected", "first_alarm", "lead_time_h"]]
    text = f"""# AI evaluation report

All numbers below are **measured** on real public datasets ({', '.join(['Industrial Hall', 'Indoor Laboratory', 'MetroPT-3', 'SKAB'])}).
Nothing is synthetic. Rebuild with `.venv/Scripts/python -m ai.train`. Model version {VERSION}.

## 1. Zone model: real fire or industrial nuisance?

Gradient-boosted trees on features relative to each sensor node's recent background (CO, CO₂, H₂, VOC,
particles by size, temperature, humidity). **Leave-one-event-out**: each of the {len(ev)} recordings is judged by
a model that never saw it. Welding and abrasive cutting have a single recording each, so they are tested as
**completely unseen** sources.

Decision rule: **coincidence detection** (as in "double-knock" fire systems): the zone alarms when at least
{ZONE_DEFAULT[1]} sensor nodes are confident (P(fire) ≥ {ZONE_DEFAULT[0]}) for 30 s.

| Result (chosen rule) | AEROGUARD | Single particle threshold |
|---|---|---|
| Real fires detected | {ch['fires_detected']}/{ch['fire_events']} | {b['fires_detected']}/{b['fire_events']} |
| Nuisances raising a fire alarm | {ch['nuisance_false_alarms']}/{ch['nuisance_events']} | {b['nuisance_false_alarms']}/{b['nuisance_events']} |
| Median time from event start to alarm | {ch['median_time_to_alarm_s']} s | – |
| Background alarms in {ch['background_hours']} h of continuous recording (incl. nights): quiet periods | {ch['bg_alarms_quiet']} | – |
| Background alarms: within 70 min after an event (smoke lingering, unventilated hall) | {ch['bg_alarms_post_event']} | – |
| Background alarms: sensor warm-up (first 30 min of the recording) | {ch['bg_alarms_warmup']} | – |

The particle threshold is set to half of the smallest fire peak, so it catches every fire.

**How the rule was chosen** (criterion fixed before comparing): detect every fire; among those rules, fewest
nuisance alarms; then fewest background alarms. The rule is selected on the same out-of-fold predictions it is
reported on (two parameters only), which slightly flatters it.

**Remaining nuisance alarms**: ethanol, the two fog-machine "smoke" runs and welding. Welding is a single
recording, so here the model had **never seen welding** during training. On a real site, welding recordings
from that site and the platform's hot-work permits (declared welding zones and times) would be used.

![zone](zone_fire_vs_nuisance.png)

All rules tested (trade-off between catching fires and ignoring nuisances):

{_md(grid)}

Per event (chosen rule):

{_md(ev)}

## 2. Early warning vs the conventional smoke detector

Unsupervised and **fixed before looking at results**: each recording's first {L.CALIBRATION_S} s define normal; a warning
is raised when ≥ {L.MIN_CHANNELS} gas channels exceed a robust z-score of {L.Z_THRESHOLD} for 10 s.

{_md(lr[['experiment', 'source', 'detector_min', 'aeroguard_min', 'lead_min', 'warned_before_detector', 'false_warning_in_stage0', 'first_channel']])}

`clothing_2` is excluded from the scores: its conventional detector switched on at 0.3 min, inside the
calibration window.

![lead time](lead_time.png)

Sensitivity to the threshold (shows the result does not depend on one lucky setting):

{_md(l['sensitivity'])}

## 3. Compressor early warning on 4 real failures (MetroPT-3)

Trained only on February–March 2020 (no failure reported). 30-minute windows; features: duty cycle,
starts, longest run, oil temperature, **physics residual** (measured minus energy-balance prediction), current,
pressures. Alarm = score above the 99.5th percentile of training scores for 1 h. An alarm up to 48 h before a
reported failure counts as an early warning.

{_md(comp)}

{_md(comp_ev)}

Reading: the autoencoder detects all 4 failures and warns 36 h and 47.5 h ahead for two of them, at the cost of
about one false alarm per week. The 47.5 h warning is at the edge of the 48 h window and may partly be chance.
Isolation Forest raises fewer false alarms but only detects failures after they start.

## 4. Motor / pump anomalies (SKAB)

First 400 samples of each experiment = normal reference (SKAB convention). Thresholds tuned on the 16
`valve1` experiments, results on the 18 others.

{_md(m['table'])}

Reading: on this bench the autoencoder matches the classic k-sigma limits on F1 while detecting every anomaly and
raising fewer false alarms. The gain is modest; it is reported as such.

## Limitations

- The fire datasets are laboratory and test-hall experiments, not a Tunisian factory. Real deployment needs a
  calibration period on site.
- Welding and abrasive cutting have one recording each; more nuisance data would make the zone model more robust.
- MetroPT-3 has only 4 reported failures: the lead times are evidence, not statistics.
- The Protection Civile incident data, once received, will be used to validate the risk engine's priorities.
"""
    (REPORTS / "evaluation.md").write_text(text, encoding="utf-8")


def main(fast: bool = False) -> None:
    warnings.filterwarnings("ignore")
    z = zone(fast); print("zone done", z["chosen"])
    l = lead(); print("early warning done", l["metrics"])
    c = compressor(); print("compressor done", {k: v[0] for k, v in c["models"].items()})
    m = motor(); print("motor done")
    figures(z, l, c)
    write_report(z, l, c, m)
    print("report:", REPORTS / "evaluation.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    main(ap.parse_args().fast)
