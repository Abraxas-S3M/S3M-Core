"""Data models for S3M Layer 07 Cyber Defense Operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class CaseSeverity(str, Enum):
    """SOC case severity aligned to military command urgency."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"

    @classmethod
    def from_value(cls, value: str | "CaseSeverity") -> "CaseSeverity":
        if isinstance(value, CaseSeverity):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid CaseSeverity value: {value}")


class CaseStatus(str, Enum):
    """SOC workflow state for commander and analyst tracking."""

    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING = "WAITING"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    FALSE_POSITIVE = "FALSE_POSITIVE"

    @classmethod
    def from_value(cls, value: str | "CaseStatus") -> "CaseStatus":
        if isinstance(value, CaseStatus):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid CaseStatus value: {value}")


class CaseVerdict(str, Enum):
    """Final analyst judgment used for military after-action records."""

    TRUE_POSITIVE = "TRUE_POSITIVE"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    INDETERMINATE = "INDETERMINATE"
    BENIGN = "BENIGN"
    MALICIOUS = "MALICIOUS"

    @classmethod
    def from_value(cls, value: str | "CaseVerdict") -> "CaseVerdict":
        if isinstance(value, CaseVerdict):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid CaseVerdict value: {value}")


@dataclass
class IncidentCase:
    """Primary incident record that drives SOC triage to response execution."""

    case_id: str = field(default_factory=lambda: str(uuid4()))
    title: str = ""
    description: str = ""
    severity: CaseSeverity = CaseSeverity.LOW
    status: CaseStatus = CaseStatus.NEW
    verdict: Optional[CaseVerdict] = None
    source_events: List[str] = field(default_factory=list)
    observables: List[dict] = field(default_factory=list)
    enrichments: List[dict] = field(default_factory=list)
    assigned_analyst: Optional[str] = None
    mitre_tactics: List[str] = field(default_factory=list)
    mitre_techniques: List[str] = field(default_factory=list)
    playbook_id: Optional[str] = None
    playbook_results: List[dict] = field(default_factory=list)
    llm_analysis: Optional[str] = None
    llm_recommendation: Optional[str] = None
    timeline: List[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    classification: str = "UNCLASSIFIED - FOUO"

    def __post_init__(self) -> None:
        self.severity = CaseSeverity.from_value(self.severity)
        self.status = CaseStatus.from_value(self.status)
        if self.verdict is not None:
            self.verdict = CaseVerdict.from_value(self.verdict)

        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("case_id must be a non-empty string")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("title must be a non-empty string")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be a non-empty string")

        if not self.timeline:
            self.add_timeline_entry("case_created", "system", "Case opened by SOC intake pipeline")

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["severity"] = self.severity.value
        payload["status"] = self.status.value
        payload["verdict"] = self.verdict.value if self.verdict else None
        payload["created_at"] = self.created_at.isoformat()
        payload["updated_at"] = self.updated_at.isoformat()
        payload["resolved_at"] = self.resolved_at.isoformat() if self.resolved_at else None
        return payload

    def duration_seconds(self) -> Optional[float]:
        if self.resolved_at is None:
            return None
        return max(0.0, (self.resolved_at - self.created_at).total_seconds())

    def add_timeline_entry(self, action: str, actor: str, detail: str) -> None:
        self.timeline.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": str(action),
                "actor": str(actor),
                "detail": str(detail),
            }
        )
        self.updated_at = datetime.now(timezone.utc)

    def is_open(self) -> bool:
        return self.status not in {CaseStatus.RESOLVED, CaseStatus.CLOSED, CaseStatus.FALSE_POSITIVE}


class ObservableType(str, Enum):
    """Observable categories used in SOC intel enrichment workflows."""

    IP_ADDRESS = "IP_ADDRESS"
    DOMAIN = "DOMAIN"
    URL = "URL"
    FILE_HASH_MD5 = "FILE_HASH_MD5"
    FILE_HASH_SHA256 = "FILE_HASH_SHA256"
    EMAIL = "EMAIL"
    FILENAME = "FILENAME"
    REGISTRY_KEY = "REGISTRY_KEY"
    PROCESS_NAME = "PROCESS_NAME"
    CVE = "CVE"
    USER_AGENT = "USER_AGENT"
    CERTIFICATE = "CERTIFICATE"

    @classmethod
    def from_value(cls, value: str | "ObservableType") -> "ObservableType":
        if isinstance(value, ObservableType):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid ObservableType value: {value}")


@dataclass
class Observable:
    """IOC or artifact tied to a case and reused across intel sharing."""

    observable_id: str = field(default_factory=lambda: str(uuid4()))
    observable_type: ObservableType = ObservableType.IP_ADDRESS
    value: str = ""
    source_case_id: str = ""
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tags: List[str] = field(default_factory=list)
    tlp: str = "AMBER"
    enrichments: List[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.observable_type = ObservableType.from_value(self.observable_type)
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("value must be a non-empty string")
        if not isinstance(self.source_case_id, str) or not self.source_case_id.strip():
            raise ValueError("source_case_id must be a non-empty string")
        allowed = {"WHITE", "GREEN", "AMBER", "RED"}
        normalized = str(self.tlp).upper()
        if normalized not in allowed:
            raise ValueError(f"Invalid TLP value: {self.tlp}")
        self.tlp = normalized

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observable_id": self.observable_id,
            "observable_type": self.observable_type.value,
            "value": self.value,
            "source_case_id": self.source_case_id,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "tags": list(self.tags),
            "tlp": self.tlp,
            "enrichments": list(self.enrichments),
        }


