# Phase 13 — Cyber Defense Operations (Layer 07)

## Overview

Phase 13 adds a full SOC stack on top of Phase 5 threat detection. The design is additive: Phase 5 adapters (Suricata/Wazuh) continue producing `ThreatEvent`s, and Layer 07 enriches those events with case triage, incident response platform bridges, SOAR playbooks, SOC dashboards, log aggregation, and cyber training workflows.

Operational flow:

1. Phase 5 emits `ThreatEvent`
2. `AlertTriage` extracts observables and maps MITRE ATT&CK
3. `CaseManager` opens/updates incident cases
4. `IRPlatformBridge` coordinates TheHive/Cortex/MISP/DFIR-IRIS
5. `SOAREngine` matches and executes playbooks
6. `LogAggregator` forwards to Graylog/OpenSearch with offline buffering
7. `SOCDashboardProvider` exposes analyst/command views

All modules are offline-safe for air-gapped deployment.

---

## Architecture

### Core package

`services/cyber/`:

- `models.py` — SOC data models/enums (cases, observables, enrichments, MITRE mappings, playbooks)
- `triage/` — alert triage + case lifecycle management
- `ir_platforms/` — adapters for TheHive, Cortex, MISP, DFIR-IRIS, plus bridge
- `soar/` — playbook library, execution engine, Shuffle adapter
- `log_aggregation/` — Graylog/OpenSearch adapters and aggregator
- `soc_dashboard.py` — SOC overview/queue/heatmap/workbench/IOC feed
- `soc_manager.py` — orchestration pipeline
- `training.py` — exercise generation, execution, and scoring

### API integration

- `src/api/cyber_models.py` — Pydantic request/response models
- `src/api/cyber_routes.py` — 22 SOC endpoints under `/cyber/*`
- `src/api/server.py` — includes `cyber_router`

---

## Alert Triage

`AlertTriage` converts `ThreatEvent` into triaged records:

- Extracted observables: IPv4, domains, MD5/SHA256, URLs, emails
- Severity mapping: ThreatLevel -> CaseSeverity
- MITRE mapping via keyword rules:
  - brute force -> T1110/TA0006
  - SQL injection -> T1190/TA0001
  - lateral movement -> T1021/TA0008
  - data exfil -> T1041/TA0010
  - malware -> T1059/TA0002
  - phishing -> T1566/TA0001
  - ransomware -> T1486/TA0040
- Triage score formula (0-100):
  - severity_weight * 40
  - confidence * 30
  - has_mitre * 15
  - observable_count_normalized * 15

---

## Case Management Lifecycle

`CaseManager` maintains thread-safe in-memory cases with bounded FIFO rotation:

- Creation: `NEW`
- Assignment: `IN_PROGRESS`
- Escalation: `ESCALATED`
- Resolution: `RESOLVED` (+ verdict + resolution timestamp)
- Closure: `CLOSED`
- False positive: `FALSE_POSITIVE`

Timeline entries are appended for all key transitions for auditability.

---

## IR Platform Adapters (Online + Offline)

Each adapter attempts localhost HTTP integration and gracefully degrades:

- **TheHiveAdapter**
  - create alert/case, update case, add observables
  - offline writes operation JSON to `data/cyber/thehive_outbox/`
- **CortexAdapter**
  - analyzer execution by observable type
  - offline returns `EnrichmentResult` from LLM fallback (`S3M_LLM_Grok`)
- **MISPAdapter**
  - IOC event creation, attribute add/search, threat-level lookup
  - offline outbox in `data/cyber/misp_outbox/`
- **DFIRIRISAdapter**
  - forensic case/evidence/IOC/timeline operations
  - offline outbox in `data/cyber/dfir_iris_outbox/`

`IRPlatformBridge` coordinates all four for a single case workflow.

---

## SOAR Engine

### Playbook format

Playbooks are YAML definitions loaded from `configs/cyber/playbooks/` with:

- metadata (id, name, description, version, author)
- trigger conditions
- MITRE techniques/tags
- ordered executable steps

