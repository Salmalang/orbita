"""ARGOS controlled learning pipeline: Detect -> Investigate -> Verify -> Preserve -> Learn -> Evaluate.

Training uses verified OFF-CHAIN records; Hedera only holds fingerprints. A record becomes a
training example only when ALL of these hold:
  1. it comes from real sensor data (simulated drone findings are never training data);
  2. a person other than the technician confirmed the real outcome (an explicit label);
  3. the outcome is conclusive;
  4. the local evidence chain is intact AND covered by a Hedera anchor verified on the mirror node;
  5. it is genuinely new: its source recording is not already in the approved training data
     (otherwise it would duplicate, and leak into, the original training/evaluation set);
  6. it is not a duplicate of another eligible incident from the same recording.
Hedera verification alone never makes a record eligible (rule 4 is necessary, not sufficient).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTCOMES = {
    "confirmed_fire": "Confirmed fire",
    "confirmed_nuisance": "Confirmed non-fire (work fumes or nuisance)",
    "confirmed_equipment_anomaly": "Confirmed equipment anomaly",
    "confirmed_normal": "Confirmed normal operation",
    "inconclusive": "Unknown or inconclusive",
}
PROD_MODEL = "zone_fire"


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def training_recordings() -> set[str]:
    """Recordings already used by the approved production model (all Industrial Hall events)."""
    try:
        from ingest.loaders.fire_sensors import load_industrial_hall
        h = load_industrial_hall()
        ev = h[h["scenario"] != "Background"]
        return {f"{s}#{int(e)}" for s, e in ev[["scenario", "experiment"]].dropna().drop_duplicates().itertuples(index=False)}
    except Exception:
        return set()


def check_leakage(train_groups: list[str], test_groups: list[str]) -> dict:
    """Windows of the same original incident/recording must never be split across train and test."""
    overlap = sorted(set(train_groups) & set(test_groups))
    return {"ok": not overlap, "overlap": overlap}


class LearningPipeline:
    def __init__(self, store, anchors, training_recs: set[str] | None = None):
        self.store, self.anchors = store, anchors
        self._training = training_recs

    @property
    def training(self) -> set[str]:
        if self._training is None:
            self._training = training_recordings()
        return self._training

    # ------------------------------------------------------------------ eligibility
    def _case_last_seq(self, case_id: str) -> int:
        ev = self.store.events(case_id=case_id, limit=10000)
        return max((e["seq"] for e in ev), default=0)

    def _verified_coverage(self) -> int:
        return max((a["snapshot"]["last_seq"] for a in self.store.list_records("anchor") if a.get("status") == "VERIFIED"), default=0)

    def assess(self) -> list[dict]:
        chain_ok = self.store.verify_chain()["ok"]
        covered = self._verified_coverage()
        seen, rows = set(), []
        for c in sorted(self.store.cases(), key=lambda c: c["opened_wall_ts"]):
            out = c.get("outcome")
            rec = {"incident_id": c["id"], "equipment": c["zone"], "kind": c.get("kind", "SENSOR_ALERT"),
                   "recording": c.get("replay_event"), "sensor_window_start": c.get("opened_data_ts"),
                   "model_version": (c.get("evidence") or {}).get("model"),
                   "ai_prediction": {"fire_nodes": c.get("fire_nodes"), "severity": c.get("severity")},
                   "technician_diagnosis": (c.get("action") or {}).get("text"),
                   "verifier": c.get("verifier"), "outcome": (out or {}).get("label"),
                   "outcome_confirmed_by": (out or {}).get("by"),
                   "provenance": "simulated drone finding" if c.get("kind") == "INSPECTION_FINDING" else "staged experiment, historical replay",
                   "integrity": {"local_chain_ok": chain_ok, "hedera_verified_through_seq": covered,
                                 "incident_last_seq": self._case_last_seq(c["id"])}}
            reasons = []
            if rec["kind"] != "SENSOR_ALERT":
                reasons.append("Simulated drone finding: never used as AI training data")
            if not out:
                state = "AWAITING_OUTCOME"
                reasons.append("Waiting for an authorized person to confirm what really happened")
            else:
                state = "EXCLUDED"
                if out["label"] == "inconclusive":
                    reasons.append("Outcome inconclusive")
                if out.get("by") and out["by"].lower() == (c.get("technician") or "").lower():
                    reasons.append("Outcome confirmed by the technician who did the work")
            if not chain_ok:
                reasons.append("Local evidence chain is broken")
            elif rec["integrity"]["incident_last_seq"] > covered:
                reasons.append("Evidence not yet anchored and verified on Hedera")
            if rec["recording"] and rec["recording"] in self.training:
                reasons.append(f"Duplicate: recording {rec['recording']} is already in the approved training data (would leak into evaluation)")
            if rec["recording"] and rec["recording"] in seen:
                reasons.append("Duplicate of another incident from the same recording")
            if rec["recording"]:
                seen.add(rec["recording"])
            if out and not reasons:
                state = "ELIGIBLE"
            elif out and reasons:
                state = "EXCLUDED"
            rows.append({**rec, "state": state, "reasons": reasons})
        return rows

    # ------------------------------------------------------------------ dataset manifest
    def current_model(self) -> dict:
        from ai import registry
        card = next((c for c in registry.cards() if c["name"] == PROD_MODEL), None)
        if not card:
            return {"available": False}
        nested = card["metrics"].get("nested_estimate", {})
        return {"available": True, "name": card["name"], "version": card["version"], "status": "production (approved baseline)",
                "model_sha256": card["model_sha256"], "training_data_sha256": card["training_data_sha256"],
                "summary": {"fires_detected": f"{nested.get('fires_detected')}/{nested.get('fire_events')}",
                            "nuisance_alarms": f"{nested.get('nuisance_false_alarms')}/{nested.get('nuisance_events')}"}}

    def prepare_dataset(self) -> dict:
        rows = self.assess()
        eligible = [r for r in rows if r["state"] == "ELIGIBLE"]
        base = self.current_model()
        n = len(self.store.list_records("dataset")) + 1
        manifest = {
            "schema": "argos-dataset/1", "dataset_version": f"DS-{n:04d}",
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "base_dataset": {"name": "Industrial Hall (doi:10.17632/yghykzm4km.1)", "training_data_sha256": base.get("training_data_sha256"),
                             "used_by_model": f"{base.get('name')}/{base.get('version')}"},
            "new_examples": [{k: r[k] for k in ("incident_id", "recording", "sensor_window_start", "model_version", "outcome",
                                                 "outcome_confirmed_by", "provenance")} for r in eligible],
            "excluded": [{"incident_id": r["incident_id"], "state": r["state"], "reasons": r["reasons"]} for r in rows if r["state"] != "ELIGIBLE"],
            "split_policy": "grouped by source recording; no recording in both training and test",
            "leakage_check": check_leakage([r["recording"] for r in eligible], sorted(self.training)) if eligible else {"ok": True, "overlap": []},
            "evidence_anchor_coverage_seq": self._verified_coverage(),
        }
        digest = _sha(manifest)
        rec = {"id": manifest["dataset_version"], "manifest": manifest, "sha256": digest, "new_examples": len(eligible)}
        self.store.put_record("dataset", rec)
        self.store.append("learning_dataset_prepared", "system", {"dataset_version": rec["id"], "sha256": digest,
                                                                 "new_examples": len(eligible), "excluded": len(manifest["excluded"])})
        return rec

    def verify_dataset(self, version: str) -> dict:
        rec = self.store.get_record("dataset", version)
        if not rec:
            raise KeyError(version)
        ok = _sha(rec["manifest"]) == rec["sha256"]
        return {"dataset_version": version, "manifest_hash_ok": ok, "sha256": rec["sha256"],
                "anchored": [a["id"] for a in self.store.list_records("anchor") if a["snapshot"].get("dataset_sha256") == rec["sha256"]]}

    def datasets(self) -> list[dict]:
        return sorted(self.store.list_records("dataset"), key=lambda d: d["id"], reverse=True)

    def train_candidate(self, version: str) -> dict:
        """Refuses to 'learn' without genuinely new verified examples; never fabricates a model or results."""
        rec = self.store.get_record("dataset", version)
        if not rec:
            raise KeyError(version)
        if not self.verify_dataset(version)["manifest_hash_ok"]:
            raise ValueError("dataset manifest was modified after it was prepared")
        if rec["new_examples"] == 0:
            raise ValueError("No genuinely new verified incidents in this dataset. Training would only reproduce the "
                             "current model, so no candidate was trained. ARGOS needs confirmed field incidents to learn.")
        raise ValueError("Candidate training from field incidents is prepared but not enabled in this prototype: "
                         "it requires real field recordings, which the demo does not contain.")
