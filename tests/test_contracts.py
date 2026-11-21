"""Part 0 checks: the shared contracts and the demo site are valid and consistent."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.schemas import (
    Anomaly, AssetType, HederaAnchor, MELAuthorization, SafetyCase, SensorReading, Severity,
)
from backend.app.site import load_site

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def site():
    return load_site()


def test_site_has_expected_shape(site):
    assert len(site.zones) == 4
    assert len(site.assets) == 10
    assert len(site.docking_stations) == 2
    assert {a.type for a in site.assets} == set(AssetType)


def test_ids_are_unique(site):
    for items in (site.zones, site.assets, site.docking_stations, site.emergency_exits, site.hazardous_materials):
        ids = [i.id for i in items]
        assert len(ids) == len(set(ids))


def test_everything_sits_inside_its_zone(site):
    zones = {z.id: z for z in site.zones}
    for item in [*site.assets, *site.docking_stations, *site.hazardous_materials]:
        assert item.zone_id in zones, item.id
        assert zones[item.zone_id].area.contains(item.position), f"{item.id} outside {item.zone_id}"


def test_exits_are_on_the_site_boundary(site):
    for e in site.emergency_exits:
        p = e.position
        assert p.x in (0, site.width_m) or p.y in (0, site.height_m), e.id


def test_every_asset_has_a_threshold_for_each_sensor(site):
    field = {"temperature": "temperature_c", "current": "current_a", "gas": "gas_ppm", "vibration": "vibration_mm_s"}
    for a in site.assets:
        assert a.has_sensors, a.id
        for s in a.has_sensors:
            assert getattr(a.thresholds, field[s]) is not None, f"{a.id} missing {s} threshold"


def test_powered_assets_run_cool_at_rated_current(site):
    """Physics sanity: at rated current, the I²R steady state must stay below the fixed alarm."""
    for a in site.assets:
        n = a.nominal
        if n.rated_current_a == 0:
            continue
        steady = n.ambient_temp_c + n.thermal_resistance_c_per_w * n.rated_current_a ** 2 * n.electrical_resistance_ohm
        assert steady < a.thresholds.temperature_c, f"{a.id}: {steady:.1f} °C at rated load"


def test_timestamps_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        SensorReading(asset_id="EP-01", timestamp=datetime(2026, 11, 21, 12, 0), temperature_c=40)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        SensorReading(asset_id="EP-01", timestamp=NOW, temp=40)


def test_contracts_round_trip_through_json():
    a = Anomaly(id="AN-1", asset_id="EP-02", timestamp=NOW, anomaly_score=3.2, is_anomaly=True,
                contributing_features={"temperature_c": 0.8, "current_a": 0.2}, model_version="ae-0.1")
    assert Anomaly.model_validate_json(a.model_dump_json()) == a

    case = SafetyCase(id="SC-1", asset_id="EP-02", risk_event_id="RE-1", severity=Severity.HIGH,
                      title="Panel heating at constant load", opened_at=NOW,
                      mel=MELAuthorization(authorized_by="u-hse", authorized_at=NOW, max_load_pct=70,
                                           max_duration_h=48, drone_check_interval_min=120))
    assert SafetyCase.model_validate_json(case.model_dump_json()) == case


def test_mel_duration_is_capped():
    with pytest.raises(ValidationError):
        MELAuthorization(authorized_by="u", authorized_at=NOW, max_load_pct=70, max_duration_h=200,
                         drone_check_interval_min=60)


def test_hedera_anchor_requires_a_sha256():
    HederaAnchor(record_type="safety_case", record_id="SC-1", sha256="a" * 64)
    with pytest.raises(ValidationError):
        HederaAnchor(record_type="safety_case", record_id="SC-1", sha256="not-a-hash")
