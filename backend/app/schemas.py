"""Shared data contracts for AEROGUARD TRUST.

Single source of truth: every module (simulator, ai, backend, hedera, drone, dashboard API)
imports these models instead of redefining them. Units are carried in field names.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)




# ---------------------------------------------------------------- site & assets

class AssetType(str, Enum):
    ELECTRICAL_PANEL = "electrical_panel"
    MOTOR = "motor"
    COMPRESSOR = "compressor"
    STORAGE = "storage"


class Point(_Model):
    x: float = Field(description="metres from the site's west edge")
    y: float = Field(description="metres from the site's north edge")


class Rect(_Model):
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)

    def contains(self, p: Point) -> bool:
        return self.x <= p.x <= self.x + self.width and self.y <= p.y <= self.y + self.height


class Zone(_Model):
    id: str
    name: str
    area: Rect
    description: str = ""


class Thresholds(_Model):
    """Conventional fixed alarm thresholds: the baseline our AI must beat."""
    temperature_c: Optional[float] = None
    current_a: Optional[float] = None
    gas_ppm: Optional[float] = None
    vibration_mm_s: Optional[float] = None


class Nominal(_Model):
    """Physical parameters of a demo-site asset (used for display and physics checks)."""
    rated_current_a: float = Field(ge=0)
    ambient_temp_c: float = 25.0
    thermal_resistance_c_per_w: float = Field(gt=0, description="steady-state °C rise per watt dissipated")
    thermal_time_constant_s: float = Field(gt=0, description="first-order thermal inertia (tau)")
    electrical_resistance_ohm: float = Field(ge=0, description="effective R for I²R Joule heating")
    base_vibration_mm_s: float = Field(ge=0, description="ISO 10816 RMS velocity in normal operation")
    base_gas_ppm: float = Field(ge=0)


class Asset(_Model):
    id: str
    name: str
    type: AssetType
    zone_id: str
    criticality: int = Field(ge=1, le=5)
    position: Point
    nominal: Nominal
    thresholds: Thresholds
    has_sensors: list[str] = Field(description="subset of: temperature, current, gas, vibration")


class DockingStation(_Model):
    id: str
    name: str
    zone_id: str
    position: Point


class EmergencyExit(_Model):
    id: str
    name: str
    position: Point


class HazardousMaterial(_Model):
    id: str
    name: str
    hazard_class: str = Field(description="GHS / ADR style class, e.g. 'Flammable liquid (Class 3)'")
    quantity: str
    zone_id: str
    position: Point


class Site(_Model):
    id: str
    name: str
    location: str
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    zones: list[Zone]
    assets: list[Asset]
    docking_stations: list[DockingStation]
    emergency_exits: list[EmergencyExit]
    hazardous_materials: list[HazardousMaterial]
    emergency_contacts: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------- telemetry & AI

class SensorReading(_Model):
    asset_id: str
    timestamp: AwareDatetime
    temperature_c: Optional[float] = None
    current_a: Optional[float] = None
    gas_ppm: Optional[float] = None
    vibration_mm_s: Optional[float] = None
    sensor_health: float = Field(1.0, ge=0, le=1, description="1 = fully reliable sensor")
    simulated: bool = True



class Anomaly(_Model):
    id: str
    asset_id: str
    timestamp: AwareDatetime
    anomaly_score: float = Field(ge=0)
    is_anomaly: bool
    contributing_features: dict[str, float] = Field(default_factory=dict, description="feature -> share of the score")
    explanation: str = ""
    sensor_confidence: float = Field(1.0, ge=0, le=1)
    model_version: str



class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskEvent(_Model):
    id: str
    anomaly_id: str
    asset_id: str
    timestamp: AwareDatetime
    severity: Severity
    priority_score: float = Field(ge=0, le=100)
    reasons: list[str]



# ---------------------------------------------------------------- drone

class MissionType(str, Enum):
    EMERGENCY = "EMERGENCY"
    TARGETED = "TARGETED"
    SCHEDULED_ROUND = "SCHEDULED_ROUND"


class MissionStatus(str, Enum):
    QUEUED = "QUEUED"
    IN_FLIGHT = "IN_FLIGHT"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class Evidence(_Model):
    kind: str = Field(description="thermal | visual | checklist")
    uri: str
    max_temperature_c: Optional[float] = None
    hotspot_detected: Optional[bool] = None
    notes: str = ""
    captured_at: AwareDatetime


class DroneMission(_Model):
    id: str
    type: MissionType
    status: MissionStatus = MissionStatus.QUEUED
    drone_id: Optional[str] = None
    target_asset_id: Optional[str] = None
    target_zone_id: Optional[str] = None
    priority_score: float = Field(0, ge=0, le=100)
    reason: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    created_at: AwareDatetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------- safety cases

class Role(str, Enum):
    TECHNICIAN = "technician"
    INDEPENDENT_VERIFIER = "independent_verifier"
    HSE_MANAGER = "hse_manager"
    CIVIL_PROTECTION = "civil_protection"
    SYSTEM = "system"


class User(_Model):
    id: str
    name: str
    role: Role


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    INSPECTED = "INSPECTED"
    REPAIR_IN_PROGRESS = "REPAIR_IN_PROGRESS"
    REPAIR_DECLARED = "REPAIR_DECLARED"
    VERIFIED = "VERIFIED"
    SYSTEM_CONFIRMED = "SYSTEM_CONFIRMED"
    CLOSED = "CLOSED"


class SignatureKind(str, Enum):
    TECHNICIAN = "technician"
    INDEPENDENT_VERIFIER = "independent_verifier"
    SYSTEM = "system"


class Signature(_Model):
    kind: SignatureKind
    signer_id: str
    signed_at: AwareDatetime
    statement: str


class CaseTransition(_Model):
    from_status: Optional[CaseStatus]
    to_status: CaseStatus
    at: AwareDatetime
    by: str
    note: str = ""


class MELStatus(str, Enum):
    NONE = "NONE"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    VIOLATED = "VIOLATED"
    REVOKED = "REVOKED"


class MELAuthorization(_Model):
    authorized_by: str
    authorized_at: AwareDatetime
    max_load_pct: float = Field(gt=0, le=100)
    max_duration_h: float = Field(gt=0, le=72)
    drone_check_interval_min: float = Field(gt=0)
    status: MELStatus = MELStatus.ACTIVE


class HederaAnchor(_Model):
    record_type: str
    record_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    topic_id: Optional[str] = None
    sequence_number: Optional[int] = None
    consensus_timestamp: Optional[str] = None
    status: str = Field("pending", description="pending | anchored | failed")


class SafetyCase(_Model):
    id: str
    asset_id: str
    risk_event_id: str
    severity: Severity
    status: CaseStatus = CaseStatus.OPEN
    title: str
    opened_at: AwareDatetime
    timeline: list[CaseTransition] = Field(default_factory=list)
    signatures: list[Signature] = Field(default_factory=list)
    mission_ids: list[str] = Field(default_factory=list)
    mel: Optional[MELAuthorization] = None
    hedera_refs: list[HederaAnchor] = Field(default_factory=list)
