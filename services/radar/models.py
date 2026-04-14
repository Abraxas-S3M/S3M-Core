"""Core data models for S3M radar adapter framework.

Military context:
These models represent the radar-specific data structures that the Krechet
9C905 processes internally: raw radar plots in polar coordinates, scan
metadata, radar hardware configurations, and RCS-based target classification.
The existing SensorReading model has no concept of these — this layer adds it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


class RadarType(str, Enum):
    """Radar hardware types matching Krechet integration catalog."""

    RPS_82 = "rps_82"  # Portable short-range surveillance
    RPS_202 = "rps_202"  # Vehicle-mounted medium-range
    GENERIC_2D = "generic_2d"  # 2D surveillance (range + azimuth)
    GENERIC_3D = "generic_3d"  # 3D (range + azimuth + elevation)
    AESA_WESTERN = "aesa_western"  # Western AESA (AN/TPS-80, Giraffe, TRML-4D class)
    AESA_PANEL = "aesa_panel"  # Fixed-panel AESA
    DOPPLER_CW = "doppler_cw"  # Continuous-wave Doppler
    CUSTOM = "custom"


class RadarBand(str, Enum):
    """IEEE radar frequency band designations."""

    L_BAND = "L"  # 1-2 GHz
    S_BAND = "S"  # 2-4 GHz
    C_BAND = "C"  # 4-8 GHz
    X_BAND = "X"  # 8-12 GHz
    KU_BAND = "Ku"  # 12-18 GHz
    K_BAND = "K"  # 18-27 GHz
    KA_BAND = "Ka"  # 27-40 GHz


class ScanMode(str, Enum):
    """Radar scanning mode."""

    ROTATING = "rotating"  # Mechanical rotation (most surveillance)
    ELECTRONIC = "electronic"  # Electronic beam steering (AESA)
    SECTOR = "sector"  # Sector scan (limited azimuth)
    TRACK_WHILE_SCAN = "tws"  # Track-while-scan


class RCSClassification(str, Enum):
    """Target classification by radar cross-section signature."""

    SMALL_UAV = "small_uav"  # < 0.01 m² (FPV, micro drones)
    MEDIUM_UAV = "medium_uav"  # 0.01 - 0.1 m² (Shahed-class)
    LARGE_UAV = "large_uav"  # 0.1 - 1.0 m² (MALE/HALE)
    CRUISE_MISSILE = "cruise_missile"  # 0.1 - 1.0 m²
    HELICOPTER = "helicopter"  # 1 - 10 m²
    FIGHTER = "fighter"  # 1 - 5 m² (modern fighter)
    LARGE_AIRCRAFT = "large_aircraft"  # 10 - 100 m²
    BALLISTIC = "ballistic"  # 0.01 - 0.5 m²
    CLUTTER = "clutter"  # Likely false alarm / ground clutter
    UNKNOWN = "unknown"


@dataclass
class RadarPlot:
    """Single radar detection in polar coordinates.

    Military context:
    This is what a radar actually outputs per detection: range, azimuth,
    optionally elevation, radial velocity from Doppler, and signal strength.
    The Krechet ingests these from 10+ radar types and converts them to a
    common Cartesian picture. S3M currently has no equivalent.
    """

    plot_id: str = field(default_factory=lambda: f"plt-{uuid4().hex[:10]}")
    radar_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Polar measurements (radar-native)
    range_m: float = 0.0  # Slant range in meters
    azimuth_deg: float = 0.0  # Azimuth bearing in degrees (0=North, CW)
    elevation_deg: float = 0.0  # Elevation angle in degrees (0=horizon)
    radial_velocity_mps: float = 0.0  # Doppler radial velocity (positive=approaching)

    # Signal characteristics
    rcs_dbsm: float = 0.0  # Radar cross section in dBsm
    snr_db: float = 0.0  # Signal-to-noise ratio in dB
    signal_strength: float = 0.0  # Raw signal amplitude

    # Computed Cartesian (filled by adapter after conversion)
    position_cartesian: Optional[Tuple[float, float, float]] = None

    # Classification (filled by RCS classifier)
    rcs_classification: RCSClassification = RCSClassification.UNKNOWN
    classification_confidence: float = 0.0

    # Correlation (filled by plot correlator)
    correlated_track_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.range_m < 0:
            raise ValueError("range_m must be non-negative")
        self.azimuth_deg = self.azimuth_deg % 360.0

    @property
    def rcs_linear_m2(self) -> float:
        """Convert dBsm to linear m² for RCS classification."""
        return 10.0 ** (self.rcs_dbsm / 10.0)

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
            "snr_db": round(self.snr_db, 2),
            "position_cartesian": list(self.position_cartesian) if self.position_cartesian else None,
            "rcs_classification": self.rcs_classification.value,
            "classification_confidence": round(self.classification_confidence, 3),
            "correlated_track_id": self.correlated_track_id,
        }


@dataclass
class RadarScan:
    """Complete radar scan containing multiple plots.

    Military context:
    One rotation or electronic sweep of the radar. The Krechet processes
    scans at the radar's update rate (typically 1-12 seconds for rotating
    radars, sub-second for AESA).
    """

    scan_id: str = field(default_factory=lambda: f"scan-{uuid4().hex[:8]}")
    radar_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scan_number: int = 0
    plots: List[RadarPlot] = field(default_factory=list)
    scan_duration_s: float = 0.0
    azimuth_start_deg: float = 0.0
    azimuth_end_deg: float = 360.0

    @property
    def plot_count(self) -> int:
        return len(self.plots)


@dataclass
class RadarConfig:
    """Hardware configuration for a specific radar unit.

    Military context:
    Each radar in the Krechet system has known characteristics that affect
    measurement quality and detection capability. The adapter uses these
    to set appropriate noise models and detection thresholds.
    """

    radar_id: str = field(default_factory=lambda: f"radar-{uuid4().hex[:8]}")
    name_en: str = ""
    name_ar: str = ""
    radar_type: RadarType = RadarType.GENERIC_3D
    band: RadarBand = RadarBand.X_BAND
    scan_mode: ScanMode = ScanMode.ROTATING

    # Position and orientation (WGS84 or local)
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # (x, y, z) or (lat, lon, alt)
    heading_deg: float = 0.0  # Boresight heading correction
    uses_wgs84: bool = False  # If True, position is (lat, lon, alt_m)

    # Performance specifications
    max_range_m: float = 50000.0
    min_range_m: float = 200.0
    max_elevation_deg: float = 70.0
    min_elevation_deg: float = -2.0
    azimuth_coverage_deg: float = 360.0
    beam_width_az_deg: float = 1.5
    beam_width_el_deg: float = 2.0
    scan_rate_rpm: float = 6.0  # Revolutions per minute (rotating)
    update_rate_hz: float = 0.1  # Scans per second

    # Detection characteristics
    min_detectable_rcs_dbsm: float = -20.0  # Minimum RCS for detection
    range_resolution_m: float = 150.0
    azimuth_resolution_deg: float = 1.5
    velocity_resolution_mps: float = 5.0
    has_elevation: bool = True
    has_doppler: bool = True

    # Noise parameters (standard deviations)
    range_noise_std_m: float = 50.0
    azimuth_noise_std_deg: float = 0.5
    elevation_noise_std_deg: float = 0.8

    # Operational
    operational: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_range_m <= self.min_range_m:
            raise ValueError("max_range_m must exceed min_range_m")

    @property
    def scan_period_s(self) -> float:
        """Time for one complete scan cycle."""
        if self.scan_rate_rpm > 0:
            return 60.0 / self.scan_rate_rpm
        if self.update_rate_hz > 0:
            return 1.0 / self.update_rate_hz
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
            "max_range_m": self.max_range_m,
            "has_elevation": self.has_elevation,
            "has_doppler": self.has_doppler,
            "scan_period_s": round(self.scan_period_s, 2),
            "operational": self.operational,
        }


@dataclass
class RadarStatus:
    """Runtime status of a registered radar."""

    radar_id: str = ""
    operational: bool = True
    scans_received: int = 0
    plots_received: int = 0
    plots_correlated: int = 0
    last_scan_time: Optional[datetime] = None
    tracks_contributed: int = 0
