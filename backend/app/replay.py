"""Historical replay of real Industrial Hall recordings with live model inference.

Honesty rules enforced here:
* The data is a **recording** (July 2023 test hall); the UI labels it "historical replay".
* Features are causal (only past readings); the model is called tick by tick on the rows at the
  replay cursor, so no future measurement can influence a decision.
* The model used for an event is the held-out model trained WITHOUT that event.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ai import registry
from ai import zone_fire as Z
from ai.holdout import DEMO_EVENTS, slug
from backend.app.risk import NodeTick, RiskConfig, RiskEngine

TICK_S = 10
PRE_ROLL = pd.Timedelta("20min")      # normal operation shown before the event
POST_ROLL = pd.Timedelta("90min")     # recovery after the event (used for stabilization)
CHART_CHANNELS = ["co_ppm", "co2_ppm", "voc_raw", "pm_total", "temperature_c", "humidity_pct"]
UNITS = {"co_ppm": "ppm", "co2_ppm": "ppm", "voc_raw": "raw", "pm_total": "count", "temperature_c": "°C",
         "humidity_pct": "%", "h2_raw": "raw", "pm05": "count", "pm10": "count", "pm25": "count"}
SPEEDS = [1, 10, 30, 60, 120]


def held_mask(df: pd.DataFrame, repeats: int = 3) -> pd.Series:
    """True where a node's reading is identical (all channels) to its previous `repeats - 1` readings."""
    from ingest.loaders.fire_sensors import HALL_FEATURES
    d = df.sort_values(["sensor_id", "timestamp"])
    same = d.groupby("sensor_id")[HALL_FEATURES].diff().abs().sum(axis=1).eq(0)
    run = same.groupby([d["sensor_id"], (~same).cumsum()]).cumsum()
    return (run >= repeats - 1).reindex(df.index)


class HallData:
    """Loads the real hall recording once and precomputes causal features per node."""

    def __init__(self):
        from ingest.loaders.fire_sensors import load_industrial_hall
        self.hall = load_industrial_hall()
        self.table = Z.build_table(self.hall)
        self.table["event"] = self.table["event"].where(~self.table["event"].str.endswith("#-1"), "")
        self.table["t10"] = self.table["timestamp"].dt.floor(f"{TICK_S}s")
        self.raw = self.hall.assign(t10=self.hall["timestamp"].dt.floor(f"{TICK_S}s"))
        # Data-quality: after most experiments the recording repeats the last values for 20-45 min
        # (all 13 channels identical every 10 s). Such rows are held values, not measurements.
        self.raw["held"] = held_mask(self.raw)
        self.table = self.table.merge(self.raw[["sensor_id", "timestamp", "held"]], on=["sensor_id", "timestamp"], how="left")
        self.table["held"] = self.table["held"].fillna(False).astype(bool)
        ev = self.table[self.table["event"] != ""].groupby("event").agg(
            start=("timestamp", "min"), end=("timestamp", "max"), scenario=("scenario", "first"),
            truth=("label", "first"))
        self.events = ev

    def catalog(self) -> list[dict]:
        out = []
        for e in DEMO_EVENTS:
            r = self.events.loc[e]
            out.append({"id": e, "scenario": r["scenario"], "truth": r["truth"],
                        "start": r["start"].isoformat(), "end": r["end"].isoformat(),
                        "duration_min": round((r["end"] - r["start"]).total_seconds() / 60, 1),
                        "model": f"zone_fire_holdout/{slug(e)}",
                        "description": {
                            "Cable#4": "Cable fire (electrical) — real incipient fire",
                            "Wood#1": "Smouldering wood fire — real incipient fire",
                            "Welding#1": "Welding (hot work) — routine nuisance, no fire",
                            "Exhaust#1": "Vehicle exhaust — routine nuisance, no fire"}.get(e, e)})
        return out


