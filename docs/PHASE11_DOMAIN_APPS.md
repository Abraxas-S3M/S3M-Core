# S3M Phase 11 — Domain Applications

UNCLASSIFIED - FOUO

## 1) Architecture Overview

Phase 11 introduces **vertical domain applications** that orchestrate existing S3M horizontal layers end-to-end:

- Layer 01 (LLM Core): task routing, tactical/reasoning/planning/Arabic responses
- Layer 02 (Threat Detection + Sensor Fusion): threat feeds, anomaly and visual detections
- Layer 03 (Autonomy): mission execution and swarm behaviors (if available in deployment)
- Layer 04 (Simulation): scenario loading, OPFOR behavior, AAR generation
- Layer 05 (Navigation): path and trajectory utilities (if available in deployment)
- Layer 06 (Dashboard): downstream consumer of API outputs
- Security Shell: input validation, auditable deterministic fallbacks, air-gap assumptions

Domain apps are intentionally **thin orchestration layers**. They call existing modules where present and degrade safely to deterministic templates when unavailable.

---

## 2) Battle Planning Application

Path: `src/apps/battle_planning/`

### Workflow

1. Mission brief in
2. OPORD generation (5-paragraph structure)
3. OPORD -> Scenario translation
4. Scenario simulation run
5. COA comparison and recommendation

### Components

- `OpsOrderGenerator`
  - Uses planning domain routing for OPORD text
  - Supports Arabic prompt routing through ALLaM (`generate_arabic`)
  - Produces deterministic OPORD template when engines are not loaded
  - Includes strict `validate_opord`
- `PlanToSimBridge`
  - Extracts force/objective intent from OPORD
  - Builds `ScenarioEngine.load_from_dict()` compatible payload
  - Executes scenario via `ScenarioRunner` + `OpForGenerator`
  - Converts OPORD to autonomy-mission-like dict
- `COAComparator`
  - Generates 3 doctrinal profiles:
    - Aggressive / weapons_free
    - Cautious / weapons_tight
    - Stealth / weapons_hold
  - Runs each COA through simulation
  - Ranks by objectives/losses/time score
  - Uses reasoning engine when available, otherwise metrics-only recommendation
- `BattlePlanner`
  - Full pipeline orchestration
  - Quick field assessment mode (`quick_assess`)
  - Session history + health check

---

## 3) Logistics Application

Path: `src/apps/logistics/`

### Capabilities

- Supply disruption prediction from shipment records
- Threat-aware convoy route optimization
- Inventory tracking and restock management

### Components

- `SupplyChainPredictor`
  - Extracts numerical features (`delay_hours`, `weight`, `priority`, `route_distance`)
  - Uses Layer 02 `AnomalyDetector`
  - Sends anomaly details for planning-domain analysis when available
  - Falls back to template recommendations
- `ConvoyRouteOptimizer`
  - Uses ThreatManager-derived overlays (MEDIUM+ levels) when not provided
  - Converts threat levels to standoff radii:
    - CRITICAL 100m, HIGH 75m, MEDIUM 50m
  - Produces primary and optional wider-avoidance alternative route
  - Computes distance, ETA, threats-near-route, and risk score
- `InventoryTracker`
  - In-memory inventory with add/update/filter
  - Restock threshold detection (`shortfall`)
  - Supply report via planning engine or deterministic template
  - JSON export support
- `LogisticsModule`
  - Top-level orchestration API (`predict`, `optimize_route`, `check_inventory`, `generate_report`)

---

## 4) Threat Hunting Application

Path: `src/apps/threat_hunting/`

### Correlation Patterns

`ThreatCorrelator` detects:

1. `coordinated_cyber`: >=3 CYBER events from same source in window
2. `multi_domain`: CYBER + KINETIC co-located in cluster (hybrid)
3. `escalation`: LOW -> MEDIUM -> HIGH progression by actor/source
4. `swarm`: >=5 KINETIC events from distributed positions converging

### OSINT Fusion

`OSINTFuser`:

- Ingests `.txt`, `.csv`, `.json`
- Extracts entities (locations/org-like tokens, dates, threat indicators)
- Performs analysis with reasoning engine when available
- Otherwise returns deterministic unavailable-analysis response
- Air-gap flow: operator drops files into `data/osint/`

### Escalation Workflow

`EscalationManager`:

- Deterministic auditable rule matching
- No arbitrary expression execution
- Tracks history, active escalations, and resolution state

`ThreatHuntingModule`:

- Correlate -> Escalate -> Summarize
- Exposes OSINT analysis and threat landscape rollup

---

## 5) Geopolitical Risk Application

Path: `src/apps/geopolitical/`

### Method

- `RiskScorer`
  - Region/topic scores 0..100
  - Event-driven deltas
  - Auto-decay (default 1 point/hour)
  - Trend derived from recent score deltas
- `EventAnalyzer`
  - Structured analysis output including impact, escalation likelihood, posture, and watch indicators
  - Arabic support via ALLaM route (`analyze_arabic`)
  - Fallback output when LLM not loaded
- `GeopoliticalForecaster`
  - Uses current score/trend/history
  - LLM forecast when available
  - Deterministic trend extrapolation fallback