### Included playbooks

1. `PB-001` Brute Force Response
2. `PB-002` Malware Detection Response
3. `PB-003` Data Exfiltration Response

### Execution behaviors

`PlaybookExecutor` supports action types:

- `BLOCK_IP`, `ISOLATE_HOST`, `DISABLE_ACCOUNT`, `SCAN_ENDPOINT`
- `COLLECT_FORENSICS`, `NOTIFY_ANALYST`, `NOTIFY_COMMANDER`
- `ESCALATE_CASE`, `ENRICH_OBSERVABLE`
- `QUERY_LLM`, `GENERATE_REPORT`, `CUSTOM`

Conditions are evaluated per step; `on_failure` policies (`continue`, `abort`, `skip`) are enforced.

`SOAREngine.auto_respond()`:

1. Match playbook
2. Execute if matched
3. Else try Shuffle workflow trigger
4. Else create manual-review recommendation

---

## Log Aggregation

`LogAggregator` dispatches to:

- **GraylogAdapter** (`data/cyber/graylog_buffer/` fallback)
- **OpenSearchAdapter** (`data/cyber/opensearch_buffer/` fallback)

Supports threat event, case, and audit ingestion + federated search.

---

## SOC Dashboard Views

`SOCDashboardProvider` exposes:

- SOC overview summary
- triaged alert queue
- MITRE ATT&CK heatmap
- analyst workbench
- IOC feed

Overview includes open cases, severity/status distributions, mean resolution time, platform connectivity, and analyst workload.

---

## Cyber Training

`CyberTrainingManager` provides synthetic scenario generation:

- `brute_force`
- `malware`
- `data_exfil`
- `ransomware`

Exercises can be run through full SOC pipeline and scored with strengths/improvements/recommendations.

---

## LLM Integration

Air-gapped-safe local simulation behavior:

- Grok-style analysis for enrichment and case reasoning (`QUERY_LLM`)
- Mistral-style report generation fallback for shift/incident summaries

No external API calls are required by default workflow.

---

## API Endpoint Reference (22 endpoints)

### Triage & Cases

1. `POST /cyber/triage`
2. `POST /cyber/cases`
3. `GET /cyber/cases`
4. `GET /cyber/cases/{case_id}`
5. `PATCH /cyber/cases/{case_id}`
6. `POST /cyber/cases/{case_id}/resolve`
7. `POST /cyber/cases/{case_id}/enrich`

### Observables

8. `GET /cyber/cases/{case_id}/observables`
9. `POST /cyber/cases/{case_id}/observables`

### Playbooks & SOAR

10. `GET /cyber/playbooks`
11. `POST /cyber/cases/{case_id}/playbook`
12. `GET /cyber/soar/history`

### SOC Dashboard

13. `GET /cyber/soc/overview`
14. `GET /cyber/soc/alerts`
15. `GET /cyber/soc/mitre-heatmap`
16. `GET /cyber/soc/ioc-feed`

### Log Search

17. `POST /cyber/logs/search`

### Training

18. `POST /cyber/training/exercise`
19. `GET /cyber/training/exercises`
20. `GET /cyber/training/exercises/{id}/score`

### Platforms & Reporting

21. `GET /cyber/platforms/status`
22. `POST /cyber/soc/report`

---

## Configuration

- Main config: `configs/cyber.yaml`
- Playbooks: `configs/cyber/playbooks/*.yaml`
- Optional deps: `requirements-cyber.txt`

All external platform adapters default to disabled/unavailable safe operation with outbox/buffer fallback.

---

## Integration Notes with Phases 1–12

- Uses `src.threat_detection.models.ThreatEvent` as intake source
- Does not modify existing threat detection logic
- Uses only additive modules in `services/cyber`
- API integration requires only one existing file change:
  - include `cyber_router` in `src/api/server.py`

---

## Future Direction

Phase 14 will extend secure communications and command-channel assurance across cyber response workflows, including hardened transport policies and cross-domain alert routing controls.

