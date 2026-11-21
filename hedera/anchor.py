"""Hedera Consensus Service (testnet) anchoring of ARGOS evidence fingerprints.

What goes on Hedera: a small JSON snapshot of the local SHA-256 event chain (chain identifier,
last event number, chain-head digest, UTC time, evidence type). Never sensor data, names or files.
Verification reads the message back from a public Hedera mirror node and compares it with the
stored snapshot AND with a fresh recomputation of the local chain.

Hedera proves that a fingerprint existed at a consensus time. It does not prove that the sensor
readings or incident labels are physically true.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "argos-evidence/1"
MIRROR = {"testnet": "https://testnet.mirrornode.hedera.com"}
STATUSES = ("NOT_ANCHORED", "AWAITING_CONFIRMATION", "VERIFIED", "MISMATCH", "UNAVAILABLE")


class HederaError(RuntimeError):
    pass


def load_env(path: Path = ROOT / ".env") -> dict:
    """Minimal .env reader (no extra dependency). Real environment variables take precedence."""
    vals = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("HEDERA_NETWORK", "HEDERA_ACCOUNT_ID", "HEDERA_PRIVATE_KEY", "HEDERA_TOPIC_ID"):
        if os.environ.get(k):
            vals[k] = os.environ[k]
    return vals


def canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


# ------------------------------------------------------------------ network adapters (replaceable in tests)
class HederaGateway:
    """Submits messages with the official Hedera Python SDK (hiero-sdk-python)."""

    def __init__(self, env: dict | None = None):
        self.env = env if env is not None else load_env()
        self.network = self.env.get("HEDERA_NETWORK", "testnet")
        if self.network != "testnet":
            raise HederaError("ARGOS only anchors on Hedera testnet in this prototype")

    def configured(self) -> tuple[bool, str]:
        acc, key = self.env.get("HEDERA_ACCOUNT_ID", ""), self.env.get("HEDERA_PRIVATE_KEY", "")
        if not acc or "x" in acc or not key:
            return False, "Hedera credentials are missing: set HEDERA_ACCOUNT_ID and HEDERA_PRIVATE_KEY in .env"
        return True, "configured"

    def _client(self):
        from hiero_sdk_python import AccountId, Client, Network, PrivateKey
        ok, why = self.configured()
        if not ok:
            raise HederaError(why)
        key_s = self.env["HEDERA_PRIVATE_KEY"]
        key = None
        for parse in (PrivateKey.from_string_der, PrivateKey.from_string_ecdsa, PrivateKey.from_string_ed25519, PrivateKey.from_string):
            try:
                key = parse(key_s)
                break
            except Exception:
                continue
        if key is None:
            raise HederaError("HEDERA_PRIVATE_KEY could not be parsed (expected DER or hex)")
        client = Client(Network(network="testnet"))
        client.set_operator(AccountId.from_string(self.env["HEDERA_ACCOUNT_ID"]), key)
        return client

    def create_topic(self, memo: str = "ARGOS evidence fingerprints") -> str:
        from hiero_sdk_python import TopicCreateTransaction
        client = self._client()
        try:
            receipt = TopicCreateTransaction().set_memo(memo).execute(client, validate_status=True)
            return str(receipt.topic_id)
        finally:
            client.close()

    def submit(self, topic_id: str, message: str) -> dict:
        from hiero_sdk_python import TopicId, TopicMessageSubmitTransaction
        client = self._client()
        try:
            receipt = (TopicMessageSubmitTransaction().set_topic_id(TopicId.from_string(topic_id))
                       .set_message(message).execute(client, validate_status=True))
            return {"transaction_id": str(receipt.transaction_id), "topic_id": topic_id,
                    "sequence_number": int(receipt.topic_sequence_number)}
        finally:
            client.close()


class MirrorNode:
    """Reads consensus messages from the public Hedera mirror node REST API."""

    def __init__(self, network: str = "testnet", timeout: float = 15):
        self.base, self.timeout = MIRROR[network], timeout

    def message(self, topic_id: str, sequence_number: int) -> dict | None:
        url = f"{self.base}/api/v1/topics/{topic_id}/messages/{sequence_number}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "argos-prototype"}),
                                        timeout=self.timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None                    # not yet visible on the mirror node
            raise HederaError(f"mirror node HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise HederaError(f"mirror node unreachable: {e}") from e


# ------------------------------------------------------------------ anchoring service
class AnchorService:
    def __init__(self, store, gateway: HederaGateway | None = None, mirror: MirrorNode | None = None):
        self.store = store
        self.gateway = gateway or HederaGateway()
        self.mirror = mirror or MirrorNode()

    def chain_id(self) -> str:
        meta = self.store.get_record("meta", "chain")
        if not meta:
            meta = {"id": "chain", "chain_id": f"argos-{uuid.uuid4().hex[:12]}"}
            self.store.put_record("meta", meta)
        return meta["chain_id"]

    def topic_id(self) -> str | None:
        meta = self.store.get_record("meta", "hedera")
        return self.gateway.env.get("HEDERA_TOPIC_ID") or (meta or {}).get("topic_id")

    def anchors(self) -> list[dict]:
        return sorted(self.store.list_records("anchor"), key=lambda a: a["id"], reverse=True)

    def status(self) -> dict:
        ok, why = self.gateway.configured()
        latest = self.anchors()[0] if self.anchors() else None
        return {"network": "testnet", "configured": ok, "config_message": why, "topic_id": self.topic_id(),
                "latest": latest, "local_chain": self.store.verify_chain(),
                "explorer": f"https://hashscan.io/testnet/topic/{self.topic_id()}" if self.topic_id() else None}

    def snapshot(self, evidence_type: str = "event-chain") -> dict:
        v = self.store.verify_chain()
        if not v["ok"]:
            raise HederaError(f"local evidence chain is broken at event {v.get('broken_at_seq')}: not anchoring")
        if not v["events"]:
            raise HederaError("no evidence recorded yet")
        last = self.store.events(limit=1)[-1]
        return {"schema": SCHEMA, "app": "ARGOS", "chain_id": self.chain_id(), "last_seq": last["seq"],
                "head_sha256": last["hash"], "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "evidence_type": evidence_type}

    def anchor(self, evidence_type: str = "event-chain", extra: dict | None = None) -> dict:
        """Submit the current chain head. Idempotent: the same head is never anchored twice."""
        snap = self.snapshot(evidence_type)
        if extra:
            snap.update(extra)
        # Duplicate = an earlier live anchor of the same kind/extra fields, with no new evidence since it,
        # other than ARGOS's own Hedera bookkeeping events (which anchoring itself appends to the chain).
        extra_of = lambda d: {k: v for k, v in d.items() if k not in ("utc", "last_seq", "head_sha256")}
        for a in self.anchors():
            if a["status"] not in ("SUBMITTED", "AWAITING_CONFIRMATION", "VERIFIED") or extra_of(a["snapshot"]) != extra_of(snap):
                continue
            newer = [e for e in self.store.events(limit=100000) if e["seq"] > a["snapshot"]["last_seq"]]
            if all(e["kind"].startswith("hedera_") for e in newer):
                return {**a, "duplicate": True}
        ok, why = self.gateway.configured()
        if not ok:
            raise HederaError(why)
        topic = self.topic_id()
        if not topic:
            topic = self.gateway.create_topic()
            self.store.put_record("meta", {"id": "hedera", "topic_id": topic})
        message = canonical(snap)
        rec = {"id": f"A-{len(self.anchors()) + 1:04d}", "snapshot": snap, "message": message,
               "message_sha256": hashlib.sha256(message.encode()).hexdigest(), "status": "PENDING", "topic_id": topic}
        self.store.put_record("anchor", rec)                 # persisted before submission (retry safety)
        try:
            res = self.gateway.submit(topic, message)
        except Exception as e:
            rec.update(status="FAILED", error=str(e)[:300])
            self.store.put_record("anchor", rec)
            raise HederaError(f"Hedera submission failed: {e}") from e
        rec.update(status="SUBMITTED", **res, submitted_at=snap["utc"])
        self.store.put_record("anchor", rec)
        self.store.append("hedera_anchor_submitted", "system", {"anchor": rec["id"], "topic_id": topic,
                          "transaction_id": res["transaction_id"], "sequence_number": res["sequence_number"],
                          "head_sha256": snap["head_sha256"], "last_seq": snap["last_seq"], "evidence_type": evidence_type})
        return rec

    def verify(self, anchor_id: str) -> dict:
        rec = self.store.get_record("anchor", anchor_id)
        if not rec:
            raise KeyError(anchor_id)
        if rec.get("status") in ("PENDING", "FAILED") or rec.get("sequence_number") is None:
            return {**rec, "verification": {"status": "NOT_ANCHORED", "detail": "No confirmed submission for this snapshot."}}
        result = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            msg = self.mirror.message(rec["topic_id"], rec["sequence_number"])
        except HederaError as e:
            result.update(status="UNAVAILABLE", detail=str(e))
            rec["verification"] = result
            self.store.put_record("anchor", rec)
            return rec
        if msg is None:
            result.update(status="AWAITING_CONFIRMATION", detail="The mirror node does not show this message yet. Try again in a few seconds.")
        else:
            onchain = base64.b64decode(msg["message"]).decode("utf-8", "replace")
            local_hash = self.store.hash_at(rec["snapshot"]["last_seq"])
            checks = {"message_matches_stored_snapshot": onchain == rec["message"],
                      "local_chain_recomputed_matches": local_hash == rec["snapshot"]["head_sha256"],
                      "local_chain_intact": self.store.verify_chain()["ok"]}
            result.update(status="VERIFIED" if all(checks.values()) else "MISMATCH", checks=checks,
                          consensus_timestamp=msg.get("consensus_timestamp"), running_hash=msg.get("running_hash"),
                          detail="On-chain fingerprint matches the stored evidence." if all(checks.values())
                          else "The evidence no longer matches the fingerprint recorded on Hedera.")
            rec["consensus_timestamp"] = msg.get("consensus_timestamp")
            rec["status"] = "VERIFIED" if all(checks.values()) else "MISMATCH"
        rec["verification"] = result
        self.store.put_record("anchor", rec)
        self.store.append("hedera_verification", "system", {"anchor": anchor_id, "status": result["status"]})
        return rec
