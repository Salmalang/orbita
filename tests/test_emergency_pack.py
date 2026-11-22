"""Firefighter Emergency Pack: QR link, access control, briefing content, map labels, PDF."""
import io
import json
import time

import pytest

from backend.app import emergency
from backend.app.emergency import PackError, PackService
from backend.app.store import Store


# ----------------------------------------------------------------- end to end on the real Cable#4 replay
@pytest.fixture(scope="module")
def fire(tmp_path_factory):
    from fastapi.testclient import TestClient
    from backend.app import main
    import os
    os.environ["ARGOS_PACK_DIR"] = str(tmp_path_factory.mktemp("packs"))
    rt = main.Runtime(db_path=tmp_path_factory.mktemp("db") / "pack.db", simulate_drone=False)
    main.use_runtime(rt)
    with TestClient(main.app) as c:
        c.post("/api/demo/reset")
        c.post("/api/replay/load", json={"event_id": "Cable#4"})
        case = None
        for _ in range(400):
            c.post("/api/replay/step", json={"ticks": 1})
            cases = c.get("/api/cases").json()
            if cases:
                case = cases[0]
                break
        assert case and case["severity"] == "CRITICAL"
        yield c, case, rt


def test_pack_is_issued_automatically_for_a_critical_fire_case(fire):
    c, case, rt = fire
    v = c.get(f"/api/cases/{case['id']}/pack").json()
    assert v["eligible"] and v["state"] == "ACTIVE" and v["auto"] is True and v["demo_access"]
    assert v["qr_url"].startswith("http") and f"/pack/{case['id']}?t=" in v["qr_url"]
    kinds = [e["kind"] for e in rt.store.events(case_id=case["id"])]
    assert "emergency_pack_issued" in kinds
    # the token never enters the evidence chain
    token = v["qr_url"].split("t=")[1]
    assert token not in json.dumps(rt.store.events(limit=100000))


def test_qr_encodes_only_the_url(fire):
    c, case, rt = fire
    v = c.get(f"/api/cases/{case['id']}/pack").json()
    r = c.get(f"/api/cases/{case['id']}/pack/qr.png")
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    import segno
    assert segno.make(v["qr_url"], error="m").matrix == tuple(bytearray(x) for x in emergency.qr_matrix(v["qr_url"]))
    assert len(v["qr_url"]) < 200                                  # a URL, not the briefing data


def test_responder_access_requires_a_valid_token(fire):
    c, case, rt = fire
    v = c.get(f"/api/cases/{case['id']}/pack").json()
    token = v["qr_url"].split("t=")[1]
    assert c.get(f"/api/pack/{case['id']}").status_code == 401
    assert c.get(f"/api/pack/{case['id']}?t=garbage").status_code == 401
    jti, exp, sig = token.split(".")
    assert c.get(f"/api/pack/{case['id']}?t={jti}.{int(exp) + 9999}.{sig}").status_code == 401     # tampered expiry
    assert c.get(f"/api/pack/SC-9999?t={token}").status_code == 401                                 # bound to the incident
    ok = c.get(f"/api/pack/{case['id']}?t={token}")
    assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"
    assert c.get(f"/pack/{case['id']}").status_code == 200                                          # page shell has no data


def test_revoke_and_reissue_invalidate_old_links(fire):
    c, case, rt = fire
    old = c.get(f"/api/cases/{case['id']}/pack").json()["qr_url"].split("t=")[1]
    c.post(f"/api/cases/{case['id']}/pack/revoke")
    assert c.get(f"/api/pack/{case['id']}?t={old}").status_code == 403
    assert c.get(f"/api/cases/{case['id']}/pack").json()["state"] == "REVOKED"     # not silently re-issued
    new = c.post(f"/api/cases/{case['id']}/pack/issue").json()
    assert new["state"] == "ACTIVE" and new["generation"] >= 2
    assert c.get(f"/api/pack/{case['id']}?t={old}").status_code == 403
    assert c.get(f"/api/pack/{case['id']}?t={new['qr_url'].split('t=')[1]}").status_code == 200


