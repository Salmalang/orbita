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
    nested_events, nested = Z.nested_rule_evaluation(oof, ZONE_RULES)
    baseline, base_summary, _ = Z.particle_baseline(table)
    # final model on all data
    cols = Z.feature_columns(table)
    train = Z._training_rows(table, np.random.default_rng(0))
    model = Z.make_model().fit(train[cols], train["label"])
    card = registry.save("zone_fire", VERSION, {"model": model, "features": cols}, metrics={
        "evaluation": "leave-one-event-out model + nested leave-one-event-out rule selection",
        "nested_estimate": nested, "chosen_rule_in_sample_optimistic": chosen,
        "particle_threshold_baseline": base_summary},
        config={"p_fire": ZONE_DEFAULT[0], "min_nodes": ZONE_DEFAULT[1], "confirm_samples": Z.CONFIRM,
                "baseline_window": Z.BASELINE, "baseline_gap": Z.BASELINE_GAP},
        datasets=["industrial_hall_fire"],
        description="Real fire vs industrial nuisance vs normal, per zone, with 2-node coincidence.")
    return {"grid": grid, "events": events, "chosen": chosen, "baseline": base_summary,
            "baseline_events": baseline, "card": card, "nested": nested, "nested_events": nested_events}


def wilson(k: int, n: int, z: float = 1.96) -> str:
    """95 % Wilson score interval, to show how uncertain small-sample rates are."""
    if n == 0:
        return "n/a"
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return f"{k}/{n} = {p:.0%} (95% CI {max(0, c - h):.0%}–{min(1, c + h):.0%})"


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
    ev, base = z["nested_events"], z["baseline_events"]
    labels = ["Fires detected", "Nuisances raising a fire alarm"]
    ai_vals = [ev.loc[ev.truth == "fire", "fire_alarm"].mean(), ev.loc[ev.truth == "nuisance", "fire_alarm"].mean()]
    b_vals = [base.loc[base.truth == "fire", "fire_alarm"].mean(), base.loc[base.truth == "nuisance", "fire_alarm"].mean()]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    x = np.arange(2)
    ax.bar(x - 0.2, b_vals, 0.4, label="calibrated particle threshold (nested)", color="#868e96")
    ax.bar(x + 0.2, ai_vals, 0.4, label="AEROGUARD zone model (nested)", color="#1971c2")
    for xi, v in zip(x - 0.2, b_vals): ax.text(xi, v + 0.02, f"{v:.0%}", ha="center", fontsize=8)
    for xi, v in zip(x + 0.2, ai_vals): ax.text(xi, v + 0.02, f"{v:.0%}", ha="center", fontsize=8)
    ax.set_xticks(x, labels); ax.set_ylim(0, 1.15); ax.legend(fontsize=8)
    ax.set_title("Industrial hall, held-out events: AI model vs calibrated particle threshold")
    fig.text(0.99, 0.01, "Source: Indoor Fire Dataset, Industrial Hall, doi:10.17632/yghykzm4km.1", ha="right", fontsize=7, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(REPORTS / "zone_fire_vs_nuisance.png", dpi=130); plt.close(fig)


def write_report(z, l, c, m) -> None:
    ch, b, nz = z["chosen"], z["baseline"], z["nested"]
    ne = z["nested_events"][["event", "truth", "fire_alarm", "time_to_alarm_s", "rule_p_fire", "rule_min_nodes"]]
    lm = l["metrics"]
    ae = c["models"]["Autoencoder"][0]
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
Provenance and data-quality findings: [docs/DATA_PROVENANCE_AUDIT.md](../../docs/DATA_PROVENANCE_AUDIT.md).

## Status of each claim

| Claim | Evidence | Status |
|---|---|---|
| 1. **Fire detection** in an industrial hall, telling fires from nuisances | Industrial Hall, leave-one-event-out + nested rule selection | **Held-out estimate** (small sample, wide intervals) |
| 2. **Earlier than a conventional detector** | Indoor Laboratory fires, rule fixed in advance | **Held-out by construction** (no training), 7 fires; laboratory, not a factory |
| 3. **Equipment anomaly / failure detection** | MetroPT-3 compressor (4 failures), SKAB motor bench | **Exploratory** for the compressor (model choice made after seeing the 4 failures); held-out tuning split for SKAB |
| 4. **Prevention of industrial fires** | None | **Not demonstrated.** No dataset links detected anomalies to fires that were then avoided |

## 1. Zone model: real fire or industrial nuisance? (primary MVP model)

Gradient-boosted trees on features relative to each sensor node's recent background (CO, CO₂, H₂, VOC,
particles by size, temperature, humidity). **Leave-one-event-out**: each of the {len(ev)} recordings is judged by
a model that never saw it. Welding and abrasive cutting have a single recording each, so they are tested as
**completely unseen** sources.

Decision rule: **coincidence detection** (as in "double-knock" fire systems): the zone alarms when at least
N sensor nodes are confident (P(fire) ≥ p) for 30 s. The pair (p, N) is chosen by a criterion fixed in advance
(detect every fire, then fewest nuisance alarms, then fewest background alarms, then fastest).

