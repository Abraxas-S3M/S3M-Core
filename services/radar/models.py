"""Core data models for S3M radar adapter framework.

Military context:
The radar subsystem ingests heterogeneous tactical sensors and must bridge
different payload contracts used across adapters, orchestration, and tests.
These models keep one canonical in-memory shape while preserving backward
compatibility aliases required by existing modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite, log10
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


def _validate_finite(value: float, *, field_name: str) -> float:
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"{field_name} must be a finite number")
    return parsed


def _validate_vec3(value: Any, *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{field_name} must be a 3-tuple")
    x = _validate_finite(value[0], field_name=f"{field_name}[0]")
    y = _validate_finite(value[1], field_name=f"{field_name}[1]")
    z = _validate_finite(value[2], field_name=f"{field_name}[2]")
    return (x, y, z)


def _to_utc(value: Any, *, field_name: str = "timestamp") -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    raise ValueError(f"{field_name} must be a datetime or ISO-8601 string")


class RadarType(str, Enum):
    """Radar hardware types matching tactical integration catalogs."""

    RPS_82 = "rps_82"
    RPS_202 = "rps_202"
    GENERIC_2D = "generic_2d"
    GENERIC_3D = "generic_3d"
    AESA_WESTERN = "aesa_western"
    WESTERN_AESA = "aesa_western"  # Alias used by newer noise presets.
    AESA_PANEL = "aesa_panel"
    DOPPLER_CW = "doppler_cw"
    COUNTER_BATTERY = "counter_battery"
    FIRE_CONTROL = "fire_control"
    AESA = "aesa_western"  # Tactical shorthand alias.
    CUSTOM = "custom"

    @classmethod
    def from_value(cls, value: Any) -> "RadarType":
        if isinstance(value, cls):
            return value
        raw = str(value).strip().lower()
        normalized = {
            "western_aesa": "aesa_western",
            "aesa": "aesa_western",
        }.get(raw, raw)
        return cls(normalized)


class RadarBand(str, Enum):
    """Radar frequency bands with compatibility aliases."""

    L_BAND = "L"
    S_BAND = "S"
    C_BAND = "C"
    X_BAND = "X"
    KU_BAND = "Ku"
    K_BAND = "K"
    KA_BAND = "Ka"
    # Compatibility aliases used by some suite templates.
    L = "L"
    S = "S"
    C = "C"
    X = "X"
    KU = "Ku"
    K = "K"
    KA = "Ka"

    @classmethod
    def from_value(cls, value: Any) -> "RadarBand":
        if isinstance(value, cls):
            return value
        raw = str(value).strip()
        normalized = {
            "l_band": "L",
            "s_band": "S",
            "c_band": "C",
            "x_band": "X",
            "ku_band": "Ku",
            "k_band": "K",
            "ka_band": "Ka",
        }.get(raw.lower(), raw)
        return cls(normalized)


class ScanMode(str, Enum):
    """Radar scan strategy and update behavior."""

    ROTATING = "rotating"
    ELECTRONIC = "electronic"
    SECTOR = "sector"
    TRACK_WHILE_SCAN = "tws"
    SEARCH = "search"
    VOLUME = "volume"

    @classmethod
    def from_value(cls, value: Any) -> "ScanMode":
        if isinstance(value, cls):
            return value
        raw = str(value).strip().lower().replace("-", "_")
        normalized = {
            "track_while_scan": "tws",
        }.get(raw, raw)
        return cls(normalized)


class RCSClassification(str, Enum):
    """Target classes derived from radar cross-section signatures."""

    SMALL_UAV = "small_uav"
    MEDIUM_UAV = "medium_uav"
    LARGE_UAV = "large_uav"
    CRUISE_MISSILE = "cruise_missile"
    HELICOPTER = "helicopter"
    FIGHTER = "fighter"
    FIGHTER_AIRCRAFT = "fighter"  # Alias used by classifier revisions.
    LARGE_AIRCRAFT = "large_aircraft"
    BALLISTIC = "ballistic"
    BALLISTIC_TARGET = "ballistic"  # Alias used by classifier revisions.
    CLUTTER = "clutter"
    UNKNOWN = "unknown"


class TrackState(str, Enum):
    """Track maturity state used by tactical fusion."""

    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    DROPPED = "dropped"


@dataclass
class RadarPlot:
    """Single radar detection normalized across adapter families."""

    plot_id: str = field(default_factory=lambda: f"plt-{uuid4().hex[:10]}")
    radar_id: str = ""
    timestamp: Any = field(default_factory=lambda: datetime.now(timezone.utc))

    range_m: float = 0.0
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0
    radial_velocity_mps: float = 0.0
    rcs_dbsm: float = 0.0
    snr_db: float = 0.0
    signal_strength: float = 0.0

    # Compatibility fields used by alternative ingestion paths.
    rcs_linear_m2: Optional[float] = None
    rcs_m2: Optional[float] = None
    confidence: float = 0.0

    position_cartesian: Optional[Tuple[float, float, float]] = None
    position_wgs84: Optional[Tuple[float, float, float]] = None
    position: Optional[Tuple[float, float, float]] = None

    rcs_classification: RCSClassification = RCSClassification.UNKNOWN
    classification_confidence: float = 0.0
    correlated_track_id: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.timestamp = _to_utc(self.timestamp)
        self.range_m = _validate_finite(self.range_m, field_name="range_m")
        if self.range_m < 0.0:
            raise ValueError("range_m must be non-negative")
        self.azimuth_deg = _validate_finite(self.azimuth_deg, field_name="azimuth_deg") % 360.0
        self.elevation_deg = _validate_finite(self.elevation_deg, field_name="elevation_deg")
        if not -90.0 <= self.elevation_deg <= 90.0:
            raise ValueError("elevation_deg must be between -90 and 90")
        self.radial_velocity_mps = _validate_finite(self.radial_velocity_mps, field_name="radial_velocity_mps")
        self.rcs_dbsm = _validate_finite(self.rcs_dbsm, field_name="rcs_dbsm")
        self.snr_db = _validate_finite(self.snr_db, field_name="snr_db")
        self.signal_strength = _validate_finite(self.signal_strength, field_name="signal_strength")

        if self.rcs_m2 is not None:
            self.rcs_m2 = _validate_finite(self.rcs_m2, field_name="rcs_m2")
            if self.rcs_m2 < 0.0:
                raise ValueError("rcs_m2 must be non-negative")
        if self.rcs_linear_m2 is not None:
            self.rcs_linear_m2 = _validate_finite(self.rcs_linear_m2, field_name="rcs_linear_m2")
            if self.rcs_linear_m2 < 0.0:
                raise ValueError("rcs_linear_m2 must be non-negative")

        if self.rcs_linear_m2 is None and self.rcs_m2 is not None:
            self.rcs_linear_m2 = self.rcs_m2
        if self.rcs_m2 is None and self.rcs_linear_m2 is not None:
            self.rcs_m2 = self.rcs_linear_m2
        if self.rcs_linear_m2 is None:
            self.rcs_linear_m2 = 10.0 ** (self.rcs_dbsm / 10.0)
        if self.rcs_m2 is None:
            self.rcs_m2 = self.rcs_linear_m2
        if self.rcs_linear_m2 > 0.0:
            # Tactical note: keep dBsm and linear RCS synchronized for downstream
            # classifier variants that consume one representation or the other.
            self.rcs_dbsm = 10.0 * log10(self.rcs_linear_m2)

        if isinstance(self.rcs_classification, str):
            self.rcs_classification = RCSClassification(str(self.rcs_classification).strip().lower())

        self.confidence = _validate_finite(self.confidence, field_name="confidence")
        self.classification_confidence = _validate_finite(
            self.classification_confidence,
            field_name="classification_confidence",
        )

        if self.position is not None:
            self.position = _validate_vec3(self.position, field_name="position")
            if self.position_cartesian is None:
                self.position_cartesian = self.position
        if self.position_cartesian is not None:
            self.position_cartesian = _validate_vec3(self.position_cartesian, field_name="position_cartesian")
        if self.position_wgs84 is not None:
            self.position_wgs84 = _validate_vec3(self.position_wgs84, field_name="position_wgs84")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plot_id": self.plot_id,
            "radar_id": self.radar_id,
            "timestamp": self.timestamp.isoformat(),
            "range_m": self.range_m,
            "azimuth_deg": round(self.azimuth_deg, 2),
            "elevation_deg": round(self.elevation_deg, 2),
            "radial_velocity_mps": round(self.radial_velocity_mps, 2),
            "rcs_dbsm": round(self.rcs_dbsm, 2),
            "rcs_linear_m2": self.rcs_linear_m2,
            "snr_db": round(self.snr_db, 2),
            "signal_strength": round(self.signal_strength, 4),
            "position_cartesian": list(self.position_cartesian) if self.position_cartesian else None,
            "position_wgs84": list(self.position_wgs84) if self.position_wgs84 else None,
            "position": list(self.position) if self.position else None,
            "rcs_classification": self.rcs_classification.value,
            "classification_confidence": round(self.classification_confidence, 3),
            "correlated_track_id": self.correlated_track_id,
            "metadata": dict(self.metadata),
            "attributes": dict(self.attributes),
        }


@dataclass
class RadarScan:
    """One radar sweep containing all plots for that update."""

    scan_id: str = field(default_factory=lambda: f"scan-{uuid4().hex[:8]}")
    radar_id: str = ""
    timestamp: Any = field(default_factory=lambda: datetime.now(timezone.utc))
    scan_number: int = 0
    scan_index: Optional[int] = None
    scan_mode: ScanMode = ScanMode.ROTATING
    plots: List[RadarPlot] = field(default_factory=list)
    scan_duration_s: float = 0.0
    azimuth_start_deg: float = 0.0
    azimuth_end_deg: float = 360.0

    def __post_init__(self) -> None:
        self.timestamp = _to_utc(self.timestamp)
        if isinstance(self.scan_mode, str):
            self.scan_mode = ScanMode.from_value(self.scan_mode)
        if self.scan_index is None:
            self.scan_index = int(self.scan_number)
        else:
            self.scan_number = int(self.scan_index)
        self.scan_duration_s = _validate_finite(self.scan_duration_s, field_name="scan_duration_s")
        self.azimuth_start_deg = _validate_finite(self.azimuth_start_deg, field_name="azimuth_start_deg")
        self.azimuth_end_deg = _validate_finite(self.azimuth_end_deg, field_name="azimuth_end_deg")

    @property
    def plot_count(self) -> int:
        return len(self.plots)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "radar_id": self.radar_id,
            "timestamp": self.timestamp.isoformat(),
            "scan_number": self.scan_number,
            "scan_index": self.scan_index,
            "scan_mode": self.scan_mode.value,
            "plot_count": self.plot_count,
            "plots": [plot.to_dict() for plot in self.plots],
        }


@dataclass
class RadarConfig:
    """Hardware and geometry configuration for one tactical radar."""

    radar_id: str = field(default_factory=lambda: f"radar-{uuid4().hex[:8]}")
    name_en: str = "Radar"
    name_ar: str = "رادار"
    radar_type: RadarType = RadarType.GENERIC_3D
    band: RadarBand = RadarBand.X_BAND
    scan_mode: ScanMode = ScanMode.ROTATING

    # Compatibility aliases used by alternate adapter stacks.
    radar_band: Optional[Any] = None
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    position_lla: Tuple[float, float, float] = (24.0, 46.0, 0.0)
    orientation_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    heading_deg: float = 0.0
    uses_wgs84: bool = False

    max_range_m: float = 50_000.0
    min_range_m: float = 200.0
    max_elevation_deg: float = 70.0
    min_elevation_deg: float = -2.0
    azimuth_coverage_deg: float = 360.0
    beam_width_az_deg: float = 1.5
    beam_width_el_deg: float = 2.0
    scan_rate_rpm: float = 6.0
    update_rate_hz: float = 0.1
    scan_rate_hz: float = 0.0

    min_detectable_rcs_dbsm: float = -20.0
    min_detectable_snr_db: float = 0.0
    range_resolution_m: float = 150.0
    azimuth_resolution_deg: float = 1.5
    velocity_resolution_mps: float = 5.0
    doppler_resolution_mps: float = 1.0
    has_elevation: bool = True
    has_doppler: bool = True

    range_noise_std_m: float = 50.0
    azimuth_noise_std_deg: float = 0.5
    elevation_noise_std_deg: float = 0.8
    velocity_noise_std_mps: float = 0.0

    operational: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.radar_id, str) or not self.radar_id.strip():
            raise ValueError("radar_id is required")
        self.radar_id = self.radar_id.strip()
        if self.radar_band is not None:
            self.band = RadarBand.from_value(self.radar_band)
        if isinstance(self.radar_type, str):
            self.radar_type = RadarType.from_value(self.radar_type)
        if isinstance(self.band, str):
            self.band = RadarBand.from_value(self.band)
        if isinstance(self.scan_mode, str):
            self.scan_mode = ScanMode.from_value(self.scan_mode)

        self.position = _validate_vec3(self.position, field_name="position")
        self.position_lla = _validate_vec3(self.position_lla, field_name="position_lla")
        self.orientation_deg = _validate_vec3(self.orientation_deg, field_name="orientation_deg")
        self.heading_deg = _validate_finite(self.heading_deg, field_name="heading_deg")

        if self.uses_wgs84:
            lat, lon, _ = self.position
            if not -90.0 <= lat <= 90.0:
                raise ValueError("WGS84 latitude must be between -90 and 90")
            if not -180.0 <= lon <= 180.0:
                raise ValueError("WGS84 longitude must be between -180 and 180")

        self.max_range_m = _validate_finite(self.max_range_m, field_name="max_range_m")
        self.min_range_m = _validate_finite(self.min_range_m, field_name="min_range_m")
        if self.max_range_m <= self.min_range_m:
            raise ValueError("max_range_m must exceed min_range_m")
        self.max_elevation_deg = _validate_finite(self.max_elevation_deg, field_name="max_elevation_deg")
        self.min_elevation_deg = _validate_finite(self.min_elevation_deg, field_name="min_elevation_deg")
        self.azimuth_coverage_deg = _validate_finite(self.azimuth_coverage_deg, field_name="azimuth_coverage_deg")
        self.beam_width_az_deg = _validate_finite(self.beam_width_az_deg, field_name="beam_width_az_deg")
        self.beam_width_el_deg = _validate_finite(self.beam_width_el_deg, field_name="beam_width_el_deg")
        self.scan_rate_rpm = _validate_finite(self.scan_rate_rpm, field_name="scan_rate_rpm")
        self.update_rate_hz = _validate_finite(self.update_rate_hz, field_name="update_rate_hz")
        self.scan_rate_hz = _validate_finite(self.scan_rate_hz, field_name="scan_rate_hz")
        self.min_detectable_rcs_dbsm = _validate_finite(
            self.min_detectable_rcs_dbsm,
            field_name="min_detectable_rcs_dbsm",
        )
        self.min_detectable_snr_db = _validate_finite(
            self.min_detectable_snr_db,
            field_name="min_detectable_snr_db",
        )
        self.range_resolution_m = _validate_finite(self.range_resolution_m, field_name="range_resolution_m")
        self.azimuth_resolution_deg = _validate_finite(
            self.azimuth_resolution_deg,
            field_name="azimuth_resolution_deg",
        )
        self.velocity_resolution_mps = _validate_finite(
            self.velocity_resolution_mps,
            field_name="velocity_resolution_mps",
        )
        self.doppler_resolution_mps = _validate_finite(
            self.doppler_resolution_mps,
            field_name="doppler_resolution_mps",
        )
        self.range_noise_std_m = _validate_finite(self.range_noise_std_m, field_name="range_noise_std_m")
        self.azimuth_noise_std_deg = _validate_finite(
            self.azimuth_noise_std_deg,
            field_name="azimuth_noise_std_deg",
        )
        self.elevation_noise_std_deg = _validate_finite(
            self.elevation_noise_std_deg,
            field_name="elevation_noise_std_deg",
        )
        self.velocity_noise_std_mps = _validate_finite(
            self.velocity_noise_std_mps,
            field_name="velocity_noise_std_mps",
        )
        if self.max_range_m <= 0.0:
            raise ValueError("max_range_m must be positive")
        if self.min_range_m < 0.0:
            raise ValueError("min_range_m must be non-negative")
        if self.range_noise_std_m < 0.0:
            raise ValueError("range_noise_std_m must be non-negative")
        if self.azimuth_noise_std_deg < 0.0:
            raise ValueError("azimuth_noise_std_deg must be non-negative")
        if self.elevation_noise_std_deg < 0.0:
            raise ValueError("elevation_noise_std_deg must be non-negative")
        if self.velocity_noise_std_mps < 0.0:
            raise ValueError("velocity_noise_std_mps must be non-negative")

    @property
    def scan_period_s(self) -> float:
        if self.scan_rate_rpm > 0.0:
            return 60.0 / self.scan_rate_rpm
        if self.update_rate_hz > 0.0:
            return 1.0 / self.update_rate_hz
        if self.scan_rate_hz > 0.0:
            return 1.0 / self.scan_rate_hz
        return 10.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "radar_id": self.radar_id,
            "name_en": self.name_en,
            "name_ar": self.name_ar,
            "radar_type": self.radar_type.value,
            "band": self.band.value,
            "scan_mode": self.scan_mode.value,
            "position": list(self.position),
            "position_lla": list(self.position_lla),
            "orientation_deg": list(self.orientation_deg),
            "max_range_m": self.max_range_m,
            "min_range_m": self.min_range_m,
            "has_elevation": self.has_elevation,
            "has_doppler": self.has_doppler,
            "scan_period_s": round(self.scan_period_s, 3),
            "operational": self.operational,
        }


@dataclass
class RadarStatus:
    """Runtime status counters for one registered radar."""

    radar_id: str = ""
    operational: bool = True
    scans_received: int = 0
    plots_received: int = 0
    plots_correlated: int = 0
    last_scan_time: Optional[datetime] = None
    tracks_contributed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "radar_id": self.radar_id,
            "operational": self.operational,
            "scans_received": self.scans_received,
            "plots_received": self.plots_received,
            "plots_correlated": self.plots_correlated,
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
            # Compatibility aliases used by demo/status endpoints.
            "scans": self.scans_received,
            "plots": self.plots_received,
            "correlated": self.plots_correlated,
        }


@dataclass
class PlotCorrelation:
    """Association score between one previous and one current plot."""

    radar_id: str
    previous_plot_id: str
    current_plot_id: str
    dt_seconds: float
    spatial_distance_m: float
    radial_velocity_delta_mps: float
    score: float


@dataclass
class FusedTrack:
    """Fused tactical track state produced from correlated radar evidence."""

    track_id: str
    state: TrackState = TrackState.TENTATIVE
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_hits: int = 0
    classification: str = "unknown"
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    sensor_sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "state": self.state.value,
            "last_update": self.last_update.isoformat(),
            "source_hits": self.source_hits,
            "classification": self.classification,
            "position": list(self.position),
            "velocity": list(self.velocity),
            "sensor_sources": list(self.sensor_sources),
            "metadata": dict(self.metadata),
        }


@dataclass
class RadarUnit:
    """Registered radar wrapper that preserves config plus generated ID."""

    radar_id: str
    config: RadarConfig
    operational: bool = True
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        # Tactical bookkeeping: manager-issued IDs must remain authoritative.
        self.config.radar_id = self.radar_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self.config, name)

    def to_dict(self) -> Dict[str, Any]:
        payload = self.config.to_dict()
        payload["radar_id"] = self.radar_id
        payload["operational"] = self.operational
        payload["registered_at"] = self.registered_at.isoformat()
        return payload
