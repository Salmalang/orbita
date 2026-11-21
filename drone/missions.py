"""Drone mission management (SIMULATED: no physical drone is connected).

Two inspection modes share one mission model:
  * PREVENTIVE  - scheduled or manually started patrols over predefined routes, before any alert;
  * TARGETED    - requested by the risk engine for the zone of an alert; needs operator approval.
A follow-up mission (FOLLOW_UP) re-inspects a checkpoint to confirm a corrective action.

Movement is simulated in wall-clock time along the route. Findings are recorded by the operator and
are always labelled "illustrative": there is no computer-vision or thermal model behind them.
The scheduler is simulated too: it only runs while the AEROGUARD server process is running.
"""
from __future__ import annotations

import itertools
import math
import threading
import time
from datetime import datetime, timedelta, timezone

LEG_SECONDS = 3.0           # simulated flight time between two checkpoints (demo speed)
DWELL_SECONDS = 2.0         # simulated inspection time at each checkpoint
FINDING_TYPES = {
    "overheating_suspected": "Suspected overheating (visual signs)",
    "visible_smoke": "Visible smoke or haze",
    "obstructed_exit": "Obstructed emergency exit",
    "visible_damage": "Visible equipment or cable damage",
    "combustibles_near_hot_work": "Combustible material near hot-work area",
    "other": "Other safety concern",
}
SEVERITIES = ["LOW", "MEDIUM", "HIGH"]
ACTIVE = ("AWAITING_APPROVAL", "PLANNED", "IN_FLIGHT", "PAUSED")


class MissionError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