**Honest estimate (nested):** for each event, (p, N) is chosen using only the *other* events, then applied to it.

| Result | AEROGUARD, nested (headline) | AEROGUARD, rule p≥{ZONE_DEFAULT[0]}, N≥{ZONE_DEFAULT[1]} chosen on all events (optimistic) | Calibrated particle threshold, nested |
|---|---|---|---|
| Real fires detected | {wilson(nz['fires_detected'], nz['fire_events'])} | {ch['fires_detected']}/{ch['fire_events']} | {wilson(b['fires_detected'], b['fire_events'])} |
| Nuisances raising a fire alarm | {wilson(nz['nuisance_false_alarms'], nz['nuisance_events'])} | {ch['nuisance_false_alarms']}/{ch['nuisance_events']} | {wilson(b['nuisance_false_alarms'], b['nuisance_events'])} |
| Median time from event start to alarm | {nz['median_time_to_alarm_s']} s | {ch['median_time_to_alarm_s']} s | {b['median_time_to_alarm_s']} s |
| Background alarm episodes | see below | {ch['background_false_alarm_episodes']} | {b['background_false_alarm_episodes']} |

**Key finding:** a particle threshold calibrated with the same nested protocol performs **as well as or better than** the
AI model on fire detection, nuisance rejection and background alarms on this dataset. The AI model alarms earlier
(median), but its nuisance rejection advantage is not demonstrated against a well-calibrated simple rule.

Rules selected across the nested folds: {nz['rules_selected']}. The event missed in the nested estimate is the
one for which leaving it out makes the stricter rule look best.

Background (rule p≥{ZONE_DEFAULT[0]}, N≥{ZONE_DEFAULT[1]}), {ch['background_hours']} h of continuous recording including nights:
{ch['bg_alarms_quiet']} alarm(s) in quiet periods, {ch['bg_alarms_post_event']} within 70 min after an event (smoke lingering,
unventilated hall), {ch['bg_alarms_warmup']} during sensor warm-up (first 30 min of the recording). The 70-minute
"post-event" window was defined **after** looking at where background alarms occur, so this split is descriptive.

Particle baseline: a node alarms when its particle count exceeds its background by more than a threshold
for 30 s; any node suffices. The threshold is chosen per held-out event from {Z.PARTICLE_GRID} with the same criterion
as the AI rule (selected: {b['thresholds_selected']}). It is a simplified stand-in for an optical smoke detector, not a
certified device. An earlier version of this report set the threshold from a stray single-row label and reported
15/15 nuisance alarms for this baseline; that was a bug and has been corrected.

Residual dependence: the out-of-fold probabilities of other events come from models that did see the held-out
event, so the nested rule choice is not perfectly independent. With 32 events this is the best available split.

**Remaining nuisance alarms**: ethanol, the two fog-machine "smoke" runs and welding. Welding is a single
recording, so here the model had **never seen welding** during training. On a real site, welding recordings
from that site and the platform's hot-work permits (declared welding zones and times) would be used.

![zone](zone_fire_vs_nuisance.png)

All rules tested (trade-off between catching fires and ignoring nuisances):

{_md(grid)}

Per event (nested estimate; rule chosen without that event):

{_md(ne)}

## 2. Early warning vs the conventional smoke detector

Unsupervised, no training: each recording's first {L.CALIBRATION_S} s define normal; a warning
is raised when ≥ {L.MIN_CHANNELS} channels exceed a robust z-score of {L.Z_THRESHOLD} for {L.CONFIRM} consecutive readings
(5 s for the 1 Hz files, 10 s for `electrical_1` and `electrical_2`, which are sampled every 2 s).
The threshold, channel count and noise floors were set before the per-experiment results were computed;
the sensitivity table below shows other settings.

Headline: warned before the conventional detector in {wilson(lm['warned_before_detector'], lm['experiments_scored'])};
electrical fires: {lm['electrical_lead_time_min']} minutes earlier. "Stage 0" (authors' no-fire label) is short in most
recordings, so the false-warning check covers little time; it is not a false-alarm rate.

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

Reading (**exploratory**): the autoencoder detects {ae['detected']}/4 failures and alarms before the reported start for
{ae['detected_before_start']} of them, at about {ae['false_alarms_per_week']} false alarm episodes per week of normal operation. The 47.5 h
warning is at the edge of the 48 h window and may be a coincidental alarm. Isolation Forest raises fewer false alarms
but alarms only after failures start. Both models are shown because the choice between them was made after seeing
the 4 failures. This is a railway compressor, used here as evidence for the method, not as factory data.

## 4. Motor / pump anomalies (SKAB, laboratory bench)

First 400 samples of each experiment = normal reference (SKAB convention). Experiments whose first 400 samples
already contain labelled anomalies are excluded (`other/2`). Thresholds tuned on the `valve1` experiments,
results on the others. F1 is point-wise; about 35 % of test points are anomalous, which favours permissive
methods, so the false-alarm rate is shown next to it.

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
