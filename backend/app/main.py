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

ROOT = Path(__file__).resolve().parents[2]
FACILITY = json.loads((Path(__file__).parent / "data" / "facility.json").read_text(encoding="utf-8"))
ZONE = FACILITY["id"]
REFERENCE_IMG = ROOT / "data" / "raw" / "motor_thermal" / "extracted" / "IR-Motor-bmp" / "A&C&B30"

app = FastAPI(title="AEROGUARD TRUST", version="0.3.0",
              description="Industrial fire-safety prototype. Historical replay of real recordings; demo roles.")


class Runtime:
    """Holds the singletons. Built lazily so tests can inject a temporary database."""

    def __init__(self, db_path=None):
        self.store = Store(db_path or os.environ.get("AEROGUARD_DB", DEFAULT_DB))
        self.cases = CaseManager(self.store)
        self.data = HallData()
        self.engine = ReplayEngine(self.data, on_tick=self.on_tick)
        self._last_level = "NORMAL"
        self._lock = threading.Lock()

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
            open_ = self.cases.open_cases(ZONE)
            if not open_:
                self.cases.open_case(zone=ZONE, event_id=engine.state.event_id, data_ts=rec["t"],
                                     decision=decision.__dict__, snapshot=evidence)
            else:
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
            "holdout_models": [k for k in cards if k.startswith("zone_fire_holdout")]}


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


@app.exception_handler(Exception)
def unhandled(_, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})