def test_briefing_uses_only_real_incident_data(fire):
    c, case, rt = fire
    tok = c.get(f"/api/cases/{case['id']}/pack").json()["qr_url"].split("t=")[1]
    b = c.get(f"/api/pack/{case['id']}?t={tok}").json()
    inc = b["incident"]
    assert inc["id"] == case["id"] and inc["severity"] == "CRITICAL" and inc["detected_recorded_ts"] == case["opened_data_ts"]
    assert inc["replay_event"] == "Cable#4" and inc["historical_replay"]
    # every sensor value comes from the case evidence recorded at detection
    for o in b["sensor_observations"]:
        ev = case["evidence"]["nodes"][o["node"]]
        assert o["p_fire_at_detection"] == round(ev["p_fire"], 3)
        for r in o["readings"]:
            if r["at_detection"] is not None:
                assert abs(r["at_detection"] - ev["readings"][r["key"]]) < 0.01
    assert {o["label"] for o in b["sensor_observations"] if o["fire_signal"]} == set(b["map"]["incident"]["nodes"])
    # facts / hypotheses / unknowns are separated, cause never asserted
    assert b["hypotheses"] and all("basis" in h for h in b["hypotheses"])
    assert any("cause" in u.lower() and "not determined" in u.lower() for u in b["unknowns"])
    assert "not a confirmed fire origin" in b["map"]["incident"]["basis"].lower()
    assert b["drone"]["simulated"] and b["demo"] and "not an approved emergency response plan" in b["not_a_plan"]
    assert "No route is recommended" in b["access"]["route_note"]
    assert b["verification"]["local_chain_ok"] is True
    kinds = [t["kind"] for t in b["timeline"]]
    assert "case_opened" in kinds and "emergency_pack_opened" in kinds