- `GeopoliticalModule`
  - End-to-end analysis + risk update + forecasting

---

## 6) Drone Operations Application

Path: `src/apps/drone_ops/`

### Lifecycle

1. Mission planning
2. Autopilot bridge connection
3. Mission launch/abort control
4. ATR processing from camera frames
5. Replan recommendation trigger on high-confidence threats

### Components

- `MissionPlanner`
  - Plans mission from structured request or natural language
  - Uses existing autonomy/navigation components when available
  - Falls back to deterministic planner when unavailable
- `AutopilotBridge`
  - Backend auto-detect:
    - MAVLink (`pymavlink`) if present
    - Simulated fallback otherwise
  - Maps S3M commands to MAVLink command IDs
  - Simulated telemetry advances toward last waypoint
- `ATRIntegrator`
  - Uses Layer 02 `ObjectDetector`
  - Converts detections to threat events
  - Replan trigger if confidence > 0.7 and threat >= HIGH
- `DroneOpsModule`
  - Orchestrates planning, launch, ATR, fleet status, and health

---

## 7) Data Management Application

Path: `src/apps/data_management/`

### Dataset Registry

- `DatasetRegistry` loads `configs/datasets/registry.yaml`
- Returns dataset metadata with local availability checks
- Includes air-gap acquisition guidance

### Data Loading

- `DataLoader` supports:
  - CSV
  - JSON
  - Text
  - Image directory cataloging (metadata only; no heavy image loading)
- Provides lightweight schema introspection

### Benchmarking

- `BenchmarkHarness`
  - Loads datasets via registry + loader
  - Runs task mode `detection` or `anomaly`
  - Uses deterministic stub metrics if models are not loaded
  - Stores benchmark results and supports comparison/export

---

## 8) LLM Integration Matrix

- **Phi-3 tactical**: battle quick assess, OPORD execution parsing prompts, tactical drone planning extraction
- **Grok reasoning**: COA comparison rationale, threat hunting landscape, geopolitical analysis/forecasting, OSINT analysis
- **Mistral planning**: OPORD generation, logistics supply reports/disruption analysis
- **ALLaM Arabic NLP**: Arabic OPORD generation, Arabic geopolitical analysis

All modules include **engine-unavailable fallback behavior**.

---

## 9) Arabic Support

Arabic I/O support is implemented in:

- `OpsOrderGenerator.generate_arabic()`
- `EventAnalyzer.analyze_arabic()`
- Drone mission NL parsing supports `language="ar"` routing behavior in planner input extraction logic.

---

## 10) API Reference (Phase 11 Endpoints)

Router file: `src/api/apps_routes.py`

### Battle Planning

- `POST /apps/battle/opord`
- `POST /apps/battle/simulate`
- `POST /apps/battle/compare-coa`
- `GET /apps/battle/plans`

### Logistics

- `POST /apps/logistics/predict`
- `POST /apps/logistics/route`
- `GET /apps/logistics/inventory`
- `POST /apps/logistics/restock-check`

### Threat Hunting

- `POST /apps/threats/correlate`
- `POST /apps/threats/osint/analyze`
- `GET /apps/threats/escalations`
- `POST /apps/threats/escalations/rules`

### Geopolitical

- `POST /apps/geopolitical/analyze`
- `GET /apps/geopolitical/risks`
- `POST /apps/geopolitical/forecast`
- `GET /apps/geopolitical/trends`

### Drone Ops

- `POST /apps/drone/mission`
- `POST /apps/drone/mission/nl`
- `GET /apps/drone/missions`
- `POST /apps/drone/missions/{id}/abort`

### Data Management

- `GET /apps/data/datasets`
- `GET /apps/data/datasets/{id}`
- `POST /apps/data/benchmark`
- `GET /apps/data/benchmarks`
- `GET /apps/data/stats`

---

## 11) Configuration

- App config: `configs/apps.yaml`
- Dataset registry: `configs/datasets/registry.yaml` (32 entries)

---

## 12) Integration with Phases 1–10

Phase 11 modules are additive and import-driven. Existing Phase 1–10 components are not reimplemented. The only core modification required is API router inclusion in:

- `src/api/server.py`:
  - `from src.api.apps_routes import apps_router`
  - `app.include_router(apps_router, tags=["Domain Applications"])`

---

## 13) Demo Scripts

- `scripts/run_battle_planning_demo.py`
- `scripts/run_logistics_demo.py`
- `scripts/run_threat_hunting_demo.py`
- `scripts/run_drone_ops_demo.py`
- `scripts/demo_dataset_registry.py`

These demos run fully offline and rely on deterministic fallbacks when optional runtime dependencies are unavailable.

---

## 14) Future Work (Phase 12)

- Deep integration with live autonomy/navigation runtime packages across all deployment profiles
- Rich dashboard widgets for domain app outputs (COP overlays, COA scorecards, escalation timelines)
- Policy-guarded automated responses for selected escalation classes
- Expanded benchmark harness with real model adapters and gold-standard label evaluation pipelines
- End-to-end mission thread persistence across planning, execution, and AAR/Intel workflows
