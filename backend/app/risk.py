"""Explainable risk engine for one monitored zone.

Input: per-node model outputs (P(fire), P(nuisance)) and sensor health, one tick at a time.
Output: a risk level with human-readable reasons. Levels are operational categories, NOT
calibrated fire probabilities. Certified fire alarms remain independent of this engine.

Rules (configurable):
  CRITICAL  >= min_nodes healthy nodes in confirmed fire state (coincidence, as in double-knock)
  HIGH      exactly 1 node in confirmed fire state
  WATCH     abnormal air composition the model attributes mainly to a process nuisance,
            or a fire signal that is not yet persistent
  NORMAL    otherwise
A node is in "confirmed fire" state when P(fire) >= p_fire for `confirm` consecutive ticks.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

LEVELS = ["NO_DATA", "NORMAL", "WATCH", "HIGH", "CRITICAL"]


@dataclass
class RiskConfig:
    p_fire: float = 0.95
    min_nodes: int = 2
    confirm: int = 3                 # ticks (10 s each) -> 30 s
    p_watch: float = 0.5             # fire OR nuisance probability above this = abnormal air
    stale_after_s: float = 60.0      # node silent longer than this = unhealthy
    frozen_ticks: int = 0            # >0 flags identical readings over N ticks; off: a quiet hall really is flat
    zone_criticality: int = 4        # 1..5, scales the score shown to operators


@dataclass
class NodeTick:
    node_id: str
    p_fire: float | None             # None when the node has no data at this tick
    p_nuisance: float | None
    readings: dict | None = None
    seconds_since_data: float = 0.0


@dataclass
class RiskDecision:
    level: str
    score: float                     # 0-100 operational priority, not a probability
    reasons: list[str]
    fire_nodes: list[str]
    watch_nodes: list[str]
    unhealthy_nodes: list[str]
    healthy_nodes: int


@dataclass
class RiskEngine:
    config: RiskConfig = field(default_factory=RiskConfig)

    def __post_init__(self):
        self.reset()

    def reset(self) -> None:
        self._fire_run = defaultdict(int)
        self._watch_run = defaultdict(int)
        self._history = defaultdict(lambda: deque(maxlen=max(1, self.config.frozen_ticks)))

    def _health(self, t: NodeTick) -> tuple[bool, str | None]:
        if t.p_fire is None or t.seconds_since_data > self.config.stale_after_s:
            return False, f"{t.node_id}: no data for {int(t.seconds_since_data)} s"
        if t.readings and self.config.frozen_ticks > 0:
            h = self._history[t.node_id]
            h.append(tuple(sorted(t.readings.items())))
            if len(h) == h.maxlen and len(set(h)) == 1:
                return False, f"{t.node_id}: readings frozen for {h.maxlen * 10 // 60} min (suspect sensor)"
        return True, None

    def evaluate(self, ticks: list[NodeTick]) -> RiskDecision:
        c = self.config
        reasons, fire_nodes, watch_nodes, unhealthy = [], [], [], []
        for t in ticks:
            ok, why = self._health(t)
            if not ok:
                unhealthy.append(t.node_id)
                reasons.append(why)
                self._fire_run[t.node_id] = 0
                self._watch_run[t.node_id] = 0
                continue
            self._fire_run[t.node_id] = self._fire_run[t.node_id] + 1 if t.p_fire >= c.p_fire else 0
            abnormal = max(t.p_fire, t.p_nuisance) >= c.p_watch
            self._watch_run[t.node_id] = self._watch_run[t.node_id] + 1 if abnormal else 0
            if self._fire_run[t.node_id] >= c.confirm:
                fire_nodes.append(t.node_id)
            elif self._watch_run[t.node_id] >= c.confirm:
                watch_nodes.append(t.node_id)
        healthy = len(ticks) - len(unhealthy)

        if healthy == 0:
            return RiskDecision("NO_DATA", 0.0, ["No sensor node is reporting (data gap): the zone is NOT known to be safe"]
                                + reasons[:3], [], [], unhealthy, 0)
        if len(fire_nodes) >= c.min_nodes:
            level = "CRITICAL"
            reasons.insert(0, f"{len(fire_nodes)} sensor nodes agree on a fire signature "
                              f"(P(fire) ≥ {c.p_fire} for {c.confirm * 10} s): coincidence rule met")
        elif fire_nodes:
            level = "HIGH"
            reasons.insert(0, f"1 sensor node ({fire_nodes[0]}) shows a persistent fire signature; "
                              f"waiting for a second node to confirm (coincidence rule)")
        elif watch_nodes:
            level = "WATCH"
            best = max((t for t in ticks if t.node_id in watch_nodes), key=lambda t: t.p_nuisance or 0)
            if (best.p_nuisance or 0) >= (best.p_fire or 0):
                reasons.insert(0, f"Abnormal air on {len(watch_nodes)} node(s); the model attributes it to a "
                                  f"process nuisance (e.g. welding, cutting, exhaust), not to a fire")
            else:
                reasons.insert(0, f"Abnormal air on {len(watch_nodes)} node(s) with a rising fire signal, "
                                  f"not yet persistent")
        else:
            level = "NORMAL"
            reasons.insert(0, "All healthy nodes within their normal signature")
        if healthy < c.min_nodes:
            reasons.append(f"Only {healthy} healthy node(s): the coincidence rule cannot be satisfied")

        base = {"NORMAL": 0, "WATCH": 30, "HIGH": 60, "CRITICAL": 85}[level]
        score = min(100.0, base + (c.zone_criticality - 3) * 5 + 2 * max(0, len(fire_nodes) - 1))
        return RiskDecision(level, max(0.0, score), reasons, fire_nodes, watch_nodes, unhealthy, healthy)