@dataclass
class EnrichmentResult:
    """Analyzer output normalized for tactical case reasoning."""

    analyzer: str
    observable_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result: dict = field(default_factory=dict)
    verdict: str = "unknown"
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.analyzer, str) or not self.analyzer.strip():
            raise ValueError("analyzer must be a non-empty string")
        if not isinstance(self.observable_id, str) or not self.observable_id.strip():
            raise ValueError("observable_id must be a non-empty string")
        self.confidence = float(self.confidence)
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analyzer": self.analyzer,
            "observable_id": self.observable_id,
            "timestamp": self.timestamp.isoformat(),
            "result": dict(self.result),
            "verdict": self.verdict,
            "confidence": self.confidence,
        }


@dataclass
class MITREMapping:
    """ATT&CK technique/tactic mapping used for automated SOC playbooks."""

    technique_id: str
    technique_name: str
    tactic_id: str
    tactic_name: str
    severity_weight: float

    @classmethod
    def from_alert(cls, alert_category: str, alert_signature: str) -> Optional["MITREMapping"]:
        text = f"{alert_category} {alert_signature}".lower()
        mappings = [
            (
                "brute force",
                cls("T1110", "Brute Force", "TA0006", "Credential Access", 0.70),
            ),
            (
                "sql injection",
                cls("T1190", "Exploit Public-Facing Application", "TA0001", "Initial Access", 0.85),
            ),
            (
                "lateral movement",
                cls("T1021", "Remote Services", "TA0008", "Lateral Movement", 0.85),
            ),
            (
                "data exfil",
                cls("T1041", "Exfiltration Over C2 Channel", "TA0010", "Exfiltration", 0.95),
            ),
            (
                "malware",
                cls("T1059", "Command and Scripting Interpreter", "TA0002", "Execution", 0.80),
            ),
            (
                "phishing",
                cls("T1566", "Phishing", "TA0001", "Initial Access", 0.80),
            ),
            (
                "ransomware",
                cls("T1486", "Data Encrypted for Impact", "TA0040", "Impact", 1.00),
            ),
        ]
        for keyword, mapping in mappings:
            if keyword in text:
                return mapping
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "technique_id": self.technique_id,
            "technique_name": self.technique_name,
            "tactic_id": self.tactic_id,
            "tactic_name": self.tactic_name,
            "severity_weight": float(self.severity_weight),
        }


class PlaybookStatus(str, Enum):
    """Execution state for SOAR playbook runtime."""

    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"

    @classmethod
    def from_value(cls, value: str | "PlaybookStatus") -> "PlaybookStatus":
        if isinstance(value, PlaybookStatus):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid PlaybookStatus value: {value}")


class PlaybookAction(str, Enum):
    """Authorized response actions in air-gapped tactical SOC workflows."""

    BLOCK_IP = "BLOCK_IP"
    ISOLATE_HOST = "ISOLATE_HOST"
    DISABLE_ACCOUNT = "DISABLE_ACCOUNT"
    SCAN_ENDPOINT = "SCAN_ENDPOINT"
    COLLECT_FORENSICS = "COLLECT_FORENSICS"
    NOTIFY_ANALYST = "NOTIFY_ANALYST"
    NOTIFY_COMMANDER = "NOTIFY_COMMANDER"
    ESCALATE_CASE = "ESCALATE_CASE"
    ENRICH_OBSERVABLE = "ENRICH_OBSERVABLE"
    QUERY_LLM = "QUERY_LLM"
    GENERATE_REPORT = "GENERATE_REPORT"
    CUSTOM = "CUSTOM"

    @classmethod
    def from_value(cls, value: str | "PlaybookAction") -> "PlaybookAction":
        if isinstance(value, PlaybookAction):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in cls.__members__:
                return cls[normalized]
        raise ValueError(f"Invalid PlaybookAction value: {value}")


@dataclass
class PlaybookStep:
    """Single action unit in a response playbook."""

    step_id: int
    name: str
    action: PlaybookAction
    parameters: dict = field(default_factory=dict)
    condition: Optional[str] = None
    timeout_seconds: float = 30.0
    on_failure: str = "continue"
    result: Optional[dict] = None
    status: PlaybookStatus = PlaybookStatus.READY

    def __post_init__(self) -> None:
        self.action = PlaybookAction.from_value(self.action)
        self.status = PlaybookStatus.from_value(self.status)
        self.timeout_seconds = float(self.timeout_seconds)
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.on_failure = str(self.on_failure).lower()
        if self.on_failure not in {"continue", "abort", "skip"}:
            raise ValueError("on_failure must be one of: continue, abort, skip")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "action": self.action.value,
            "parameters": dict(self.parameters),
            "condition": self.condition,
            "timeout_seconds": self.timeout_seconds,
            "on_failure": self.on_failure,
            "result": self.result,
            "status": self.status.value,
        }


@dataclass
class Playbook:
    """Executable playbook definition for SOC automation."""

    playbook_id: str
    name: str
    description: str
    trigger_conditions: List[str] = field(default_factory=list)
    steps: List[PlaybookStep] = field(default_factory=list)
    author: str = "S3M SOC"
    version: str = "1.0"
    mitre_techniques: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "playbook_id": self.playbook_id,
            "name": self.name,
            "description": self.description,
            "trigger_conditions": list(self.trigger_conditions),
            "steps": [step.to_dict() for step in self.steps],
            "author": self.author,
            "version": self.version,
            "mitre_techniques": list(self.mitre_techniques),
            "tags": list(self.tags),
        }

    def step_count(self) -> int:
        return len(self.steps)
