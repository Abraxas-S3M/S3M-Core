"""
S3M Layer 07 — Cyber Defense Operations
Full Security Operations Center (SOC) built on top of Phase 5 threat detection.

Subsystems:
- SOC Stack: Wazuh/Suricata enterprise deployment orchestration
- Incident Response: TheHive case management, Cortex enrichment, MISP intel sharing
- SOAR: Shuffle-compatible playbook execution engine with automated response
- Playbook Library: 50+ military IR playbooks as executable YAML definitions
- SOC Dashboard: Alert queues, case management, MITRE ATT&CK heatmap, analyst workbench
- Log Aggregation: Graylog/OpenSearch bridge for searchable event indexing
- Cyber Training: SOC simulator integration for analyst exercises
- LLM Analysis: Grok-powered alert enrichment and automated IR report generation

Architecture:
  Phase 5 ThreatEvents → SOC triage → Incident cases → Playbook execution → Response
  All events enriched by Layer 01 LLM (Grok for analysis, Mistral for reports)
"""

from services.cyber.ir_platforms import (
    CortexAdapter,
    DFIRIRISAdapter,
    IRPlatformAdapter,
    IRPlatformBridge,
    MISPAdapter,
    TheHiveAdapter,
)
from services.cyber.log_aggregation import GraylogAdapter, LogAggregator, OpenSearchAdapter
from services.cyber.models import (
    CaseSeverity,
    CaseStatus,
    CaseVerdict,
    EnrichmentResult,
    IncidentCase,
    MITREMapping,
    Observable,
    ObservableType,
    Playbook,
    PlaybookAction,
    PlaybookStatus,
    PlaybookStep,
)
from services.cyber.soc_dashboard import SOCDashboardProvider
from services.cyber.soc_manager import SOCManager
from services.cyber.soar import PlaybookExecutor, PlaybookLibrary, SOAREngine, ShuffleAdapter
from services.cyber.training import CyberTrainingManager
from services.cyber.triage import AlertTriage, CaseManager

__all__ = [
    "SOCManager",
    "IncidentCase",
    "CaseSeverity",
    "CaseStatus",
    "CaseVerdict",
    "PlaybookAction",
    "PlaybookStatus",
    "Playbook",
    "PlaybookStep",
    "SOAREngine",
    "Observable",
    "ObservableType",
    "EnrichmentResult",
    "IRPlatformAdapter",
    "TheHiveAdapter",
    "CortexAdapter",
    "MISPAdapter",
    "ShuffleAdapter",
    "GraylogAdapter",
    "OpenSearchAdapter",
    "SOCDashboardProvider",
    "CyberTrainingManager",
    "AlertTriage",
    "MITREMapping",
    "CaseManager",
    "PlaybookLibrary",
    "PlaybookExecutor",
    "IRPlatformBridge",
    "DFIRIRISAdapter",
    "LogAggregator",
]