def test_briefing_pdf_is_generated_and_readable(fire):
    c, case, rt = fire
    r = c.get(f"/api/cases/{case['id']}/pack/briefing.pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-" and r.headers["content-type"] == "application/pdf"
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(io.BytesIO(r.content))
    assert len(doc) >= 3
    text = " ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    for needle in (case["id"], "CRITICAL", "DEMONSTRATION", "FLOOR PLAN", "No route is recommended", "SIMULATED", "Unknown"):
        assert needle.lower() in text.lower(), needle
    import os
    assert (os.path.join(os.environ["ARGOS_PACK_DIR"], f"ARGOS_firefighter_briefing_{case['id']}.pdf"))


# ----------------------------------------------------------------- unit level
def _case(**kw):
    base = {"id": "SC-0042", "kind": "SENSOR_ALERT", "severity": "CRITICAL", "status": "OPEN", "zone": "HALL-A",
            "replay_event": "Cable#4", "opened_data_ts": "2023-07-12T13:53:50+00:00", "opened_wall_ts": "2026-11-22T08:00:00+00:00",
            "findings": ["r"], "fire_nodes": ["sensornode0006", "sensornode0007"], "escalations": 0, "missions": [],
            "evidence": {"model": "zone_fire_holdout/cable-4", "nodes": {
                "sensornode0006": {"p_fire": 0.97, "p_nuisance": 0.01, "readings": {"co_ppm": 4.2, "co2_ppm": 600, "pm_total": 900, "temperature_c": 24.1}},
                "sensornode0007": {"p_fire": 0.96, "p_nuisance": 0.02, "readings": {"co_ppm": 3.1, "co2_ppm": 590, "pm_total": 800, "temperature_c": 23.8}},
                "sensornode0012": {"p_fire": 0.02, "p_nuisance": 0.01, "readings": {"co_ppm": 0.1, "co2_ppm": 450, "pm_total": 20, "temperature_c": 22.0}}}}}
    base.update(kw)
    return base


def test_eligibility_only_critical_fire_incidents():
    assert PackService.eligible(_case())[0]
    assert not PackService.eligible(_case(severity="HIGH"))[0]
    assert PackService.eligible(_case(severity="HIGH", escalations=1))[0]
    assert not PackService.eligible(_case(kind="INSPECTION_FINDING"))[0]


def test_token_expiry_and_ineligible_issue(tmp_path):
    st = Store(tmp_path / "t.db")
    svc = PackService(st, ttl_min=1, secret="k")
    rec = svc.issue(_case())
    assert svc.validate("SC-0042", rec["token"])["id"] == "SC-0042"
    rec["exp"] = int(time.time()) - 1                       # simulate the passage of time on the stored record
    st.put_record("emergency_pack", rec)
    jti = rec["jti"]
    expired = f"{jti}.{rec['exp']}.{svc._sign('SC-0042', jti, rec['exp'])}"
    with pytest.raises(PackError) as e:
        svc.validate("SC-0042", expired)
    assert e.value.code == 410
    with pytest.raises(PackError):
        svc.issue(_case(kind="INSPECTION_FINDING"))
    # a different server secret cannot mint valid links
    other = PackService(st, secret="other")
    with pytest.raises(PackError):
        svc.validate("SC-0042", other.issue(_case())["token"].replace(other.get("SC-0042")["jti"], "x"))


def test_links_survive_a_server_restart(tmp_path):
    st = Store(tmp_path / "r.db")
    svc = PackService(st)                                   # service starts with the server
    svc.issue(_case())
    st.reset()                                              # demo reset while the server runs
    tok = svc.issue(_case())["token"]
    restarted = PackService(Store(tmp_path / "r.db"))       # new process, same database
    assert restarted.validate("SC-0042", tok)["id"] == "SC-0042"


def _facility():
    from backend.app.main import FACILITY
    return FACILITY


def test_map_labels_and_demo_marking():
    b = emergency.build_briefing(_case(), facility=_facility(), events=[])
    s = b["map"]["site"]
    assert "fictional" in s["name"].lower() and b["demo"]
    labels = " ".join(x["label"] for k in ("exits", "firefighter_access", "power_isolation", "extinguishers", "hydrants", "assembly_points", "hazards")
                      for x in s[k])
    for word in ("exit", "Fire brigade", "power isolation", "extinguisher", "Hydrant", "Assembly point", "Paint"):
        assert word.lower() in labels.lower(), word
    assert {r["id"] for r in s["rooms"]} >= {"HALL-A", "ELEC", "CORR"}
    # incident area is placed on the flagged sensors (N6, N7) inside Hall A
    inc, hall = b["map"]["incident"], next(r for r in s["rooms"] if r["id"] == "HALL-A")
    assert inc["nodes"] == ["N6", "N7"]
    assert hall["x"] <= inc["x"] <= hall["x"] + hall["w"] and hall["y"] <= inc["y"] <= hall["y"] + hall["h"]
    assert b["access"]["hazards"][0]["distance_m"] <= b["access"]["hazards"][-1]["distance_m"]


def test_no_fabricated_live_values_without_live_data():
    b = emergency.build_briefing(_case(), facility=_facility(), events=[])
    assert not b["live"]["available"]
    for o in b["sensor_observations"]:
        assert o["p_fire_now"] is None and all(r["now"] is None and r["trend"] == "unknown" for r in o["readings"])
    assert [o["label"] for o in b["sensor_observations"]] == ["N6", "N7"]        # non-flagged quiet sensor not listed
    assert any("not playing" in u for u in b["unknowns"])


def test_blocked_exit_from_simulated_finding_is_labelled():
    f = {"id": "F-0003", "mission_id": "M-1", "checkpoint": "CP-EE", "checkpoint_label": "East loading door", "type": "obstructed_exit",
         "type_label": "Obstructed exit", "severity": "MEDIUM", "note": "", "resolved": False}
    b = emergency.build_briefing(_case(), facility=_facility(), events=[], findings=[f])
    bl = b["access"]["blocked"]
    assert bl and "simulated" in bl[0]["source"].lower() and bl[0]["exit"] == "EX-HE"
    assert b["drone"]["findings"][0]["illustrative"]
    resolved = emergency.build_briefing(_case(), facility=_facility(), events=[], findings=[{**f, "resolved": True}])
    assert not resolved["access"]["blocked"]


def test_pdf_offline_without_server_url():
    pdf = emergency.render_pdf(emergency.build_briefing(_case(), facility=_facility(), events=[]), None, None)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 10_000


def test_laptop_view_uses_localhost_and_keeps_token_checks(fire):
    from fastapi.testclient import TestClient
    from backend.app import main
    c, case, rt = fire
    with TestClient(main.app, base_url="http://localhost:8010") as local:
        v = local.get(f"/api/cases/{case['id']}/pack").json()
        assert v["local_url"].startswith(f"http://localhost:8010/pack/{case['id']}?t=")      # reachable on this machine
        assert not v["qr_url"].startswith("http://localhost")                                # phones get a network address
        tok = v["local_url"].split("t=")[1]
        assert local.get(f"/api/pack/{case['id']}?t={tok}&src=console").status_code == 200  # same signed link
        assert local.get(f"/api/pack/{case['id']}?src=console").status_code == 401         # src never replaces the token


def test_ui_wires_clickable_qr_button_and_return_path():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "dashboard"
    app_js, pack_js = (root / "app.js").read_text(encoding="utf-8"), (root / "pack.js").read_text(encoding="utf-8")
    assert 'class="qrlink" href=${firefighterView(v)} target="_blank"' in app_js
    assert "Open Firefighter View" in app_js and "packUrl: firefighterView(v)" in app_js
    assert "Back to incident" in pack_js and 'qs.get("src") === "console"' in pack_js
