"""Part 3 checks: replay, risk engine, Safety Case workflow, persistence and API, on real data."""
import pandas as pd
import pytest

from ingest.download import RAW

pytestmark = pytest.mark.skipif(not (RAW / "industrial_hall_fire").exists(), reason="run: python -m ingest download")


# ----------------------------------------------------------------- risk engine (unit)

def _ticks(pf, pn=0.0, n=3, age=0.0):
    from backend.app.risk import NodeTick
    return [NodeTick(f"n{i}", pf, pn, {"co_ppm": 0.1 * i}, age) for i in range(n)]


def test_risk_requires_persistence_and_coincidence():
    from backend.app.risk import RiskEngine
    eng = RiskEngine()
    levels = [eng.evaluate(_ticks(0.99)).level for _ in range(3)]
    assert levels[-1] == "CRITICAL" and "CRITICAL" not in levels[:2]
    eng.reset()
    from backend.app.risk import NodeTick
    one = lambda: [NodeTick("a", 0.99, 0, None), NodeTick("b", 0.01, 0, None)]
    assert [eng.evaluate(one()).level for _ in range(3)][-1] == "HIGH"


def test_risk_nuisance_is_watch_not_fire():
    from backend.app.risk import RiskEngine
    eng = RiskEngine()
    d = [eng.evaluate(_ticks(0.1, 0.9)) for _ in range(3)][-1]
    assert d.level == "WATCH" and "nuisance" in d.reasons[0]


def test_risk_data_gap_is_no_data_not_normal():
    from backend.app.risk import RiskEngine
    d = RiskEngine().evaluate(_ticks(None, None, age=300))
    assert d.level == "NO_DATA" and d.healthy_nodes == 0


# ----------------------------------------------------------------- no future data

def test_features_are_causal():
    """Features at time t must not change when every reading after t is deleted."""
    from ai import zone_fire as Z
    from ingest.loaders.fire_sensors import load_industrial_hall
    hall = load_industrial_hall()
    node = hall[hall["sensor_id"] == "sensornode0010"].sort_values("timestamp").iloc[:6000]
    cut = node["timestamp"].iloc[4000]
    full = Z.node_features(node).set_index("timestamp")
    past = Z.node_features(node[node["timestamp"] <= cut]).set_index("timestamp")
    pd.testing.assert_frame_equal(full.loc[:cut], past, check_freq=False)


# ----------------------------------------------------------------- API end to end

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from fastapi.testclient import TestClient
    from backend.app import main
    rt = main.Runtime(db_path=tmp_path_factory.mktemp("db") / "test.db")
    main.use_runtime(rt)
    with TestClient(main.app) as c:
        yield c


def test_health_and_catalog(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["integrity"]["ok"]
    cat = client.get("/api/replay/catalog").json()
    assert {"Cable#4", "Exhaust#1"} <= {e["id"] for e in cat}


def test_api_errors(client):
    assert client.post("/api/replay/load", json={"event_id": "Nope#1"}).status_code == 404
    assert client.post("/api/replay/speed", json={"speed": 7}).status_code == 422
    assert client.get("/api/cases/SC-9999").status_code == 404
    assert client.post("/api/cases/SC-9999/action", json={"technician": "Amine", "action": "x" * 12}).status_code == 404


def test_nuisance_replay_opens_no_case(client):
    client.post("/api/demo/reset")
    client.post("/api/replay/load", json={"event_id": "Exhaust#1"})
    client.post("/api/replay/step", json={"ticks": 2000})
    assert client.get("/api/cases").json() == []


def test_fire_replay_full_safety_case_workflow(client):
    client.post("/api/demo/reset")
    info = client.post("/api/replay/load", json={"event_id": "Cable#4"}).json()
    assert info["model"] == "zone_fire_holdout/cable-4"           # held-out model, never saw Cable#4
    # advance until a case opens
    case = None
    for _ in range(400):
        client.post("/api/replay/step", json={"ticks": 1})
        cases = client.get("/api/cases").json()
        if cases:
            case = cases[0]
            break
    assert case and case["status"] == "OPEN" and case["severity"] == "CRITICAL"
    cid = case["id"]
    state = client.get("/api/replay/state").json()
    assert state["cursor"] <= state["event_end"]                  # detected during the real event
    # cannot verify or close before the technician acts
    assert client.post(f"/api/cases/{cid}/verify", json={"verifier": "Sami", "approve": True}).status_code == 409
    assert client.post(f"/api/cases/{cid}/stabilization").status_code == 409
    # simulated drone, in order only
    assert client.post(f"/api/cases/{cid}/drone", json={"step": "COMPLETED"}).status_code == 409
    for step in ("REQUESTED", "APPROVED", "IN_FLIGHT", "COMPLETED"):
        assert client.post(f"/api/cases/{cid}/drone", json={"step": step}).status_code == 200
    # technician, then the same person cannot verify
    r = client.post(f"/api/cases/{cid}/action", json={"technician": "Amine", "action": "Isolated cable tray circuit, removed burnt insulation"})
    assert r.status_code == 200 and r.json()["status"] == "ACTION_RECORDED"
    assert client.post(f"/api/cases/{cid}/verify", json={"verifier": "amine", "approve": True}).status_code == 409
    assert client.post(f"/api/cases/{cid}/verify", json={"verifier": "Sami", "approve": True, "note": "Checked on site"}).json()["status"] == "VERIFIED"
    # stabilization right after verification: not enough measured normal data yet
    c = client.post(f"/api/cases/{cid}/stabilization").json()
    assert c["status"] == "VERIFIED" and not c["stabilization"]["passed"]
    # replay the real recovery data, then the system check passes
    client.post("/api/replay/step", json={"ticks": 2000})
    c = client.post(f"/api/cases/{cid}/stabilization").json()
    assert c["stabilization"]["passed"] and c["status"] == "CLOSED", c["stabilization"]
    # passport and black box reflect it, chain intact
    p = client.get("/api/passport").json()
    assert p["counts"]["closed"] == 1 and p["integrity"]["ok"] and p["hedera"]["status"] == "pending"
    kinds = [e["kind"] for e in client.get(f"/api/timeline?case_id={cid}").json()]
    for k in ("case_opened", "drone_requested", "technician_action", "verification_approved", "stabilization_check", "case_closed"):
        assert k in kinds
    sources = {e["source"] for e in client.get(f"/api/timeline?case_id={cid}").json()}
    assert "simulated" in sources and "human" in sources


def test_tampering_breaks_the_chain(tmp_path):
    from backend.app.store import Store
    s = Store(tmp_path / "t.db")
    s.append("a", "system", {"x": 1})
    s.append("b", "human", {"y": 2}, actor="technician:Amine")
    assert s.verify_chain()["ok"]
    s._db.execute("UPDATE events SET payload = ? WHERE seq = 1", ('{"x":999}',))
    s._db.commit()
    v = s.verify_chain()
    assert not v["ok"] and v["broken_at_seq"] == 1


def test_ui_and_static_assets_are_served(client):
    html = client.get("/").text
    assert "app.js" in html and "vendor/chart.umd.js" in html
    for path in ("/app.js", "/styles.css", "/vendor/htm-preact-standalone.js", "/vendor/chart.umd.js"):
        r = client.get(path)
        assert r.status_code == 200 and len(r.content) > 1000, path
    js = client.get("/app.js").text
    # every API path the UI calls must exist on the backend
    import re
    from backend.app.main import app
    routes = {r.path for r in app.routes}
    for p in set(re.findall(r'"(/api/[a-z/_-]+)', js)):
        assert any(rt.startswith(p.rstrip("/")) for rt in routes), p
