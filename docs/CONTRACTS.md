# Data contracts

The code is the source of truth: [`backend/app/schemas.py`](../backend/app/schemas.py). This page explains it. If the two disagree, the code wins: fix this page.

All timestamps are **timezone-aware UTC** (naive datetimes are rejected). Unknown fields are rejected. Units are carried in field names.

## Flow

```
SensorReading ──► AI ──► Anomaly ──► Risk engine ──► RiskEvent
                                                        │
                    ┌───────────────────────────────────┼────────────────────┐
                    ▼                                   ▼                    ▼
              DroneMission (+Evidence)            SafetyCase          Fire Pack (CRITICAL)
                                          (3 Signatures, MEL, timeline)
                                                        │
                                                        ▼
                                              HederaAnchor (SHA-256 only)
```

## Site (`backend/app/data/site.json`, fictional demo factory)
| Model | Key fields |
|---|---|
| `Site` | 120 m × 70 m; zones, assets, docking stations, emergency exits, hazardous materials, emergency contacts |
| `Zone` | `id`, `name`, `area` (rectangle in metres) |
| `Asset` | `id`, `type` (`electrical_panel`, `motor`, `compressor`, `storage`), `zone_id`, `criticality` 1–5, `position`, `nominal` (physics), `thresholds` (conventional alarms), `has_sensors` |
| `Nominal` | physics for the simulator: rated current, ambient temperature, thermal resistance (°C/W), thermal time constant τ (s), electrical resistance (Ω) for I²R heating, base vibration, base gas |
| `Thresholds` | fixed alarm levels: the **baseline the AI must beat** |

Threshold sources:
- Vibration 7.1 mm/s RMS: ISO 10816-3, group 2 machines on flexible foundations, zone C/D boundary.
- Solvent store gas 2,500 ppm: 10 % of the lower explosive limit of acetone (LEL 2.5 % vol).
- Electrical panels 80 °C: conservative alarm for LV switchgear terminals (IEC 61439 limits terminal temperature rise to 70 K).
- Storage rack temperature 57 °C: the activation temperature of standard 57 °C sprinkler bulbs, used as a "too late" reference.

## Telemetry and AI
| Model | Key fields |
|---|---|
| `SensorReading` | `asset_id`, `timestamp`, `temperature_c`, `current_a`, `gas_ppm`, `vibration_mm_s` (missing sensors = `null`), `sensor_health` 0–1, `simulated` |
| `Anomaly` | `anomaly_score`, `is_anomaly`, `contributing_features` (feature → share), `explanation`, `sensor_confidence`, `model_version` |
| `RiskEvent` | `severity` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), `priority_score` 0–100, human-readable `reasons` |

## Drone
| Model | Key fields |
|---|---|
| `DroneMission` | `type` (`EMERGENCY` > `TARGETED` > `SCHEDULED_ROUND`), `status`, `drone_id`, target asset/zone, `priority_score`, `reason`, `evidence` |
| `Evidence` | `kind` (thermal/visual/checklist), `uri`, `max_temperature_c`, `hotspot_detected` |

## Safety cases
| Model | Key fields |
|---|---|
| `SafetyCase` | `status` lifecycle below, `timeline`, `signatures`, `mission_ids`, `mel`, `hedera_refs` |
| `Signature` | `kind` (`technician`, `independent_verifier`, `system`), `signer_id`, `signed_at`, `statement` |
| `MELAuthorization` | `max_load_pct`, `max_duration_h` (≤ 72), `drone_check_interval_min`, `status` |
| `User` | `role`: `technician`, `independent_verifier`, `hse_manager`, `civil_protection`, `system` |

Lifecycle:
```
OPEN → INSPECTED → REPAIR_IN_PROGRESS → REPAIR_DECLARED → VERIFIED → SYSTEM_CONFIRMED → CLOSED
                         ▲                                                   │
                         └──────────── anomaly returns during stabilization ─┘
```
`CLOSED` requires all three signatures; the verifier must not be the technician. MEL is allowed for `MEDIUM` only.

## Hedera
| Model | Key fields |
|---|---|
| `HederaAnchor` | `record_type`, `record_id`, `sha256` (64 hex chars), `topic_id`, `sequence_number`, `consensus_timestamp`, `status` (`pending`, `anchored`, `failed`) |
