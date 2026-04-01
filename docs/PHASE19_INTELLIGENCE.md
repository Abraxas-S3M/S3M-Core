# Phase 19 — Intelligence & OSINT Briefings (Layer 13)

## Overview

Phase 19 extends S3M geopolitical awareness into a full strategic intelligence center. It builds on:

- **Phase 11**: baseline geopolitical risk scoring
- **Phase 13**: cyber threat intelligence feeds
- **Phase 14**: Arabic NLP summarization and language workflows
- **Phase 15**: maritime intelligence inputs

All processing remains **offline and air-gapped** on NVIDIA Jetson AGX Orin.

## Architecture

Primary components in `src/apps/intel/`:

- `models.py`: canonical intelligence dataclasses and enums
- `osint/`: source registry, file ingester, analyzer, collection orchestrator
- `briefings/`: SITREP/INTSUM/threat reports + daily/weekly products
- `monitoring/`: crisis tracker, early warning indicators, geopolitical monitor
- `intel_dashboard.py`: dashboard-ready fused intelligence views
- `intel_manager.py`: central orchestration facade

## OSINT Collection (Air-Gapped)

### Source management

`SourceManager` maintains structured source metadata with NATO reliability grades A–F.

### File-based ingestion

`OSINTIngester` consumes dropped files from watch directory:

- JSON records (`title`, `content`, `timestamp`, `url`, `region`, `topic`)
- CSV columns (`title`, `content`, `timestamp`, `url`, `region`, `topic`)
- TXT lines/paragraphs as discrete items

No external API calls are used.

### Relevance scoring

Scoring emphasizes Saudi/GCC relevance, military-security context, critical topics (Yemen/Hormuz/oil/drone), source reliability weighting, and recency.

## OSINT Analysis

`OSINTAnalyzer` performs:

- Language detection (Arabic/English)
- Entity extraction (military units, weapons, leaders, locations, temporal references)
- Sentiment tagging (`positive`, `negative`, `neutral`, `alarming`)
- Topic mapping (`maritime_security`, `cyber_operations`, etc.)
- Credibility assessment (`confirmed` ... `improbable`)
- Cross-reference fusion across independent sources

## Intelligence Products

Structured output includes:

- **SITREP**
- **INTSUM**
- **WARNORD-compatible reports**
- **Threat assessment**
- **Country brief**
- **Crisis report**
- **Daily Brief**
- **Weekly Estimate**

Bilingual fields (EN/AR) are generated with model fallback templates when local LLMs are unavailable.

## Briefing Generation LLM Pipeline

Design intent:

- **Mistral/planning domain** for structured report format
- **Grok/reasoning domain** for strategic analysis depth
- **ALLaM/arabic domain** for Arabic language briefing output

In offline fallback mode, deterministic templates ensure continuity.

## Geopolitical Monitoring

`GeopoliticalMonitor` fuses:

- Crisis clustering and lifecycle updates
- Indicator threshold warnings
- Region risk deltas via Phase 11 `RiskScorer`

`CrisisTracker` auto-detects crisis signals when >=3 alarming items cluster by region/topic within 24h.

## Early Warning Indicators

Default Saudi-focused indicators (8):

1. Yemen Escalation
2. Hormuz Tension
3. GCC Cyber Threat
4. Drone/UAV Threat Level
5. Oil Infrastructure Risk
6. Border Incursion Risk
7. Regional Proxy Activity
8. Maritime Piracy Index

## Default Intelligence Sources

Default catalog seeds 12 Saudi-relevant source profiles with reliability grading.

## Saudi Monitored Regions

Configured regions include Arabian Peninsula, Persian Gulf, Red Sea, Bab el-Mandeb, Strait of Hormuz, Gulf of Aden, Yemen, Horn of Africa, Levant, Iraq, Iran, and North Africa.

## API Endpoints

Implemented in `src/api/intel_routes.py`:

1. `POST /intel/collect`
2. `GET /intel/items`
3. `GET /intel/items/{id}`
4. `GET /intel/sources`
5. `POST /intel/sources`
6. `POST /intel/sources/defaults`
7. `GET /intel/sources/health`
8. `POST /intel/brief/daily`
9. `POST /intel/brief/weekly`
10. `POST /intel/report/sitrep`
11. `POST /intel/report/intsum`
12. `POST /intel/report/threat`
13. `GET /intel/reports`
14. `GET /intel/reports/{id}`
15. `GET /intel/crises`
16. `POST /intel/crises`
17. `PATCH /intel/crises/{id}`
18. `GET /intel/warnings`
19. `POST /intel/warnings`
20. `POST /intel/warnings/defaults`
21. `GET /intel/overview`
22. `GET /intel/region/{region}`
23. `GET /intel/crises/board`
24. `GET /intel/status`

## Configuration

Primary configuration: `configs/intel.yaml`

Source registry persistence: `configs/intel/sources.yaml`

## Future

Phase 20: **Personnel & Readiness** closes the final S3M expansion phase.
