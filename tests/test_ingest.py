"""Part 1 checks: real datasets are registered, intact, and load into the expected shape.

Data tests are skipped on a fresh clone until `python -m ingest download` has been run.
"""
import json

import numpy as np
import pytest

from ingest.download import MANIFEST, RAW, sha256_of
from ingest.registry import DATASETS

needs = lambda ds: pytest.mark.skipif(not (RAW / ds).exists(), reason=f"run: python -m ingest download {ds}")


# ----------------------------------------------------------------- registry & integrity

def test_every_dataset_is_credited():
    assert len(DATASETS) == 7
    for d in DATASETS.values():
        assert d.page.startswith("https://") and d.license and d.citation and d.used_for and d.files


def test_mendeley_files_have_publisher_hashes():
    for d in DATASETS.values():
        for f in d.files:
            if "mendeley.com" in f.url:
                assert f.sha256 and len(f.sha256) == 64, f"{d.id}/{f.name}"


@pytest.mark.skipif(not MANIFEST.exists(), reason="no downloads yet")
def test_downloaded_files_match_manifest_hashes():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for ds_id, entry in manifest.items():
        for f in entry["files"]:
            assert sha256_of(RAW / ds_id / f["file"]) == f["sha256"], f"{ds_id}/{f['file']} changed on disk"


# ----------------------------------------------------------------- fire sensor datasets

@needs("industrial_hall_fire")
def test_industrial_hall_fire_vs_nuisance_labels():
    from ingest.loaders.fire_sensors import FIRE_SCENARIOS, NUISANCE_SCENARIOS, load_industrial_hall
    df = load_industrial_hall()
    assert len(df) == 248_502 and df["sensor_id"].nunique() == 9
    assert {"Cable", "Welding", "Abrasive_Cutting"} <= set(df["scenario"])
    assert df.loc[df["scenario"].isin(FIRE_SCENARIOS), "is_fire"].mean() > 0.5
    assert not df.loc[df["scenario"].isin(NUISANCE_SCENARIOS), "is_fire"].any()
    assert str(df["timestamp"].dt.tz) == "UTC"


@needs("indoor_lab_fire")
def test_indoor_lab_has_baseline_detector():
    from ingest.loaders.fire_sensors import load_indoor_lab
    df = load_indoor_lab()
    assert df["experiment"].nunique() == 8
    assert df.groupby("source")["experiment"].nunique().to_dict() == {"carton": 2, "clothing": 2, "electrical": 4}
    assert df["detector_on"].dtype == bool and df.groupby("experiment")["detector_on"].any().all()
    assert (df.groupby("experiment")["t_s"].apply(lambda s: s.is_monotonic_increasing)).all()


@needs("test_chamber_fire")
def test_test_chamber_intensity_stages():
    from ingest.loaders.fire_sensors import load_test_chamber
    df = load_test_chamber()
    # The publisher's description says "up to 6 stages"; the published file actually reaches 4.
    assert len(df) == 2900 and df["intensity"].min() == 1 and df["intensity"].max() == 4
    assert {"co_ppm", "co2_ppm", "temperature_c", "co_trend"} <= set(df.columns)


# ----------------------------------------------------------------- machines

@needs("skab")
def test_skab_experiments():
    from ingest.loaders.machines import SKAB_FEATURES, load_skab
    exps = load_skab()
    assert len(exps) == 35
    normal = exps[0]
    assert normal.group == "anomaly-free" and normal.data["anomaly"].sum() == 0
    assert all(set(SKAB_FEATURES) <= set(e.data.columns) for e in exps)
    assert sum(e.data["anomaly"].sum() > 0 for e in exps[1:]) >= 30


@needs("metropt3")
def test_metropt3_has_the_four_reported_failures():
    from ingest.loaders.machines import METROPT3_FAILURES, load_metropt3
    df = load_metropt3()
    assert len(METROPT3_FAILURES) == 4
    assert df["timestamp"].min().month == 2 and df["failure"].any()
    for f in METROPT3_FAILURES.itertuples():
        assert df.loc[df["timestamp"].between(f.start, f.end), "failure"].all()


# ----------------------------------------------------------------- thermal images & accidents

@needs("motor_thermal")
def test_motor_thermal_images():
    from ingest.loaders.thermal import CONDITIONS, list_motor_thermal_images, read_image
    imgs = list_motor_thermal_images()
    assert len(imgs) == 369 and imgs["folder"].nunique() == len(CONDITIONS)
    assert (~imgs["is_fault"]).sum() == 25
    assert read_image(imgs["path"].iloc[0]).shape == (240, 320, 3)


@needs("aria")
def test_aria_fire_statistics():
    from ingest.loaders.accidents import fire_statistics, load_aria
    df = load_aria()
    assert len(df) > 50_000 and df["is_fire"].sum() > 20_000
    stats = fire_statistics(df)
    assert stats["top_primary_causes"].iloc[0] > 1000


# ----------------------------------------------------------------- physics on real data

def test_thermal_model_steady_state_formula():
    from physics.thermal import FirstOrderThermalModel
    m = FirstOrderThermalModel(a=0.05, b=0.1)
    assert m.steady_rise(4.0) == pytest.approx(8.0)
    assert m.tau_s == pytest.approx(600.0)


@needs("metropt3")
def test_thermal_model_identified_on_real_compressor_is_physical():
    from ingest.loaders.machines import load_metropt3
    from physics.thermal import FirstOrderThermalModel, ambient_proxy, r2
    m = load_metropt3().set_index("timestamp").asfreq("1min")
    T, I = m["oil_temperature_c"].to_numpy(), m["motor_current_a"].to_numpy()
    Ta = ambient_proxy(m["oil_temperature_c"]).to_numpy()
    train = m.index < "2020-04-01"
    model = FirstOrderThermalModel().fit(T[train], I[train], Ta[train])
    assert 5 * 60 < model.tau_s < 60 * 60           # thermal time constant between 5 and 60 min
    assert 10 < model.steady_rise(7.0) < 80          # loaded-compressor oil rise in kelvin
    pred = model.predict_with_resets(T, I, Ta, horizon=60)
    assert r2(T[~train], pred[~train]) > 0.3
    measured = ~train & np.isfinite(T)   # the logger has real gaps; judge coverage where data exists
    assert np.isfinite(pred[measured]).mean() > 0.9
