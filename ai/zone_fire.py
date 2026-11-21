"""Zone model: is it a real fire, an industrial nuisance (welding, cutting, exhaust...), or normal?

Data: Indoor Fire Dataset, Industrial Hall (real, 9 sensor nodes, 10 s sampling).
Model: gradient-boosted trees on features computed relative to each node's recent background.
Evaluation: leave-one-event-out. Every fire or nuisance recording is predicted by a model that
never saw it, so single recordings (welding, abrasive cutting) are tested as *unseen* sources.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from ai.common import persistent

CHANNELS = ["co_ppm", "co2_ppm", "h2_raw", "voc_raw", "pm05", "pm10", "pm25", "pm_total",
            "pm_typical_size_um", "temperature_c", "humidity_pct"]
CLASSES = np.array(["normal", "nuisance", "fire"])
CONFIRM = 3              # 3 consecutive predictions = 30 s
BASELINE = "15min"       # background reference window
BASELINE_GAP = "3min"    # reference ends 3 min before "now" so a starting event does not hide itself
POST_EVENT = "70min"     # unventilated hall: smoke lingers after an event
POST_WARMUP = "30min"    # sensor warm-up at the start of the recording


def node_features(node: pd.DataFrame) -> pd.DataFrame:
    """Features for one sensor node, time-ordered, using only past data (deployable in real time)."""
    d = node.set_index("timestamp")[CHANNELS].astype(float)
    base = d.shift(freq=BASELINE_GAP).rolling(BASELINE, min_periods=10).median().reindex(d.index, method="ffill")
    spread = (d.rolling(BASELINE, min_periods=10).std().shift(1)).clip(lower=1e-3)
    feats = {}
    for c in CHANNELS:
        delta = d[c] - base[c]
        feats[f"{c}_delta"] = delta
        feats[f"{c}_z"] = delta / spread[c]
        feats[f"{c}_slope60"] = d[c].diff(6) / 60.0
        feats[f"{c}_max60"] = delta.rolling(6, min_periods=1).max()
    eps = 1e-3
    feats["co_per_particle"] = feats["co_ppm_delta"] / (feats["pm_total_delta"].abs() + 1)
    feats["voc_per_particle"] = feats["voc_raw_delta"] / (feats["pm_total_delta"].abs() + 1)
    feats["fine_fraction"] = d["pm05"] / (d["pm_total"] + eps)
    feats["co2_per_co"] = feats["co2_ppm_delta"] / (feats["co_ppm_delta"].abs() + 0.05)
    out = pd.DataFrame(feats, index=d.index).replace([np.inf, -np.inf], np.nan)
    return out.reset_index()


def build_table(hall: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sid, node in hall.groupby("sensor_id"):
        f = node_features(node)
        meta = node[["timestamp", "scenario", "experiment", "is_fire", "is_anomaly"]].reset_index(drop=True)
        rows.append(pd.concat([meta, f.drop(columns="timestamp")], axis=1).assign(sensor_id=sid))
    t = pd.concat(rows, ignore_index=True)
    t["label"] = np.where(~t["is_anomaly"], "normal", np.where(t["is_fire"], "fire", "nuisance"))
    t["event"] = np.where(t["scenario"] == "Background", "",
                          t["scenario"] + "#" + t["experiment"].fillna(-1).astype(int).astype(str))
    return t


def feature_columns(t: pd.DataFrame) -> list[str]:
    return [c for c in t.columns if c.endswith(("_delta", "_z", "_slope60", "_max60"))
            or c in ("co_per_particle", "voc_per_particle", "fine_fraction", "co2_per_co")]


def make_model(seed: int = 0) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08, max_leaf_nodes=31,
                                          l2_regularization=1.0, class_weight="balanced", random_state=seed)


def _training_rows(t: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    normal = t[t["label"] == "normal"]
    keep = rng.random(len(normal)) < 0.1          # background is 83 % of rows; subsample it
    return pd.concat([normal[keep], t[t["label"] != "normal"]])


def node_alarms(group: pd.DataFrame, p_fire: float, k: int = CONFIRM) -> pd.DataFrame:
    """Per node: confirmed fire alarm when P(fire) >= p_fire for k consecutive samples."""
    out = []
    for sid, node in group.sort_values("timestamp").groupby("sensor_id"):
        out.append(pd.DataFrame({"timestamp": node["timestamp"].to_numpy(), "sensor_id": sid,
                                 "alarm": persistent(node["p_fire"].to_numpy() >= p_fire, k)}))
    return pd.concat(out)


def zone_alarm_times(group: pd.DataFrame, p_fire: float, min_nodes: int, k: int = CONFIRM) -> pd.Series:
    """Coincidence ("double-knock") rule: the zone alarms when at least `min_nodes` nodes are in
    confirmed alarm within the same 30 s bucket. Returns the sorted alarm bucket times."""
    a = node_alarms(group, p_fire, k)
    a = a[a["alarm"]]
    if a.empty:
        return pd.Series([], dtype="datetime64[ns, UTC]")
    bucket = a["timestamp"].dt.floor("30s")
    n = a.groupby(bucket)["sensor_id"].nunique()
    return pd.Series(n.index[n >= min_nodes])


def out_of_fold_probabilities(t: pd.DataFrame, n_bg_blocks: int = 5, seed: int = 0, log=print) -> pd.DataFrame:
    """P(fire) for every row from a model that never saw that row's event (leave-one-event-out),
    and for background rows from a model that never saw that time block."""
    rng = np.random.default_rng(seed)
    cols = feature_columns(t)
    p = pd.Series(np.nan, index=t.index)
    events = sorted(e for e in t["event"].unique() if e)
    for i, ev in enumerate(events, 1):
        test = t[t["event"] == ev]
        train = _training_rows(t[t["event"] != ev], rng)
        model = make_model(seed).fit(train[cols], train["label"])
        p.loc[test.index] = model.predict_proba(test[cols])[:, list(model.classes_).index("fire")]
        log(f"  event {i}/{len(events)} {ev}")
    bg = t[t["event"] == ""]
    edges = np.quantile(bg["timestamp"].astype("int64"), np.linspace(0, 1, n_bg_blocks + 1))
    for i in range(n_bg_blocks):
        block = bg[bg["timestamp"].astype("int64").between(edges[i], edges[i + 1])]
        train = _training_rows(t.drop(block.index), rng)
        model = make_model(seed).fit(train[cols], train["label"])
        p.loc[block.index] = model.predict_proba(block[cols])[:, list(model.classes_).index("fire")]
        log(f"  background block {i + 1}/{n_bg_blocks}")
    return t[["timestamp", "sensor_id", "event", "scenario", "label"]].assign(p_fire=p)


def evaluate_rule(oof: pd.DataFrame, p_fire: float, min_nodes: int) -> tuple[pd.DataFrame, dict]:
    """Event-level and background outcomes of one decision rule on out-of-fold probabilities."""
    rows = []
    for ev, g in oof[oof["event"] != ""].groupby("event"):
        if g["timestamp"].nunique() < 6:
            continue
        times = zone_alarm_times(g, p_fire, min_nodes)
        start = g["timestamp"].min()
        rows.append({"event": ev, "scenario": g["scenario"].iloc[0], "truth": g["label"].iloc[0],
                     "fire_alarm": len(times) > 0,
                     "time_to_alarm_s": (times.iloc[0] - start).total_seconds() if len(times) else np.nan})
    res = pd.DataFrame(rows)
    bg = oof[oof["event"] == ""]
    times = zone_alarm_times(bg, p_fire, min_nodes)
    episodes = times[(times.diff() > pd.Timedelta("10min")) | (np.arange(len(times)) == 0)]
    # Classify background alarm episodes: sensor warm-up (first 30 min of the recording),
    # post-event (smoke still lingering: the hall is unventilated), or truly quiet background.
    ends = oof[oof["event"] != ""].groupby("event")["timestamp"].max().sort_values()
    rec_start = bg["timestamp"].min()
    kinds = []
    for t0 in episodes:
        prev = ends[ends <= t0]
        if t0 - rec_start <= pd.Timedelta(POST_WARMUP):
            kinds.append("warm-up")
        elif len(prev) and t0 - prev.iloc[-1] <= pd.Timedelta(POST_EVENT):
            kinds.append("post-event")
        else:
            kinds.append("quiet")
    kinds = pd.Series(kinds, dtype=object)
    hours = bg.groupby("sensor_id")["timestamp"].count().mean() * 10 / 3600
    s = summarize(res)
    s.update({"background_hours": round(hours, 1), "background_false_alarm_episodes": len(episodes),
              "bg_alarms_warmup": int((kinds == "warm-up").sum()),
              "bg_alarms_post_event": int((kinds == "post-event").sum()),
              "bg_alarms_quiet": int((kinds == "quiet").sum()),
              "p_fire": p_fire, "min_nodes": min_nodes})
    return res, s


def select_rule(per_rule: dict, exclude: str | None = None) -> tuple:
    """Criterion fixed in advance: detect every fire; then fewest nuisance alarms; then fewest
    background alarms (quiet + post-event); then fastest median alarm. `exclude` leaves one event out."""
    def key(rule):
        ev, s = per_rule[rule]
        ev = ev[ev["event"] != exclude]
        fires, nuis = ev[ev["truth"] == "fire"], ev[ev["truth"] == "nuisance"]
        missed = int((~fires["fire_alarm"]).sum())
        return (missed, int(nuis["fire_alarm"].sum()), s["bg_alarms_quiet"] + s["bg_alarms_post_event"],
                float(fires["time_to_alarm_s"].median()))
    return min(per_rule, key=key)


def nested_rule_evaluation(oof: pd.DataFrame, rules: list[tuple]) -> tuple[pd.DataFrame, dict]:
    """Honest estimate: for each event, choose the rule using only the OTHER events, then apply it
    to that event. Removes the optimism of picking the rule on the reported results."""
    per_rule = {r: evaluate_rule(oof, *r) for r in rules}
    events = per_rule[rules[0]][0]["event"].tolist()
    rows = []
    for ev in events:
        rule = select_rule(per_rule, exclude=ev)
        row = per_rule[rule][0].set_index("event").loc[ev].to_dict()
        rows.append({"event": ev, **row, "rule_p_fire": rule[0], "rule_min_nodes": rule[1]})
    res = pd.DataFrame(rows)
    chosen_counts = res.groupby(["rule_p_fire", "rule_min_nodes"]).size().to_dict()
    s = summarize(res)
    s["rules_selected"] = {f"p>={p}, nodes>={n}": int(c) for (p, n), c in chosen_counts.items()}
    return res, s


# ---------------------------------------------------------------- conventional baseline

def particle_threshold_baseline(t: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Single-sensor rule standing in for an optical smoke detector: particles above background
    by more than `threshold` for 30 s on any node -> fire alarm."""
    out = []
    for ev, test in t[t["event"] != ""].groupby("event"):
        if test["timestamp"].nunique() < 6:
            continue
        g = test[["timestamp", "sensor_id"]].assign(p_fire=(test["pm_total_delta"] > threshold).astype(float))
        times = zone_alarm_times(g, 0.5, min_nodes=1)
        out.append({"event": ev, "scenario": test["scenario"].iloc[0], "truth": test["label"].iloc[0],
                    "fire_alarm": len(times) > 0})
    return pd.DataFrame(out)


def summarize(res: pd.DataFrame) -> dict:
    fires, nuis = res[res["truth"] == "fire"], res[res["truth"] == "nuisance"]
    return {
        "fire_events": len(fires), "fires_detected": int(fires["fire_alarm"].sum()),
        "fire_detection_rate": round(fires["fire_alarm"].mean(), 3) if len(fires) else None,
        "nuisance_events": len(nuis), "nuisance_false_alarms": int(nuis["fire_alarm"].sum()),
        "nuisance_false_alarm_rate": round(nuis["fire_alarm"].mean(), 3) if len(nuis) else None,
        "median_time_to_alarm_s": float(fires["time_to_alarm_s"].median()) if "time_to_alarm_s" in fires and fires["fire_alarm"].any() else None,
    }