class MissionManager:
    def __init__(self, store, facility: dict, on_event=None, clock=_now, autostart: bool = True):
        self.store = store
        self.facility = facility
        self.cp = {c["id"]: c for c in facility["checkpoints"]}
        self.routes = {r["id"]: r for r in facility["routes"]}
        self.dock = facility["drone_dock"]
        self.on_event = on_event or (lambda *a, **k: None)
        self.clock = clock
        self._lock = threading.RLock()
        self._ids = {k: itertools.count(self._max_id(k) + 1) for k in ("mission", "finding", "schedule")}
        if not self.store.list_records("schedule"):
            self.create_schedule("R-FULL", every_minutes=60, start_in_minutes=60, enabled=True)
        if autostart:
            threading.Thread(target=self._loop, daemon=True).start()

    def _max_id(self, kind: str) -> int:
        return max((int(r["id"].split("-")[-1]) for r in self.store.list_records(kind)), default=0)

    def _next_id(self, kind: str, prefix: str) -> str:
        return f"{prefix}-{next(self._ids[kind]):04d}"

    def _log(self, kind: str, payload: dict, source: str = "simulated", actor=None, case_id=None):
        self.store.append(kind, source, payload, actor=actor, case_id=case_id)
        self.on_event(kind, payload)

    # ------------------------------------------------------------------ schedules (simulated scheduler)
    def create_schedule(self, route_id: str, every_minutes: int, start_in_minutes: int = 0, enabled: bool = True) -> dict:
        if route_id not in self.routes:
            raise MissionError(f"unknown route {route_id}")
        if not 1 <= every_minutes <= 24 * 60:
            raise MissionError("frequency must be between 1 minute and 24 hours")
        s = {"id": self._next_id("schedule", "PS"), "route_id": route_id, "every_minutes": every_minutes,
             "enabled": enabled, "next_due": _iso(self.clock() + timedelta(minutes=start_in_minutes)),
             "simulated": True}
        self.store.put_record("schedule", s)
        self._log("patrol_schedule_set", {"schedule": s["id"], "route": route_id, "every_minutes": every_minutes},
                  source="human", actor="operator")
        return s

    def update_schedule(self, sid: str, every_minutes: int | None = None, enabled: bool | None = None,
                        start_in_minutes: int | None = None) -> dict:
        s = self.store.get_record("schedule", sid)
        if not s:
            raise KeyError(sid)
        if every_minutes is not None:
            if not 1 <= every_minutes <= 24 * 60:
                raise MissionError("frequency must be between 1 minute and 24 hours")
            s["every_minutes"] = every_minutes
        if enabled is not None:
            s["enabled"] = enabled
        if start_in_minutes is not None:
            s["next_due"] = _iso(self.clock() + timedelta(minutes=start_in_minutes))
        self.store.put_record("schedule", s)
        self._log("patrol_schedule_set", {"schedule": sid, "every_minutes": s["every_minutes"], "enabled": s["enabled"]},
                  source="human", actor="operator")
        return s

    def schedules(self) -> list[dict]:
        return sorted(self.store.list_records("schedule"), key=lambda s: s["id"])

    def run_due_schedules(self) -> list[dict]:
        started = []
        now = self.clock()
        for s in self.schedules():
            if s["enabled"] and datetime.fromisoformat(s["next_due"]) <= now and not self.active_mission():
                started.append(self.create_mission("PREVENTIVE", s["route_id"], origin="SCHEDULED", schedule_id=s["id"]))
                due = datetime.fromisoformat(s["next_due"])
                while due <= now:
                    due += timedelta(minutes=s["every_minutes"])
                s["next_due"] = _iso(due)
                self.store.put_record("schedule", s)
        return started

    # ------------------------------------------------------------------ missions
    def _path(self, checkpoint_ids: list[str]) -> list[dict]:
        pts = [{"id": "DOCK", "label": self.dock["label"], "x": self.dock["x"], "y": self.dock["y"]}]
        pts += [{"id": c, "label": self.cp[c]["label"], "x": self.cp[c]["x"], "y": self.cp[c]["y"]} for c in checkpoint_ids]
        pts.append({"id": "DOCK", "label": self.dock["label"], "x": self.dock["x"], "y": self.dock["y"]})
        return pts

    def create_mission(self, mode: str, route_id: str | None = None, *, origin: str, checkpoints: list[str] | None = None,
                       case_id: str | None = None, schedule_id: str | None = None, reason: str = "") -> dict:
        if mode not in ("PREVENTIVE", "TARGETED", "FOLLOW_UP"):
            raise MissionError(f"unknown mode {mode}")
        with self._lock:
            if self.active_mission() and mode != "TARGETED":
                raise MissionError("another mission is active: cancel or finish it first")
            if route_id:
                if route_id not in self.routes:
                    raise MissionError(f"unknown route {route_id}")
                checkpoints = self.routes[route_id]["checkpoints"]
                label = self.routes[route_id]["label"]
            else:
                if not checkpoints or any(c not in self.cp for c in checkpoints):
                    raise MissionError("valid checkpoints are required")
                label = {"TARGETED": "Targeted inspection", "FOLLOW_UP": "Follow-up inspection"}.get(mode, "Inspection")
            m = {"id": self._next_id("mission", "M"), "mode": mode, "origin": origin, "route_id": route_id,
                 "label": label, "reason": reason, "checkpoints": [{"id": c, "label": self.cp[c]["label"], "status": "pending",
                                                                     "result": None} for c in checkpoints],
                 "path": self._path(checkpoints), "status": "AWAITING_APPROVAL" if mode == "TARGETED" else "IN_FLIGHT",
                 "case_id": case_id, "schedule_id": schedule_id, "created_at": _iso(self.clock()),
                 "started_at": None, "ended_at": None, "elapsed_s": 0.0, "position": {"x": self.dock["x"], "y": self.dock["y"]},
                 "leg": 0, "progress": 0.0, "findings": [], "simulated": True,
                 "note": "Simulated drone mission. No physical drone connected; no imagery or thermal data captured."}
            if m["status"] == "IN_FLIGHT":
                m["started_at"] = _iso(self.clock())
            self.store.put_record("mission", m)
        self._log("mission_created", {"mission": m["id"], "mode": mode, "origin": origin, "label": label,
                                      "checkpoints": checkpoints, "status": m["status"]}, case_id=case_id)
        return m

    def get(self, mid: str) -> dict:
        m = self.store.get_record("mission", mid)
        if not m:
            raise KeyError(mid)
        return m

    def missions(self) -> list[dict]:
        return sorted(self.store.list_records("mission"), key=lambda m: m["id"], reverse=True)

    def active_mission(self) -> dict | None:
        act = [m for m in self.store.list_records("mission") if m["status"] in ("IN_FLIGHT", "PAUSED")]
        return act[0] if act else None

    def control(self, mid: str, action: str, actor: str = "operator") -> dict:
        with self._lock:
            m = self.get(mid)
            transitions = {"approve": ("AWAITING_APPROVAL", "IN_FLIGHT"), "pause": ("IN_FLIGHT", "PAUSED"),
                           "resume": ("PAUSED", "IN_FLIGHT")}
            if action == "cancel":
                if m["status"] not in ACTIVE:
                    raise MissionError(f"cannot cancel a mission that is {m['status']}")
                m["status"], m["ended_at"] = "CANCELLED", _iso(self.clock())
            elif action in transitions:
                frm, to = transitions[action]
                if m["status"] != frm:
                    raise MissionError(f"cannot {action} a mission that is {m['status']}")
                if action in ("approve", "resume") and self.active_mission() and self.active_mission()["id"] != mid:
                    raise MissionError("another mission is in flight: pause or cancel it first")
                m["status"] = to
                if action == "approve":
                    m["started_at"] = _iso(self.clock())
            else:
                raise MissionError(f"unknown action {action}")
            self.store.put_record("mission", m)
        self._log(f"mission_{action}", {"mission": mid, "status": m["status"]}, source="human", actor=actor, case_id=m["case_id"])
        return m

    def tick(self, dt: float) -> None:
        """Advance every in-flight mission by dt seconds of simulated flight."""
        with self._lock:
            for m in self.store.list_records("mission"):
                if m["status"] != "IN_FLIGHT":
                    continue
                m["elapsed_s"] += dt
                legs = len(m["path"]) - 1
                per = LEG_SECONDS + DWELL_SECONDS
                leg = min(int(m["elapsed_s"] // per), legs)
                within = m["elapsed_s"] - leg * per
                if leg >= legs:
                    m["position"] = {"x": m["path"][-1]["x"], "y": m["path"][-1]["y"]}
                    m["status"], m["ended_at"], m["progress"], m["leg"] = "COMPLETED", _iso(self.clock()), 1.0, legs
                    for c in m["checkpoints"]:
                        if c["status"] != "inspected":
                            c["status"] = "inspected"
                    self.store.put_record("mission", m)
                    self._log("mission_completed", {"mission": m["id"], "findings": len(m["findings"])}, case_id=m["case_id"])
                    continue
                a, b = m["path"][leg], m["path"][leg + 1]
                f = min(1.0, within / LEG_SECONDS)
                m["position"] = {"x": a["x"] + (b["x"] - a["x"]) * f, "y": a["y"] + (b["y"] - a["y"]) * f}
                # checkpoint index i is reached at the end of leg i (path[i+1])
                for i, c in enumerate(m["checkpoints"]):
                    reached = leg > i or (leg == i and within >= LEG_SECONDS)
                    if reached and c["status"] == "pending":
                        c["status"] = "inspected"
                        self._log("checkpoint_inspected", {"mission": m["id"], "checkpoint": c["id"], "label": c["label"]},
                                  case_id=m["case_id"])
                m["leg"], m["progress"] = leg, round(m["elapsed_s"] / (legs * per), 4)
                m["current"] = b["label"] if f < 1 else f"Inspecting: {b['label']}"
                self.store.put_record("mission", m)

    def _loop(self):
        last = time.monotonic()
        while True:
            time.sleep(0.25)
            now = time.monotonic()
            try:
                self.tick(now - last)
                self.run_due_schedules()
            except Exception:       # never let the simulator thread die during a demo
                pass
            last = now

    # ------------------------------------------------------------------ findings
    def record_finding(self, mid: str, checkpoint_id: str, ftype: str, severity: str, note: str, actor: str = "operator") -> dict:
        if ftype not in FINDING_TYPES:
            raise MissionError(f"unknown finding type {ftype}")
        if severity not in SEVERITIES:
            raise MissionError(f"severity must be one of {SEVERITIES}")
        with self._lock:
            m = self.get(mid)
            cp = next((c for c in m["checkpoints"] if c["id"] == checkpoint_id), None)
            if not cp:
                raise MissionError("checkpoint is not part of this mission")
            if cp["status"] != "inspected":
                raise MissionError("the drone has not inspected this checkpoint yet")
            f = {"id": self._next_id("finding", "F"), "mission_id": mid, "mission_mode": m["mode"], "checkpoint": checkpoint_id,
                 "checkpoint_label": cp["label"], "type": ftype, "type_label": FINDING_TYPES[ftype], "severity": severity,
                 "note": note.strip(), "recorded_at": _iso(self.clock()), "recorded_by": actor,
                 "near_nodes": self.cp[checkpoint_id]["near_nodes"], "illustrative": True, "case_id": None,
                 "label": "Illustrative inspection finding (simulated mission, recorded by the operator; no validated detection model)"}
            cp["result"] = "finding"
            m["findings"].append(f["id"])
            self.store.put_record("finding", f)
            self.store.put_record("mission", m)
        self._log("inspection_finding", {"finding": f["id"], "mission": mid, "checkpoint": cp["label"], "type": f["type_label"],
                                         "severity": severity, "illustrative": True}, source="human", actor=actor,
                  case_id=m["case_id"])
        return f

    def mark_clear(self, mid: str, checkpoint_id: str, actor: str = "operator") -> dict:
        with self._lock:
            m = self.get(mid)
            cp = next((c for c in m["checkpoints"] if c["id"] == checkpoint_id), None)
            if not cp or cp["status"] != "inspected":
                raise MissionError("the drone has not inspected this checkpoint yet")
            cp["result"] = "clear"
            self.store.put_record("mission", m)
        self._log("checkpoint_clear", {"mission": mid, "checkpoint": cp["label"], "illustrative": True},
                  source="human", actor=actor, case_id=m["case_id"])
        return m

    def findings(self) -> list[dict]:
        return sorted(self.store.list_records("finding"), key=lambda f: f["id"], reverse=True)

    def get_finding(self, fid: str) -> dict:
        f = self.store.get_record("finding", fid)
        if not f:
            raise KeyError(fid)
        return f

    def link_finding(self, fid: str, case_id: str) -> dict:
        f = self.get_finding(fid)
        f["case_id"] = case_id
        self.store.put_record("finding", f)
        return f

    def checkpoints_for_nodes(self, node_ids: list[str]) -> list[str]:
        hits = [c["id"] for c in self.facility["checkpoints"] if set(c["near_nodes"]) & set(node_ids)]
        return hits or [self.facility["checkpoints"][0]["id"]]
