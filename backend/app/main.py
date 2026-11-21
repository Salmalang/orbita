"""AEROGUARD TRUST backend API + control-room UI.

Run:  .venv/Scripts/python -m uvicorn backend.app.main:app --port 8000
Open: http://localhost:8000
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ai import registry
from backend.app.cases import CaseManager, WorkflowError
from backend.app.replay import SPEEDS, HallData, ReplayEngine
from backend.app.store import DEFAULT_DB, Store
from drone.missions import FINDING_TYPES, SEVERITIES, MissionError, MissionManager

ROOT = Path(__file__).resolve().parents[2]
FACILITY = json.loads((Path(__file__).parent / "data" / "facility.json").read_text(encoding="utf-8"))
ZONE = FACILITY["id"]
REFERENCE_IMG = ROOT / "data" / "raw" / "motor_thermal" / "extracted" / "IR-Motor-bmp" / "A&C&B30"

app = FastAPI(title="AEROGUARD TRUST", version="0.3.0",
              description="Industrial fire-safety prototype. Historical replay of real recordings; demo roles.")


class Runtime:
    """Holds the singletons. Built lazily so tests can inject a temporary database."""

    def __init__(self, db_path=None, simulate_drone: bool = True):
        self.store = Store(db_path or os.environ.get("AEROGUARD_DB", DEFAULT_DB))
        self.cases = CaseManager(self.store)
        self.simulate_drone = simulate_drone
        self.drone = MissionManager(self.store, FACILITY, autostart=simulate_drone)
        self.data = HallData()
        self.engine = ReplayEngine(self.data, on_tick=self.on_tick)
        self._last_level = "NORMAL"
        self._lock = threading.Lock()
        self.auto_pause = True

    def on_tick(self, rec: dict, decision, engine: ReplayEngine) -> None:
        level = decision.level
        with self._lock:
            prev, self._last_level = self._last_level, level
        if level == prev:
            return
        snap = engine.snapshot()["latest"]
        evidence = {"nodes": {k: {"p_fire": round(v["p_fire"], 4), "p_nuisance": round(v["p_nuisance"], 4),
                                  "readings": v["readings"]} for k, v in snap["nodes"].items()},
                    "model": engine.snapshot()["model"]}
        self.store.append("risk_level_changed", "risk",
                          {"from": prev, "to": level, "score": decision.score, "reasons": decision.reasons,
                           "fire_nodes": decision.fire_nodes, "evidence": evidence},
                          data_ts=rec["t"])
        if level in ("HIGH", "CRITICAL"):
            self.store.append("alert", "risk", {"level": level, "reasons": decision.reasons,
                                                "replay_event": engine.state.event_id}, data_ts=rec["t"])
        if level == "CRITICAL":
            open_ = self.cases.open_cases(ZONE, kind="SENSOR_ALERT")
            if not open_:
                case = self.cases.open_case(zone=ZONE, event_id=engine.state.event_id, data_ts=rec["t"],
                                            decision=decision.__dict__, snapshot=evidence)
                # MODE B: request a targeted inspection of the flagged area; it waits for operator approval
                cps = self.drone.checkpoints_for_nodes(decision.fire_nodes)
                m = self.drone.create_mission("TARGETED", origin="ALERT", checkpoints=cps, case_id=case["id"],
                                              reason=f"Sensor alert: {decision.reasons[0]}")
                self.cases.attach_mission(case["id"], m["id"])
                if self.auto_pause:
                    engine.pause()   # the operator stops the replay to respond, as in a real control room
                    self.store.append("replay_auto_paused", "system", {"reason": f"Safety Case {case['id']} opened"},
                                      data_ts=rec["t"], case_id=case["id"])
            elif open_[0]["status"] != "OPEN":
                # fire signature back after the corrective action: that is a real escalation
                self.cases.escalate(open_[0]["id"], rec["t"], decision.__dict__)

    def cursor(self) -> str | None:
        return self.engine.snapshot()["cursor"]


_rt: Runtime | None = None
_rt_lock = threading.Lock()


def rt() -> Runtime:
    global _rt
    with _rt_lock:
        if _rt is None:
            _rt = Runtime()
        return _rt


def use_runtime(runtime: Runtime) -> None:
    """For tests."""
    global _rt
    _rt = runtime


def _err(e: Exception, code: int = 409):
    raise HTTPException(status_code=code, detail=str(e))


# ------------------------------------------------------------------------------ models
class LoadReq(BaseModel):
    event_id: str


class SpeedReq(BaseModel):
    speed: int


class StepReq(BaseModel):
    ticks: int = Field(1, ge=1, le=2000)


class ActionReq(BaseModel):
    technician: str = Field(min_length=2, max_length=60)
    action: str = Field(min_length=10, max_length=1000)


class VerifyReq(BaseModel):
    verifier: str = Field(min_length=2, max_length=60)
    approve: bool
    note: str = Field("", max_length=1000)


class MissionReq(BaseModel):
    route_id: str


class FindingReq(BaseModel):
    checkpoint: str
    type: str
    severity: str
    note: str = Field("", max_length=500)
    actor: str = Field("operator", max_length=60)


class ClearReq(BaseModel):
    checkpoint: str
    actor: str = Field("operator", max_length=60)


class ScheduleReq(BaseModel):
    every_minutes: int | None = Field(None, ge=1, le=1440)
    enabled: bool | None = None
    start_in_minutes: int | None = Field(None, ge=0, le=1440)


class NewScheduleReq(BaseModel):
    route_id: str
    every_minutes: int = Field(ge=1, le=1440)
    start_in_minutes: int = Field(0, ge=0, le=1440)


class FindingCaseReq(BaseModel):
    opened_by: str = Field("operator", max_length=60)


class DroneReq(BaseModel):
    step: str
    actor: str = Field("operator", max_length=60)


# ------------------------------------------------------------------------------ system
@app.get("/api/health")
def health():
    r = rt()
    return {"status": "ok", "replay_loaded": r.engine.state.event_id is not None,
            "models": [f"{c['name']}/{c['version']}" for c in registry.cards()],
            "integrity": r.store.verify_chain()}


@app.get("/api/facility")
def facility():
    return FACILITY


@app.post("/api/demo/reset")
def demo_reset():
    r = rt()
    r.engine.pause()
    r.store.reset()
    r.cases = CaseManager(r.store)
    r.drone.__init__(r.store, FACILITY, autostart=False)   # keep the running simulator thread, reset state
    r._last_level = "NORMAL"
    r.store.append("demo_reset", "system", {"note": "demo database cleared"})
    return {"ok": True}


# ------------------------------------------------------------------------------ replay
@app.get("/api/replay/catalog")
def catalog():
    return rt().data.catalog()


@app.post("/api/replay/load")
def replay_load(req: LoadReq):
    r = rt()
    try:
        info = r.engine.load(req.event_id)
    except KeyError as e:
        _err(e, 404)
    r._last_level = "NORMAL"
    r.store.append("replay_loaded", "system", info)
    return info


@app.post("/api/replay/play")
def replay_play():
    try:
        rt().engine.play()
    except RuntimeError as e:
        _err(e)
    return rt().engine.snapshot()


@app.post("/api/replay/pause")
def replay_pause():
    rt().engine.pause()
    return rt().engine.snapshot()


@app.post("/api/replay/speed")
def replay_speed(req: SpeedReq):
    try:
        rt().engine.set_speed(req.speed)
    except ValueError as e:
        _err(e, 422)
    return rt().engine.snapshot()


@app.post("/api/replay/step")
def replay_step(req: StepReq):
    if rt().engine.state.event_id is None:
        _err(RuntimeError("load an event first"))
    rt().engine.step(req.ticks)
    return rt().engine.snapshot()


@app.get("/api/replay/state")
def replay_state():
    return {**rt().engine.snapshot(), "speeds": SPEEDS}


@app.get("/api/replay/series")
def replay_series(since: int = 0):
    return rt().engine.series(max(0, since))


@app.get("/api/replay/node/{node_id}")
def replay_node(node_id: str):
    if node_id not in {n["id"] for n in FACILITY["nodes"]}:
        _err(KeyError(f"unknown node {node_id}"), 404)
    return rt().engine.node_history(node_id)


# ------------------------------------------------------------------------------ alerts / cases
@app.get("/api/alerts")
def alerts(limit: int = 50):
    return rt().store.events(kinds=["alert"], limit=limit)


@app.get("/api/cases")
def list_cases():
    return rt().store.cases()


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    try:
        return rt().cases.get(case_id)
    except KeyError:
        _err(KeyError(f"case {case_id} not found"), 404)


@app.post("/api/cases/{case_id}/action")
def case_action(case_id: str, req: ActionReq):
    try:
        return rt().cases.record_action(case_id, req.technician, req.action, rt().cursor())
    except KeyError:
        _err(KeyError(case_id), 404)
    except WorkflowError as e:
        _err(e)


@app.post("/api/cases/{case_id}/verify")
def case_verify(case_id: str, req: VerifyReq):
    try:
        return rt().cases.verify(case_id, req.verifier, req.approve, req.note, rt().cursor())
    except KeyError:
        _err(KeyError(case_id), 404)
    except WorkflowError as e:
        _err(e)


@app.post("/api/cases/{case_id}/stabilization")
def case_stabilization(case_id: str):
    try:
        return rt().cases.stabilization_check(case_id, rt().engine.state.ticks)
    except KeyError:
        _err(KeyError(case_id), 404)
    except WorkflowError as e:
        _err(e)


@app.post("/api/cases/{case_id}/drone")
def case_drone(case_id: str, req: DroneReq):
    try:
        return rt().cases.drone(case_id, req.step, req.actor, rt().cursor())
    except KeyError:
        _err(KeyError(case_id), 404)
    except WorkflowError as e:
        _err(e)


# ------------------------------------------------------------------------------ drone operations (SIMULATED)
@app.get("/api/drone")
def drone_overview():
    d = rt().drone
    return {"routes": FACILITY["routes"], "checkpoints": FACILITY["checkpoints"], "dock": FACILITY["drone_dock"],
            "schedules": d.schedules(), "active": d.active_mission(), "missions": d.missions()[:30],
            "findings": d.findings()[:50], "finding_types": FINDING_TYPES, "severities": SEVERITIES,
            "simulated": True, "note": FACILITY["drone_note"],
            "scheduler_note": "Simulated scheduler: patrols launch only while the AEROGUARD server is running."}


def _mission_call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except KeyError as e:
        _err(KeyError(f"not found: {e}"), 404)
    except MissionError as e:
        _err(e)


@app.post("/api/drone/missions")
def drone_start(req: MissionReq):
    return _mission_call(rt().drone.create_mission, "PREVENTIVE", req.route_id, origin="MANUAL")


@app.post("/api/drone/missions/{mid}/actions/{action}")
def drone_control(mid: str, action: str):
    if action not in ("approve", "pause", "resume", "cancel"):
        _err(ValueError("action must be approve, pause, resume or cancel"), 422)
    return _mission_call(rt().drone.control, mid, action)


@app.post("/api/drone/missions/{mid}/findings")
def drone_finding(mid: str, req: FindingReq):
    return _mission_call(rt().drone.record_finding, mid, req.checkpoint, req.type, req.severity, req.note, req.actor)


@app.post("/api/drone/missions/{mid}/clear")
def drone_clear(mid: str, req: ClearReq):
    return _mission_call(rt().drone.mark_clear, mid, req.checkpoint, req.actor)


@app.post("/api/drone/schedules")
def drone_new_schedule(req: NewScheduleReq):
    return _mission_call(rt().drone.create_schedule, req.route_id, req.every_minutes, req.start_in_minutes)


@app.post("/api/drone/schedules/{sid}")
def drone_update_schedule(sid: str, req: ScheduleReq):
    return _mission_call(rt().drone.update_schedule, sid, req.every_minutes, req.enabled, req.start_in_minutes)


@app.post("/api/findings/{fid}/case")
def finding_to_case(fid: str, req: FindingCaseReq):
    r = rt()
    f = _mission_call(r.drone.get_finding, fid)
    if f["case_id"]:
        _err(WorkflowError(f"finding already linked to {f['case_id']}"))
    case = r.cases.open_finding_case(zone=ZONE, finding=f, opened_by=req.opened_by)
    r.drone.link_finding(fid, case["id"])
    r.store.append("alert", "simulated", {"level": case["severity"], "reasons": case["findings"][:1],
                                          "from_finding": fid, "illustrative": True}, case_id=case["id"])
    return case


@app.post("/api/cases/{case_id}/inspection")
def case_inspection(case_id: str):
    """Request a drone inspection for a case: follow-up after the corrective action, targeted otherwise."""
    r = rt()
    try:
        c = r.cases.get(case_id)
    except KeyError:
        _err(KeyError(case_id), 404)
    if c["status"] == "CLOSED":
        _err(WorkflowError("case is closed"))
    if c.get("kind") == "INSPECTION_FINDING":
        cps, mode, origin = [c["checkpoint"]], "FOLLOW_UP", "FOLLOW_UP"
    else:
        cps = r.drone.checkpoints_for_nodes(c.get("fire_nodes", []))
        mode, origin = ("FOLLOW_UP", "FOLLOW_UP") if c.get("action") else ("TARGETED", "ALERT")
    m = _mission_call(r.drone.create_mission, mode, origin=origin, checkpoints=cps, case_id=case_id,
                      reason=f"Requested for {case_id}")
    r.cases.attach_mission(case_id, m["id"])
    return m


@app.post("/api/cases/{case_id}/close-check")
def case_close_check(case_id: str):
    r = rt()
    try:
        c = r.cases.get(case_id)
        if c.get("kind") == "INSPECTION_FINDING":
            return r.cases.inspection_closure_check(case_id, r.drone.missions())
        return r.cases.stabilization_check(case_id, r.engine.state.ticks)
    except KeyError:
        _err(KeyError(case_id), 404)
    except WorkflowError as e:
        _err(e)


# ------------------------------------------------------------------------------ passport, timeline, fire pack
@app.get("/api/timeline")
def timeline(case_id: str | None = None, limit: int = 500):
    return rt().store.events(case_id=case_id, limit=limit)


@app.get("/api/passport")
def passport():
    r = rt()
    cases = [c for c in r.store.cases() if c["zone"] == ZONE]
    return {"zone": {k: FACILITY[k] for k in ("id", "name", "site", "dimensions_m", "criticality", "illustrative_note")},
            "nodes": FACILITY["nodes"],
            "cases": cases,
            "counts": {"total": len(cases), "closed": sum(c["status"] == "CLOSED" for c in cases),
                       "open": sum(c["status"] != "CLOSED" for c in cases)},
            "integrity": r.store.verify_chain(),
            "inspections": {"missions": r.drone.missions()[:20], "findings": r.drone.findings()[:20], "simulated": True},
            "hedera": {"status": "pending", "note": "Hedera anchoring not implemented yet; integrity is a local SHA-256 chain"},
            "models": [{"name": c["name"], "version": c["version"], "model_sha256": c["model_sha256"],
                        "training_data_sha256": c["training_data_sha256"]} for c in registry.cards()]}


@app.get("/api/firepack")
def firepack():
    r = rt()
    snap = r.engine.snapshot()
    return {"facility": FACILITY, "replay": {"event_id": snap["event_id"], "cursor": snap["cursor"],
                                             "historical_replay": True},
            "latest": snap["latest"], "open_cases": r.cases.open_cases(ZONE)}


@app.get("/api/evidence")
def evidence():
    cards = {f"{c['name']}/{c['version']}": c for c in registry.cards()}
    z = cards.get("zone_fire/1.0.0", {}).get("metrics", {})
    return {"zone_nested": z.get("nested_estimate"), "zone_particle_baseline": z.get("particle_threshold_baseline"),
            "early_warning": cards.get("early_warning/1.0.0", {}).get("metrics"),
            "compressor": cards.get("compressor/1.0.0", {}).get("metrics"),
            "motor": cards.get("motor/1.0.0", {}).get("metrics"),
            "holdout_models": [k for k in cards if k.startswith("zone_fire_holdout")],
            "timing": _report_numbers().get("zone_timing")}


def _report_numbers() -> dict:
    p = ROOT / "docs" / "report_figures" / "numbers.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@app.get("/api/reference-image")
def reference_image():
    files = sorted(REFERENCE_IMG.glob("*.bmp")) if REFERENCE_IMG.exists() else []
    if not files:
        raise HTTPException(404, "reference images not downloaded (python -m ingest download motor_thermal)")
    return FileResponse(files[len(files) // 2], media_type="image/bmp")


# ------------------------------------------------------------------------------ static
for mount, folder in (("/figures", ROOT / "docs" / "figures"), ("/reports", ROOT / "ai" / "reports")):
    if folder.exists():
        app.mount(mount, StaticFiles(directory=folder), name=mount.strip("/"))
app.mount("/", StaticFiles(directory=ROOT / "dashboard", html=True), name="ui")


@app.middleware("http")
async def no_stale_ui(request, call_next):
    """Browsers must revalidate UI files so a demo never runs an outdated interface."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(Exception)
def unhandled(_, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})
