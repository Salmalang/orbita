"""Hedera evidence anchoring (network mocked) and the controlled learning pipeline."""
import base64

import pytest

from backend.app.cases import CaseManager, WorkflowError
from backend.app.store import Store
from hedera.anchor import AnchorService, HederaError, HederaGateway
from learning.pipeline import LearningPipeline, check_leakage

ENV = {"HEDERA_NETWORK": "testnet", "HEDERA_ACCOUNT_ID": "0.0.1001", "HEDERA_PRIVATE_KEY": "302e-test", "HEDERA_TOPIC_ID": "0.0.5005"}


class FakeGateway(HederaGateway):
    def __init__(self, env=ENV, fail=False):
        super().__init__(dict(env))
        self.sent, self.fail = [], fail

    def submit(self, topic_id, message):
        if self.fail:
            raise RuntimeError("INVALID_SIGNATURE")
        self.sent.append(message)
        return {"transaction_id": f"0.0.1001@1700000000.{len(self.sent):09d}", "topic_id": topic_id, "sequence_number": len(self.sent)}

    def create_topic(self, memo=""):
        return "0.0.5005"


class FakeMirror:
    def __init__(self, gw):
        self.gw, self.mode = gw, "ok"

    def message(self, topic_id, seq):
        if self.mode == "down":
            raise HederaError("mirror node unreachable: timeout")
        if self.mode == "missing":
            return None
        msg = self.gw.sent[seq - 1] if self.mode == "ok" else '{"tampered":true}'
        return {"message": base64.b64encode(msg.encode()).decode(), "consensus_timestamp": "1700000001.000000001",
                "running_hash": "ab", "sequence_number": seq}


@pytest.fixture
def svc(tmp_path):
    st = Store(tmp_path / "h.db")
    st.append("demo", "system", {"x": 1})
    st.append("demo", "human", {"y": 2}, actor="technician:A")
    gw = FakeGateway()
    return AnchorService(st, gw, FakeMirror(gw)), st, gw


# ----------------------------------------------------------------- Hedera
def test_missing_credentials_are_reported_not_faked(tmp_path):
    st = Store(tmp_path / "c.db")
    st.append("demo", "system", {"x": 1})
    s = AnchorService(st, HederaGateway({"HEDERA_NETWORK": "testnet", "HEDERA_ACCOUNT_ID": "0.0.xxxxxxx"}), None)
    assert not s.status()["configured"]
    with pytest.raises(HederaError, match="credentials are missing"):
        s.anchor()
    assert s.anchors() == []


def test_anchor_submits_fingerprint_only_and_persists_receipt(svc):
    s, st, gw = svc
    a = s.anchor()
    assert a["status"] == "SUBMITTED" and a["transaction_id"].startswith("0.0.1001@") and a["sequence_number"] == 1
    assert '"head_sha256"' in gw.sent[0] and "technician" not in gw.sent[0]          # no identities, only fingerprints
    assert a["snapshot"]["head_sha256"] == st.hash_at(a["snapshot"]["last_seq"])


def test_duplicate_anchoring_is_prevented(svc):
    s, st, gw = svc
    a1 = s.anchor()
    a2 = s.anchor()
    assert a2["duplicate"] and a2["id"] == a1["id"] and len(gw.sent) == 1


def test_mirror_verification_statuses(svc):
    s, st, gw = svc
    a = s.anchor()
    assert s.verify(a["id"])["verification"]["status"] == "VERIFIED"
    s.mirror.mode = "missing"
    assert s.verify(a["id"])["verification"]["status"] == "AWAITING_CONFIRMATION"
    s.mirror.mode = "down"
    assert s.verify(a["id"])["verification"]["status"] == "UNAVAILABLE"
    s.mirror.mode = "wrong"
    assert s.verify(a["id"])["verification"]["status"] == "MISMATCH"


def test_local_tampering_is_detected_against_hedera(svc):
    s, st, gw = svc
    a = s.anchor()
    st._db.execute("UPDATE events SET payload = ? WHERE seq = 1", ('{"x":999}',))
    st._db.commit()
    v = s.verify(a["id"])["verification"]
    assert v["status"] == "MISMATCH" and v["checks"]["message_matches_stored_snapshot"] and not v["checks"]["local_chain_recomputed_matches"]


def test_submission_failure_is_recorded_and_raised(tmp_path):
    st = Store(tmp_path / "f.db")
    st.append("demo", "system", {"x": 1})
    s = AnchorService(st, FakeGateway(fail=True), None)
    with pytest.raises(HederaError, match="submission failed"):
        s.anchor()
    assert s.anchors()[0]["status"] == "FAILED"
    assert s.verify(s.anchors()[0]["id"])["verification"]["status"] == "NOT_ANCHORED"