@dataclass
class ReplayState:
    event_id: str | None = None
    window_start: pd.Timestamp | None = None
    window_end: pd.Timestamp | None = None
    cursor: pd.Timestamp | None = None
    running: bool = False
    speed: int = 30
    finished: bool = False
    ticks: list = field(default_factory=list)          # per-tick summary history (for charts / stabilization)
    latest: dict = field(default_factory=dict)


class ReplayEngine:
    def __init__(self, data: HallData, on_tick=None, risk_config: RiskConfig | None = None):
        self.data = data
        self.on_tick = on_tick                       # callback(tick_record, decision, engine)
        self.risk = RiskEngine(risk_config or RiskConfig())
        self.state = ReplayState()
        self._lock = threading.RLock()
        self._model = None
        self._features = None
        self._card = None
        self._window = None
        self._times = []
        self._idx = 0
        self._nodes = {}
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ control
    def load(self, event_id: str) -> dict:
        if event_id not in DEMO_EVENTS:
            raise KeyError(f"unknown demo event {event_id!r}")
        bundle, card = registry.load("zone_fire_holdout", slug(event_id))
        if bundle["excluded_event"] != event_id:
            raise RuntimeError("held-out model does not match the event")
        ev = self.data.events.loc[event_id]
        start, end = ev["start"] - PRE_ROLL, ev["end"] + POST_ROLL
        # never run into the next or previous experiment: stop 1 min before the next one starts
        later = self.data.events.loc[self.data.events["start"] > ev["end"], "start"]
        if len(later):
            end = min(end, later.min() - pd.Timedelta("1min"))
        earlier = self.data.events.loc[self.data.events["end"] < ev["start"], "end"]
        if len(earlier):
            start = max(start, earlier.max() + pd.Timedelta("1min"))
        with self._lock:
            self._model, self._features, self._card = bundle["model"], bundle["features"], card
            w = self.data.table[(self.data.table["timestamp"] >= start) & (self.data.table["timestamp"] <= end)]
            self._window = w
            self._raw = self.data.raw[(self.data.raw["timestamp"] >= start) & (self.data.raw["timestamp"] <= end)]
            self._times = sorted(w["t10"].unique())
            self._idx = 0
            self._nodes = {}
            cfg = card["config"]
            self.risk.config.p_fire, self.risk.config.min_nodes = cfg["p_fire"], cfg["min_nodes"]
            self.risk.reset()
            self.state = ReplayState(event_id=event_id, window_start=start, window_end=end,
                                     cursor=None, running=False, speed=self.state.speed)
        return {"event_id": event_id, "ticks": len(self._times), "model": card["name"] + "/" + card["version"],
                "model_sha256": card["model_sha256"]}

    def play(self):
        with self._lock:
            if self._window is None:
                raise RuntimeError("load an event first")
            self.state.running = not self.state.finished

    def pause(self):
        with self._lock:
            self.state.running = False

    def set_speed(self, speed: int):
        if speed not in SPEEDS:
            raise ValueError(f"speed must be one of {SPEEDS}")
        with self._lock:
            self.state.speed = speed

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            if not self._advance():
                break

    # ------------------------------------------------------------------ core
    def _loop(self):
        while True:
            with self._lock:
                running, speed = self.state.running, self.state.speed
            if running:
                self._advance()
                time.sleep(TICK_S / speed)
            else:
                time.sleep(0.05)

    def _advance(self) -> bool:
        with self._lock:
            if self._window is None or self._idx >= len(self._times):
                self.state.running = False
                self.state.finished = self._window is not None
                return False
            t = self._times[self._idx]
            self._idx += 1
            at_t = self._window[self._window["t10"] == t]
            rows = at_t[~at_t["held"]]                     # only live measurements are analysed
            held_nodes = int(at_t["held"].sum())
            raw = self._raw[self._raw["t10"] == t]
            fresh = {}
            if len(rows):
                proba = self._model.predict_proba(rows[self._features])   # only the rows at the cursor
                classes = list(self._model.classes_)
                for i, sid in enumerate(rows["sensor_id"]):
                    rr = raw[raw["sensor_id"] == sid]
                    readings = {c: float(rr[c].iloc[0]) for c in UNITS if len(rr) and c in rr}
                    fresh[sid] = {"p_fire": float(proba[i, classes.index("fire")]),
                                  "p_nuisance": float(proba[i, classes.index("nuisance")]),
                                  "readings": readings, "last_seen": t}
            # nodes without a reading at this tick keep their last state; the risk engine sees their age
            self._nodes.update(fresh)
            ticks = []
            for nid, n in sorted(self._nodes.items()):
                age = (t - n["last_seen"]).total_seconds()
                ticks.append(NodeTick(nid, n["p_fire"] if age <= self.risk.config.stale_after_s else None,
                                      n["p_nuisance"], n["readings"] if nid in fresh else None, age))
            nodes = self._nodes
            decision = self.risk.evaluate(ticks)
            rec = {"t": t.isoformat(), "level": decision.level, "score": decision.score,
                   "max_p_fire": max((n["p_fire"] for n in fresh.values()), default=None),
                   "max_p_nuisance": max((n["p_nuisance"] for n in fresh.values()), default=None),
                   "mean": {c: (float(np.mean([n["readings"][c] for n in fresh.values() if c in n["readings"]]))
                                if fresh else None) for c in CHART_CHANNELS},
                   "fire_nodes": decision.fire_nodes, "fresh_nodes": len(fresh), "held_nodes": held_nodes,
                   "nodes": {k: [round(v["p_fire"], 4), round(v["p_nuisance"], 4)] for k, v in fresh.items()},
                   "healthy_nodes": decision.healthy_nodes}
            self.state.ticks.append(rec)
            self.state.cursor = t
            self.state.latest = {"nodes": {k: {**v, "last_seen": v["last_seen"].isoformat()} for k, v in nodes.items()},
                                 "decision": decision.__dict__, "t": t.isoformat()}
        if self.on_tick:
            self.on_tick(rec, decision, self)
        return True

    # ------------------------------------------------------------------ views
    def snapshot(self) -> dict:
        with self._lock:
            s = self.state
            total = len(self._times) or 1
            ev = self.data.events.loc[s.event_id] if s.event_id else None
            return {
                "event_id": s.event_id, "running": s.running, "speed": s.speed, "finished": s.finished,
                "cursor": s.cursor.isoformat() if s.cursor is not None else None,
                "window_start": s.window_start.isoformat() if s.window_start is not None else None,
                "window_end": s.window_end.isoformat() if s.window_end is not None else None,
                "event_start": ev["start"].isoformat() if ev is not None else None,
                "event_end": ev["end"].isoformat() if ev is not None else None,
                "progress": round(self._idx / total, 4),
                "model": (self._card["name"] + "/" + self._card["version"]) if self._card else None,
                "latest": s.latest, "units": UNITS,
            }

    def series(self, since: int = 0) -> dict:
        with self._lock:
            return {"from": since, "ticks": self.state.ticks[since:]}

    def node_history(self, node_id: str) -> dict:
        """Readings and model outputs of one node up to the replay cursor (never beyond it)."""
        with self._lock:
            if self._window is None or self.state.cursor is None:
                return {"node_id": node_id, "points": []}
            raw = self._raw[(self._raw["sensor_id"] == node_id) & (self._raw["t10"] <= self.state.cursor)]
            probs = {r["t"]: r["nodes"].get(node_id) for r in self.state.ticks if node_id in r.get("nodes", {})}
            pts = []
            for _, r in raw.iterrows():
                t = r["t10"].isoformat()
                pr = probs.get(t)
                pts.append({"t": t, **{c: float(r[c]) for c in UNITS},
                            "p_fire": pr[0] if pr else None, "p_nuisance": pr[1] if pr else None})
            return {"node_id": node_id, "units": UNITS, "points": pts}

    def recent_ticks(self, seconds: float) -> list[dict]:
        with self._lock:
            if not self.state.ticks:
                return []
            end = pd.Timestamp(self.state.ticks[-1]["t"])
            return [r for r in self.state.ticks if (end - pd.Timestamp(r["t"])).total_seconds() <= seconds]
