"""Part 2 checks: the AI models behave as reported on the real data.

The thresholds below are floors well under the measured results, so the tests catch regressions
without hard-coding exact numbers. Skipped on a fresh clone until the data is downloaded.
"""
import json

import numpy as np
import pytest

from ai.common import persistent
from ingest.download import RAW

needs = lambda ds: pytest.mark.skipif(not (RAW / ds).exists(), reason=f"run: python -m ingest download {ds}")


def test_persistent_requires_consecutive_samples():
    f = np.array([1, 1, 0, 1, 1, 1, 0], dtype=bool)
    assert persistent(f, 3).tolist() == [False, False, False, False, False, True, False]
    assert persistent(f, 1).tolist() == f.tolist()


@needs("indoor_lab_fire")
def test_early_warning_beats_detector_on_every_electrical_fire():
    from ai import lead_time as L
    from ingest.loaders.fire_sensors import load_indoor_lab
    res = L.evaluate(load_indoor_lab())
    elec = res[res["source"] == "electrical"]
    assert elec["warned_before_detector"].all()
    assert (elec["lead_time_s"] > 120).all()               # at least 2 minutes earlier, each time
    assert not res.loc[~res["detector_before_calibration_end"], "false_warning_in_stage0"].any()


@needs("metropt3")
def test_compressor_autoencoder_detects_real_failures():
    from ai import compressor as C
    from ingest.loaders.machines import METROPT3_FAILURES, load_metropt3
    feats = C.window_features(load_metropt3().set_index("timestamp"))
    assert (feats.index < C.TRAIN_END).sum() > 1000          # enough normal windows to learn from
    summary, res = C.evaluate(feats, METROPT3_FAILURES, C.AutoencoderScorer())
    assert summary["detected"] >= 3
    assert summary["detected_before_start"] >= 1
    assert summary["false_alarms_per_week"] < 2


@needs("skab")
def test_motor_autoencoder_catches_anomalies_with_fewer_false_alarms_than_sigma_limits():
    from ai import motor as M
    from ingest.loaders.machines import load_skab
    t = M.compare(load_skab()).set_index("method")
    ae, sig = t.loc["MLP autoencoder"], t.loc["Fixed k-sigma limits"]
    assert ae["f1"] > 0.7
    assert ae["false_alarm_rate"] < sig["false_alarm_rate"]


def test_registry_cards_trace_training_data():
    from ai.registry import REGISTRY
    cards = [json.loads(p.read_text(encoding="utf-8")) for p in REGISTRY.glob("*/*/card.json")]
    if not cards:
        pytest.skip("run: python -m ai.train")
    for c in cards:
        assert len(c["model_sha256"]) == 64 and len(c["training_data_sha256"]) == 64
        assert c["training_data"] and all(c["training_data"].values()), c["name"]
        assert c["metrics"]


def test_registry_rejects_a_tampered_model(tmp_path, monkeypatch):
    from ai import registry
    monkeypatch.setattr(registry, "REGISTRY", tmp_path)
    monkeypatch.setattr(registry, "MANIFEST", tmp_path / "none.json")
    registry.save("demo", "1.0.0", {"w": [1, 2, 3]}, metrics={"m": 1}, config={}, datasets=[], description="t")
    model, card = registry.load("demo")
    assert model == {"w": [1, 2, 3]}
    (tmp_path / "demo" / "1.0.0" / "model.joblib").write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="does not match"):
        registry.load("demo")


@needs("industrial_hall_fire")
def test_inference_flags_a_real_cable_fire_and_not_quiet_background():
    from ai.registry import REGISTRY
    if not (REGISTRY / "zone_fire").exists():
        pytest.skip("run: python -m ai.train")
    import pandas as pd
    from ai.inference import ZoneFireDetector
    from ingest.loaders.fire_sensors import load_industrial_hall
    hall = load_industrial_hall()
    det = ZoneFireDetector()
    ev = hall[(hall["scenario"] == "Cable") & (hall["experiment"] == 4)]
    start, end = ev["timestamp"].min(), ev["timestamp"].max()
    window = hall[hall["timestamp"].between(start - pd.Timedelta("30min"), end)]
    assert det.assess(window)["fire_alarm"]
    # Functional check of the runtime API (the final model saw all data; performance figures come
    # from the leave-one-event-out evaluation in ai/reports). The hall is recorded continuously and
    # nights have no events. Take the first night, from 70 min
    # after the last event of the day until the first event of the next morning.
    evs = hall[hall["scenario"] != "Background"].groupby(["scenario", "experiment"])["timestamp"].agg(["min", "max"])
    evs = evs.sort_values("min").reset_index(drop=True)
    gaps = pd.DataFrame({"from": evs["max"].shift() + pd.Timedelta("70min"), "to": evs["min"]}).dropna()
    night = gaps.loc[(gaps["to"] - gaps["from"]).idxmax()]
    assert night["to"] - night["from"] > pd.Timedelta("10h")
    quiet = hall[(hall["timestamp"] >= night["from"]) & (hall["timestamp"] < night["to"])]
    assert quiet["scenario"].eq("Background").all()
    assert not det.assess(quiet)["fire_alarm"]
