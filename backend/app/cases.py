"""Digital Safety Case workflow (prototype, demo roles).

Lifecycle:
  OPEN -> ACTION_RECORDED (technician) -> VERIFIED (independent verifier, different person)
       -> CLOSED (system: stabilization measured on real readings after the action)
  Any open case can be ESCALATED by a new CRITICAL decision (logged; remains open).
  A drone inspection can be requested at any time before closure (SIMULATED workflow).

Closure is refused unless all three conditions hold. Roles are demo roles chosen in the UI;
this is not production authentication.
"""
from __future__ import annotations

import itertools
from datetime import datetime, timezone

import pandas as pd

from backend.app.store import Store

STABILIZATION_MIN = 15          # prototype-configured rule (not a validated industrial standard)
MIN_LIVE_NODES = 2              # at least 2 nodes must deliver live data (coincidence still possible)
STABLE_P_FIRE = 0.2
DRONE_STEPS = ["REQUESTED", "APPROVED", "IN_FLIGHT", "COMPLETED"]


class WorkflowError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CaseManager:
    def __init__(self, store: Store):
        self.store = store
        existing = [int(c["id"].split("-")[-1]) for c in store.cases()]
        self._ids = itertools.count(max(existing, default=0) + 1)

    # ---------------------------------------------------------------- opening
    def open_case(self, *, zone: str, event_id: str, data_ts: str, decision: dict, snapshot: dict,
                  replay_run: int | None = None) -> dict:
        case = {
            "id": f"SC-{next(self._ids):04d}", "kind": "SENSOR_ALERT", "zone": zone, "replay_event": event_id,
            "replay_run": replay_run,
            "status": "OPEN", "severity": decision["level"], "opened_wall_ts": _now(), "opened_data_ts": data_ts,
            "findings": decision["reasons"], "fire_nodes": decision["fire_nodes"],
            "evidence": snapshot, "recommended_inspection": (
                "Inspect the zone around the flagged sensor nodes for smouldering material, overheated cables and "
                "electrical cabinets. Do not approach visible flames: follow the site emergency procedure."),
            "technician": None, "action": None, "verifier": None, "verification": None,
            "stabilization": None, "drone": None, "escalations": 0, "missions": [],
            "hedera": {"status": "pending", "note": "Anchoring on Hedera is not implemented yet"},
        }
        self.store.save_case(case)
        self.store.append("case_opened", "system", {"severity": case["severity"], "findings": case["findings"]},
                          data_ts=data_ts, case_id=case["id"])
        return case

    def open_finding_case(self, *, zone: str, finding: dict, opened_by: str) -> dict:
        """Safety Case from a preventive-inspection finding. The evidence is SIMULATED (illustrative finding)."""
        sev = {"LOW": "WATCH", "MEDIUM": "HIGH", "HIGH": "CRITICAL"}[finding["severity"]]
        case = {
            "id": f"SC-{next(self._ids):04d}", "kind": "INSPECTION_FINDING", "zone": zone, "replay_event": None,
            "status": "OPEN", "severity": sev, "opened_wall_ts": _now(), "opened_data_ts": None,
            "findings": [f"{finding['type_label']} at {finding['checkpoint_label']} ({finding['severity']})",
                         f"Operator note: {finding['note'] or '-'}",
                         "Illustrative finding from a SIMULATED drone mission; not detected by an AI model."],
            "fire_nodes": [], "evidence": {"finding": finding, "simulated": True},
            "source_finding": finding["id"], "checkpoint": finding["checkpoint"],
            "recommended_inspection": f"Correct the condition at {finding['checkpoint_label']}, then request a follow-up drone "
                                      "inspection of that checkpoint to confirm it is clear.",
            "technician": None, "action": None, "verifier": None, "verification": None,
            "stabilization": None, "drone": None, "escalations": 0, "missions": [finding["mission_id"]],
            "hedera": {"status": "pending", "note": "Anchoring on Hedera is not implemented yet"},
        }
        self.store.save_case(case)
        self.store.append("case_opened", "human", {"severity": sev, "from_finding": finding["id"], "illustrative": True,
                                                    "findings": case["findings"]}, actor=opened_by, case_id=case["id"])
        return case

    def attach_mission(self, case_id: str, mission_id: str) -> None:
        c = self.get(case_id)
        if mission_id not in c.setdefault("missions", []):
            c["missions"].append(mission_id)
            self.store.save_case(c)

    def inspection_closure_check(self, case_id: str, missions: list[dict]) -> dict:
        """INSPECTION_FINDING cases close when a FOLLOW_UP mission, started AFTER the corrective action, inspected the
        same checkpoint and the operator marked it clear. Simulated evidence, labelled as such."""
        c = self.get(case_id)
        if c["status"] != "VERIFIED":
            raise WorkflowError(f"the closure check runs after independent verification (status {c['status']})")
        after = c["action"]["wall_ts"]
        ok_m = [m for m in missions if m["id"] in c.get("missions", []) and m["mode"] == "FOLLOW_UP"
                and m["status"] == "COMPLETED" and (m["started_at"] or "") >= after
                and any(cp["id"] == c["checkpoint"] and cp["result"] == "clear" for cp in m["checkpoints"])]
        result = {"passed": bool(ok_m), "kind": "follow_up_inspection", "simulated": True,
                  "criterion": "A follow-up drone inspection of the same checkpoint, flown after the corrective action, "
                               "confirms the condition is cleared (SIMULATED mission; operator-recorded result).",
                  "evidence_mission": ok_m[0]["id"] if ok_m else None, "wall_ts": _now(),
                  "note": None if ok_m else "No completed follow-up inspection marked clear after the corrective action yet."}
        c["stabilization"] = result
        if ok_m:
            c["status"], c["closed_wall_ts"] = "CLOSED", _now()
        self.store.save_case(c)
        self.store.append("closure_check", "system", result, case_id=case_id)
        if ok_m:
            self.store.append("case_closed", "system", {"signatures": ["technician", "independent_verifier",
                                                                      "follow-up inspection (simulated)"]}, case_id=case_id)
        return c

    def get(self, case_id: str) -> dict:
        c = self.store.get_case(case_id)
        if not c:
            raise KeyError(case_id)
        return c

    def open_cases(self, zone: str | None = None, kind: str | None = None) -> list[dict]:
        return [c for c in self.store.cases() if c["status"] != "CLOSED" and (zone is None or c["zone"] == zone)
                and (kind is None or c.get("kind", "SENSOR_ALERT") == kind)]

    def escalate(self, case_id: str, data_ts: str, decision: dict) -> None:
        c = self.get(case_id)
        c["escalations"] += 1
        c["severity"] = "CRITICAL"
        self.store.save_case(c)
        self.store.append("case_escalated", "risk", {"reasons": decision["reasons"]}, data_ts=data_ts, case_id=case_id)

    # ---------------------------------------------------------------- drone (simulated)
    def drone(self, case_id: str, step: str, actor: str, data_ts: str | None) -> dict:
        c = self.get(case_id)
        if c["status"] == "CLOSED":
            raise WorkflowError("case is closed")
        cur = (c["drone"] or {}).get("status")
        expected = DRONE_STEPS[0] if cur is None else (DRONE_STEPS[DRONE_STEPS.index(cur) + 1]
                                                         if cur != DRONE_STEPS[-1] else None)
        if step != expected:
            raise WorkflowError(f"drone step {step!r} not allowed now (expected {expected!r})")
        d = c["drone"] or {"simulated": True, "history": []}
        d["status"] = step
        d["history"].append({"step": step, "actor": actor, "wall_ts": _now(), "data_ts": data_ts})
        if step == "COMPLETED":
            d["findings"] = ("SIMULATED inspection: no imagery was captured (no drone hardware connected). "
                             "In a deployment the drone would record visual and thermal images of the flagged area.")
        c["drone"] = d
        self.store.save_case(c)
        self.store.append(f"drone_{step.lower()}", "simulated", {"step": step}, data_ts=data_ts, actor=actor,
                          case_id=case_id)
        return c

    # ---------------------------------------------------------------- human steps
    def record_action(self, case_id: str, technician: str, action: str, data_ts: str) -> dict:
        c = self.get(case_id)
        if c["status"] not in ("OPEN",):
            raise WorkflowError(f"cannot record an action in status {c['status']}")
        if not technician.strip() or len(action.strip()) < 10:
            raise WorkflowError("technician name and a corrective action description (≥ 10 characters) are required")
        c.update(status="ACTION_RECORDED", technician=technician.strip(),
                 action={"text": action.strip(), "wall_ts": _now(), "data_ts": data_ts})
        self.store.save_case(c)
        self.store.append("technician_action", "human", {"action": action.strip()}, data_ts=data_ts,
                          actor=f"technician:{technician.strip()}", case_id=case_id)
        return c

    def verify(self, case_id: str, verifier: str, approve: bool, note: str, data_ts: str) -> dict:
        c = self.get(case_id)
        if c["status"] != "ACTION_RECORDED":
            raise WorkflowError(f"cannot verify in status {c['status']}")
        if verifier.strip().lower() == (c["technician"] or "").lower():
            raise WorkflowError("independent verification: the verifier must be a different person from the technician")
        if not approve:
            c.update(status="OPEN", verification={"by": verifier, "approved": False, "note": note, "wall_ts": _now()})
            self.store.save_case(c)
            self.store.append("verification_rejected", "human", {"note": note}, data_ts=data_ts,
                              actor=f"verifier:{verifier}", case_id=case_id)
            return c
        c.update(status="VERIFIED", verifier=verifier.strip(),
                 verification={"by": verifier.strip(), "approved": True, "note": note, "wall_ts": _now(), "data_ts": data_ts})
        self.store.save_case(c)
        self.store.append("verification_approved", "human", {"note": note}, data_ts=data_ts,
                          actor=f"verifier:{verifier.strip()}", case_id=case_id)
        return c

    # ---------------------------------------------------------------- outcome (label for learning)
    def confirm_outcome(self, case_id: str, person: str, outcome: str, note: str) -> dict:
        from learning.pipeline import OUTCOMES
        c = self.get(case_id)
        if outcome not in OUTCOMES:
            raise WorkflowError(f"outcome must be one of {sorted(OUTCOMES)}")
        if c["status"] not in ("VERIFIED", "CLOSED"):
            raise WorkflowError("the real outcome is confirmed after the independent check")
        if person.strip().lower() == (c.get("technician") or "").lower():
            raise WorkflowError("the outcome must be confirmed by someone other than the technician")
        c["outcome"] = {"label": outcome, "text": OUTCOMES[outcome], "by": person.strip(), "note": note.strip(), "wall_ts": _now()}
        self.store.save_case(c)
        self.store.append("outcome_confirmed", "human", {"outcome": outcome, "note": note.strip()},
                          actor=f"verifier:{person.strip()}", case_id=case_id)
        return c

    # ---------------------------------------------------------------- system check
    def stabilization_check(self, case_id: str, ticks: list[dict]) -> dict:
        """Count minutes of MEASURED readings after the corrective action in which every reporting node
        has P(fire) < STABLE_P_FIRE and the zone is NORMAL. Gaps (no fresh data) do not count."""
        c = self.get(case_id)
        if c.get("kind") == "INSPECTION_FINDING":
            raise WorkflowError("inspection-finding cases close with a follow-up inspection, not a sensor stabilization check")
        if c["status"] != "VERIFIED":
            raise WorkflowError(f"stabilization is checked after independent verification (status {c['status']})")
        since = pd.Timestamp(c["action"]["data_ts"])
        after = [t for t in ticks if pd.Timestamp(t["t"]) > since]
        good, run, broken_at = 0, 0, None
        for t in after:
            if t.get("fresh_nodes", 0) < MIN_LIVE_NODES:
                continue                                    # gap or held values: does not count, does not reset
            if t["level"] == "NORMAL" and (t["max_p_fire"] or 0) < STABLE_P_FIRE:
                run += 1
            else:
                run, broken_at = 0, t["t"]
            good = max(good, run)
        need = STABILIZATION_MIN * 60 // 10
        ok = good >= need
        last_t = after[-1]["t"] if after else None
        measured_after = sum(1 for t in after if t.get("fresh_nodes", 0) >= MIN_LIVE_NODES)
        held_after = sum(1 for t in after if t.get("fresh_nodes", 0) < MIN_LIVE_NODES)
        result = {"passed": ok, "measured_minutes": round(good * 10 / 60, 1), "required_minutes": STABILIZATION_MIN,
                  "criterion": f"{STABILIZATION_MIN} consecutive minutes of LIVE readings (>= {MIN_LIVE_NODES} nodes) with risk "
                               f"NORMAL and P(fire) < {STABLE_P_FIRE}, after the corrective action. Gaps and held/repeated "
                               "values do not count. Prototype rule, not a validated industrial standard.",
                  "last_interruption": broken_at, "checked_up_to": last_t, "wall_ts": _now(),
                  "measured_ticks_after_action": measured_after, "non_live_ticks_after_action": held_after,
                  "note": None if ok else ("No measured data after the corrective action yet: resume the replay. "
                                           "If the recording has ended, the case stays open awaiting stabilization; "
                                           "it is never closed on simulated or held data." if measured_after == 0 else
                                           f"Not enough consecutive live normal readings ({round(good * 10 / 60, 1)} of "
                                           f"{STABILIZATION_MIN} min). {held_after} of the {len(after)} readings after the "
                                           "action were missing or held/repeated values and do not count. If the replay "
                                           "is still running, check again later; if the recording has ended, the case "
                                           "stays open awaiting stabilization.")}
        c["stabilization"] = result
        if ok:
            c["status"] = "CLOSED"
            c["closed_wall_ts"] = _now()
            c["closed_data_ts"] = last_t
        self.store.save_case(c)
        self.store.append("stabilization_check", "system", result, data_ts=last_t, case_id=case_id)
        if ok:
            self.store.append("case_closed", "system", {"signatures": ["technician", "independent_verifier", "system"]},
                              data_ts=last_t, case_id=case_id)
        return c