def test_testnet_only(tmp_path):
    with pytest.raises(HederaError):
        HederaGateway({"HEDERA_NETWORK": "mainnet"})


# ----------------------------------------------------------------- learning pipeline
def _sensor_case(cm, recording, tech="Tech A", verifier="Ver B"):
    c = cm.open_case(zone="HALL-A", event_id=recording, data_ts="2023-07-12T13:53:50+00:00",
                     decision={"level": "CRITICAL", "reasons": ["r"], "fire_nodes": ["n1", "n2"]}, snapshot={"model": "m"})
    cm.record_action(c["id"], tech, "Isolated circuit and removed burnt insulation", None)
    cm.verify(c["id"], verifier, True, "ok", None)
    return c["id"]


@pytest.fixture
def lp(svc):
    s, st, gw = svc
    cm = CaseManager(st)
    return LearningPipeline(st, s, training_recs={"Cable#4", "Wood#1"}), cm, s, st


def test_outcome_requires_independent_person_and_valid_label(lp):
    pipe, cm, s, st = lp
    cid = _sensor_case(cm, "Cable#4")
    with pytest.raises(WorkflowError):
        cm.confirm_outcome(cid, "Tech A", "confirmed_fire", "")
    with pytest.raises(WorkflowError):
        cm.confirm_outcome(cid, "Ver B", "probably_fire", "")


def test_eligibility_rules(lp):
    pipe, cm, s, st = lp
    dup = _sensor_case(cm, "Cable#4")                     # recording already in the training data
    new = _sensor_case(cm, "Field#1")                      # genuinely new recording
    waiting = _sensor_case(cm, "Field#2")                  # no outcome yet
    inc = _sensor_case(cm, "Field#3")
    for cid in (dup, new):
        cm.confirm_outcome(cid, "Ver B", "confirmed_fire", "seen on site")
    cm.confirm_outcome(inc, "Ver B", "inconclusive", "")
    state = {r["incident_id"]: r for r in pipe.assess()}
    assert state[waiting]["state"] == "AWAITING_OUTCOME"
    assert state[dup]["state"] == "EXCLUDED" and any("already in the approved training data" in x for x in state[dup]["reasons"])
    assert state[inc]["state"] == "EXCLUDED"
    # labelled and new, but evidence not yet verified on Hedera -> not eligible (Hedera is necessary)
    assert state[new]["state"] == "EXCLUDED" and any("Hedera" in x for x in state[new]["reasons"])
    a = s.anchor()
    s.verify(a["id"])
    state = {r["incident_id"]: r for r in pipe.assess()}
    assert state[new]["state"] == "ELIGIBLE"
    # Hedera is not sufficient: the duplicate stays excluded even with verified evidence
    assert state[dup]["state"] == "EXCLUDED"


def test_simulated_findings_never_become_training_data(lp):
    pipe, cm, s, st = lp
    f = {"id": "F-0001", "mission_id": "M-1", "checkpoint": "CP-EE", "checkpoint_label": "East door", "type_label": "Obstructed exit",
         "severity": "MEDIUM", "note": "", "recorded_at": "t", "recorded_by": "op"}
    c = cm.open_finding_case(zone="HALL-A", finding=f, opened_by="op")
    row = next(r for r in pipe.assess() if r["incident_id"] == c["id"])
    assert any("Simulated" in x for x in row["reasons"])


def test_dataset_manifest_hash_and_no_fake_training(lp):
    pipe, cm, s, st = lp
    _sensor_case(cm, "Cable#4")
    d = pipe.prepare_dataset()
    assert d["new_examples"] == 0 and len(d["sha256"]) == 64
    assert pipe.verify_dataset(d["id"])["manifest_hash_ok"]
    with pytest.raises(ValueError, match="No genuinely new verified incidents"):
        pipe.train_candidate(d["id"])
    d["manifest"]["new_examples"].append({"incident_id": "forged"})
    st.put_record("dataset", d)
    assert not pipe.verify_dataset(d["id"])["manifest_hash_ok"]
    with pytest.raises(ValueError, match="modified"):
        pipe.train_candidate(d["id"])


def test_dataset_anchor_is_distinct_from_chain_anchor(lp):
    pipe, cm, s, st = lp
    d = pipe.prepare_dataset()
    a1 = s.anchor()
    a2 = s.anchor("dataset-manifest", {"dataset_version": d["id"], "dataset_sha256": d["sha256"]})
    assert a1["id"] != a2["id"] and a2["snapshot"]["dataset_sha256"] == d["sha256"]


def test_leakage_check():
    assert check_leakage(["Field#1"], ["Cable#4"])["ok"]
    assert check_leakage(["Cable#4", "Field#1"], ["Cable#4"]) == {"ok": False, "overlap": ["Cable#4"]}
