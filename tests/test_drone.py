"""Drone operations (simulated): preventive patrols, scheduling, findings, alert-triggered inspections,
and their integration with Safety Cases, Passport and Black Box."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.store import Store
from drone.missions import DWELL_SECONDS, LEG_SECONDS, MissionError, MissionManager
from ingest.download import RAW

FACILITY = json.loads((Path(__file__).resolve().parents[1] / "backend/app/data/facility.json").read_text(encoding="utf-8"))


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def mm(tmp_path):
    clock = Clock()
    m = MissionManager(Store(tmp_path / "d.db"), FACILITY, clock=clock, autostart=False)
    m.clock_obj = clock
    return m


def fly(mm, seconds, step=0.5):
    for _ in range(int(seconds / step)):
        mm.tick(step)


# ----------------------------------------------------------------- preventive patrols

def test_default_schedule_exists_and_is_labelled_simulated(mm):
    s = mm.schedules()
    assert len(s) == 1 and s[0]["route_id"] == "R-FULL" and s[0]["simulated"] and s[0]["enabled"]


def test_manual_patrol_moves_along_route_and_completes(mm):
    m = mm.create_mission("PREVENTIVE", "R-ELEC", origin="MANUAL")
    assert m["status"] == "IN_FLIGHT" and [c["id"] for c in m["checkpoints"]] == ["CP-EL", "CP-CT"]
    start = dict(m["position"])
    fly(mm, LEG_SECONDS / 2)
    mid = mm.get(m["id"])
    assert mid["position"] != start and mid["checkpoints"][0]["status"] == "pending"
    fly(mm, LEG_SECONDS)                                   # first checkpoint reached
    assert mm.get(m["id"])["checkpoints"][0]["status"] == "inspected"
    fly(mm, 3 * (LEG_SECONDS + DWELL_SECONDS))
    done = mm.get(m["id"])
    assert done["status"] == "COMPLETED" and done["progress"] == 1.0
    assert all(c["status"] == "inspected" for c in done["checkpoints"])
    assert done["position"] == {"x": FACILITY["drone_dock"]["x"], "y": FACILITY["drone_dock"]["y"]}


def test_pause_resume_and_cancel(mm):
    m = mm.create_mission("PREVENTIVE", "R-FULL", origin="MANUAL")
    fly(mm, 2)
    mm.control(m["id"], "pause")
    pos = mm.get(m["id"])["position"]
    fly(mm, 5)
    assert mm.get(m["id"])["position"] == pos              # paused: no movement
    mm.control(m["id"], "resume")
    fly(mm, 1)
    assert mm.get(m["id"])["position"] != pos
    mm.control(m["id"], "cancel")
    assert mm.get(m["id"])["status"] == "CANCELLED"
    with pytest.raises(MissionError):
        mm.control(m["id"], "resume")


def test_only_one_patrol_in_flight(mm):
    mm.create_mission("PREVENTIVE", "R-FULL", origin="MANUAL")
    with pytest.raises(MissionError):
        mm.create_mission("PREVENTIVE", "R-ELEC", origin="MANUAL")


def test_scheduler_launches_due_patrols_and_reschedules(mm):
    s = mm.update_schedule(mm.schedules()[0]["id"], every_minutes=30, start_in_minutes=0)
    started = mm.run_due_schedules()
    assert len(started) == 1 and started[0]["origin"] == "SCHEDULED" and started[0]["schedule_id"] == s["id"]
    nxt = datetime.fromisoformat(mm.schedules()[0]["next_due"])
    assert nxt > mm.clock_obj.t
    assert mm.run_due_schedules() == []                    # not due again yet
    mm.update_schedule(s["id"], enabled=False)
    mm.clock_obj.advance(hours=2)
    assert mm.run_due_schedules() == []                    # disabled


def test_schedule_validation(mm):
    with pytest.raises(MissionError):
        mm.create_schedule("R-NOPE", 10)
    with pytest.raises(MissionError):
        mm.create_schedule("R-FULL", 0)


def test_findings_only_on_inspected_checkpoints_and_are_illustrative(mm):
    m = mm.create_mission("PREVENTIVE", "R-EXITS", origin="MANUAL")
    with pytest.raises(MissionError):
        mm.record_finding(m["id"], "CP-EE", "obstructed_exit", "MEDIUM", "pallets")
    fly(mm, 3 * (LEG_SECONDS + DWELL_SECONDS))
    f = mm.record_finding(m["id"], "CP-EE", "obstructed_exit", "MEDIUM", "pallets in front of the door")
    assert f["illustrative"] and "Illustrative" in f["label"] and f["checkpoint"] == "CP-EE"
    assert mm.get_finding(f["id"])["mission_id"] == m["id"]
    with pytest.raises(MissionError):
        mm.record_finding(m["id"], "CP-EE", "not_a_type", "MEDIUM", "x")


def test_targeted_mission_needs_operator_approval(mm):
    m = mm.create_mission("TARGETED", origin="ALERT", checkpoints=["CP-CT"], case_id="SC-0001")
    assert m["status"] == "AWAITING_APPROVAL"
    fly(mm, 20)
    assert mm.get(m["id"])["status"] == "AWAITING_APPROVAL"   # never flies without approval
    mm.control(m["id"], "approve")
    assert mm.get(m["id"])["status"] == "IN_FLIGHT"


def test_checkpoints_follow_flagged_nodes(mm):
    assert mm.checkpoints_for_nodes(["sensornode0006", "sensornode0007"]) == ["CP-EL", "CP-CT"]


# ----------------------------------------------------------------- integration through the API

needs_data = pytest.mark.skipif(not (RAW / "industrial_hall_fire").exists(), reason="run: python -m ingest download")


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    from fastapi.testclient import TestClient
    from backend.app import main
    rt = main.Runtime(db_path=tmp_path_factory.mktemp("db") / "api.db", simulate_drone=False)
    main.use_runtime(rt)
    with TestClient(main.app) as c:
        c.rt = rt
        yield c


@needs_data
def test_preventive_finding_to_closed_case_with_role_separation(api):
    rt = api.rt
    api.post("/api/demo/reset")
    m = api.post("/api/drone/missions", json={"route_id": "R-EXITS"}).json()
    fly(rt.drone, 3 * (LEG_SECONDS + DWELL_SECONDS))
    f = api.post(f"/api/drone/missions/{m['id']}/findings",
                 json={"checkpoint": "CP-EE", "type": "obstructed_exit", "severity": "MEDIUM", "note": "pallets"}).json()
    case = api.post(f"/api/findings/{f['id']}/case", json={}).json()
    assert case["kind"] == "INSPECTION_FINDING" and case["evidence"]["simulated"]
    assert api.post(f"/api/findings/{f['id']}/case", json={}).status_code == 409     # no duplicate case
    cid = case["id"]
    # closure refused before action / verification
    assert api.post(f"/api/cases/{cid}/close-check").status_code == 409
    api.post(f"/api/cases/{cid}/action", json={"technician": "Amine", "action": "Removed pallets from the exit"})
    assert api.post(f"/api/cases/{cid}/verify", json={"verifier": "Amine", "approve": True}).status_code == 409
    api.post(f"/api/cases/{cid}/verify", json={"verifier": "Sami", "approve": True, "note": "ok"})
    # no follow-up inspection yet -> stays open
    c = api.post(f"/api/cases/{cid}/close-check").json()
    assert c["status"] == "VERIFIED" and not c["stabilization"]["passed"]
    # follow-up inspection, operator marks the exit clear, then the check closes the case
    fu = api.post(f"/api/cases/{cid}/inspection").json()
    assert fu["mode"] == "FOLLOW_UP" and [x["id"] for x in fu["checkpoints"]] == ["CP-EE"]
    fly(rt.drone, 3 * (LEG_SECONDS + DWELL_SECONDS))
    api.post(f"/api/drone/missions/{fu['id']}/clear", json={"checkpoint": "CP-EE"})
    c = api.post(f"/api/cases/{cid}/close-check").json()
    assert c["status"] == "CLOSED" and c["stabilization"]["simulated"]
    # passport and black box
    p = api.get("/api/passport").json()
    assert p["counts"]["closed"] == 1 and p["inspections"]["findings"][0]["case_id"] == cid and p["integrity"]["ok"]
    kinds = [e["kind"] for e in api.get(f"/api/timeline?case_id={cid}").json()]
    for k in ("case_opened", "technician_action", "verification_approved", "mission_created", "checkpoint_clear", "case_closed"):
        assert k in kinds, k
    assert any(e["kind"] == "inspection_finding" for e in api.get("/api/timeline").json())


@needs_data
def test_sensor_alert_requests_targeted_inspection_awaiting_approval(api):
    api.post("/api/demo/reset")
    api.post("/api/replay/load", json={"event_id": "Cable#4"})
    case = None
    for _ in range(400):
        api.post("/api/replay/step", json={"ticks": 1})
        cs = api.get("/api/cases").json()
        if cs:
            case = cs[0]
            break
    assert case and case["kind"] == "SENSOR_ALERT" and len(case["missions"]) == 1
    m = next(x for x in api.get("/api/drone").json()["missions"] if x["id"] == case["missions"][0])
    assert m["mode"] == "TARGETED" and m["status"] == "AWAITING_APPROVAL" and m["case_id"] == case["id"]
    assert {c["id"] for c in m["checkpoints"]} & {"CP-EL", "CP-CT", "CP-WE"}
    assert api.post(f"/api/drone/missions/{m["id"]}/actions/approve").json()["status"] == "IN_FLIGHT"
    # a sensor case still uses the measured stabilization rule, not the inspection rule
    assert api.post(f"/api/cases/{case['id']}/close-check").status_code == 409            # not verified yet


@needs_data
def test_drone_api_errors(api):
    assert api.post("/api/drone/missions", json={"route_id": "R-NOPE"}).status_code == 409
    assert api.post("/api/drone/missions/M-9999/actions/pause").status_code == 404
    assert api.post("/api/drone/missions/M-9999/actions/explode").status_code == 422
    assert api.post("/api/findings/F-9999/case", json={}).status_code == 404
