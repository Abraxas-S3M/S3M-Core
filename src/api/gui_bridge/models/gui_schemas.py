"""Pydantic v2 models matching S3M-GUI TypeScript interfaces.

IMPORTANT: All field names use camelCase to match the frontend.
Use model_config = ConfigDict(populate_by_name=True) and Field(alias=...)
where Python reserved words conflict (e.g. 'from').
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GUIBaseModel(BaseModel):
    """Base model for GUI contract payloads."""

    model_config = ConfigDict(populate_by_name=True)


# -- Enums ----------------------------------------------------


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DecisionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    STEADY = "steady"


class UnitReadinessStatus(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class AssetStatus(str, Enum):
    ACTIVE = "active"
    STANDBY = "standby"
    MAINTENANCE = "maintenance"


class MessagePriority(str, Enum):
    ROUTINE = "routine"
    PRIORITY = "priority"
    IMMEDIATE = "immediate"
    EMERGENCY = "emergency"


class TaskingStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


# -- Command Overview (OperationalContextData) ----------------


class GUIThreatItem(GUIBaseModel):
    id: str
    label: str
    level: SeverityLevel
    domain: str
    summary: str
    updatedAt: str


class GUIDirectiveItem(GUIBaseModel):
    id: str
    title: str
    authority: str
    status: str
    details: str
    updatedAt: str


class GUIDecision(GUIBaseModel):
    id: str
    title: str
    risk: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    description: str
    status: DecisionStatus
    severity: SeverityLevel
    updatedAt: Optional[str] = None


class GUIOperationalContextData(GUIBaseModel):
    threats: List[GUIThreatItem]
    decisions: List[GUIDecision]
    directives: List[GUIDirectiveItem]
    metrics: Optional["GUIOverviewMetrics"] = None
    updatedAt: str


class GUIOverviewMetrics(GUIBaseModel):
    readinessScore: int = Field(ge=0, le=100)
    activeMissions: int = Field(ge=0)
    assetAvailability: int = Field(ge=0, le=100)
    openRisks: int = Field(ge=0)


# -- Risk (RiskData) ------------------------------------------


class GUIRiskDomain(GUIBaseModel):
    domain: str
    score: int = Field(ge=0, le=100)
    trend: TrendDirection


class GUIRiskForecast(GUIBaseModel):
    timestamp: str
    score: int = Field(ge=0, le=100)


class GUIRiskDriver(GUIBaseModel):
    name: str
    impact: float = Field(ge=-1.0, le=1.0)
    direction: str  # "positive" | "negative"


class GUIRiskData(GUIBaseModel):
    composite: int = Field(ge=0, le=100)
    domains: List[GUIRiskDomain]
    forecast: List[GUIRiskForecast]
    drivers: List[GUIRiskDriver]
    updatedAt: str


# -- COP Tracks (ThreatTrack) ---------------------------------


class GUIThreatTrack(GUIBaseModel):
    id: str
    domain: str
    confidence: int = Field(ge=0, le=100)
    severity: int = Field(ge=0, le=100)
    correlatedTrackIds: List[str] = Field(default_factory=list)
    summary: str
    lastSeen: str


class GUITracksData(GUIBaseModel):
    tracks: List[GUIThreatTrack]
    updatedAt: str


# -- Readiness (ReadinessData) --------------------------------


class GUIPersonnelSummary(GUIBaseModel):
    available: int
    deployed: int
    onLeave: int


class GUIEquipmentSummary(GUIBaseModel):
    ready: int
    maintenance: int
    unavailable: int


class GUIUnitStatus(GUIBaseModel):
    unitId: str
    readiness: int = Field(ge=0, le=100)
    status: UnitReadinessStatus


class GUIReadinessData(GUIBaseModel):
    personnel: GUIPersonnelSummary
    equipment: GUIEquipmentSummary
    unitStatus: List[GUIUnitStatus]
    updatedAt: str


# -- Surveillance / ISR (SurveillanceData) --------------------


class GUIISRAsset(GUIBaseModel):
    id: str
    type: str
    status: AssetStatus
    location: str


class GUITaskingItem(GUIBaseModel):
    id: str
    priority: str
    description: str
    assignedAssetId: Optional[str] = None
    status: TaskingStatus


class GUITargetBoardItem(GUIBaseModel):
    id: str
    designation: str
    confidence: int = Field(ge=0, le=100)
    lastSeen: str


class GUISurveillanceData(GUIBaseModel):
    assets: List[GUIISRAsset]
    taskingQueue: List[GUITaskingItem]
    targetBoard: List[GUITargetBoardItem]
    updatedAt: str


# -- Communications (CommsData) -------------------------------


class GUICommsMessage(GUIBaseModel):
    id: str
    from_field: str = Field(alias="from")
    to: str
    subject: str
    body: str
    read: bool
    priority: MessagePriority
    timestamp: str


class GUIRelayStatus(GUIBaseModel):
    id: str
    messageId: str
    status: str
    updatedAt: str


class GUICommsData(GUIBaseModel):
    inbox: List[GUICommsMessage]
    relayQueue: List[GUIRelayStatus]
    updatedAt: str


# -- Timeline Events ------------------------------------------


class GUITimelineEvent(GUIBaseModel):
    id: str
    title: str
    category: str
    severity: SeverityLevel
    occurredAt: str
    details: str


class GUITimelineEventData(GUIBaseModel):
    events: List[GUITimelineEvent]
    updatedAt: str


# -- Simulation -----------------------------------------------


class GUIScenario(GUIBaseModel):
    id: str
    name: str
    description: str
    status: str
    type: str
    updatedAt: Optional[str] = None


class GUISimulationData(GUIBaseModel):
    scenarios: List[GUIScenario]
    updatedAt: str


# -- Cyber -----------------------------------------------------


class GUICyberIncident(GUIBaseModel):
    id: str
    title: str
    severity: SeverityLevel
    status: str
    source: str
    detectedAt: str
    description: str


class GUICyberResilienceMetric(GUIBaseModel):
    domain: str
    score: int = Field(ge=0, le=100)
    status: str


class GUICyberData(GUIBaseModel):
    incidents: List[GUICyberIncident]
    resilience: List[GUICyberResilienceMetric]
    updatedAt: str


# -- Sustainment ----------------------------------------------


class GUIFleetUnit(GUIBaseModel):
    unitId: str
    unitName: str
    fmc: int  # fully mission capable count
    pmc: int  # partially mission capable
    nmc: int  # non-mission capable
    totalAssets: int
    readinessPercent: int = Field(ge=0, le=100)


class GUISupplyCategory(GUIBaseModel):
    category: str
    onHand: int
    required: int
    fillRate: int = Field(ge=0, le=100)
    status: str  # green | amber | red


class GUIFleetData(GUIBaseModel):
    units: List[GUIFleetUnit]
    updatedAt: str


class GUISupplyData(GUIBaseModel):
    categories: List[GUISupplyCategory]
    updatedAt: str


# -- Planning --------------------------------------------------


class GUIMissionPhase(GUIBaseModel):
    id: str
    name: str
    status: str  # planned | active | complete
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    objectives: List[str] = Field(default_factory=list)


class GUICOA(GUIBaseModel):
    id: str
    name: str
    description: str
    riskScore: int = Field(ge=0, le=100)
    successProbability: float = Field(ge=0.0, le=1.0)
    selected: bool = False
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)


class GUIPlanningPhasesData(GUIBaseModel):
    phases: List[GUIMissionPhase]
    updatedAt: str


class GUICOAData(GUIBaseModel):
    coursesOfAction: List[GUICOA]
    updatedAt: str
