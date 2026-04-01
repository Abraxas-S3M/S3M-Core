# S3M Phase 17 - Layer 11 Procurement & Maintenance

## Overview

Phase 17 introduces Layer 11 for predictive maintenance, asset lifecycle tracking, procurement orchestration, and maintenance intelligence generation. This layer is built for air-gapped deployment and defaults to deterministic, local-only behavior when optional ML/ERP systems are unavailable.

## Architecture

Layer 11 is organized into five service groups:

1. **Predictive Engine** (`services/maintenance/predictive/`)
   - `RULEstimator`: LSTM/GBM/RF adapters with rule-based fallback.
   - `ConditionMonitor`: sensor threshold and trend analysis.
   - `FailureClassifier`: rule-based failure mode inference.
   - `PredictiveEngine`: composition wrapper for unified access.

2. **Asset Management** (`services/maintenance/assets/`)
   - `AssetRegistry`: military asset registry and lifecycle metadata.
   - `FleetManager`: telemetry ingestion, condition updates, RUL updates, readiness views.
   - `ERPAdapter`: ERPNext/Snipe-IT/GLPI/Dolibarr adapter with standalone outbox fallback.

3. **Procurement & Scheduling** (`services/maintenance/procurement/`)
   - `SparePartsManager`: stock, reorder checks, value tracking.
   - `ProcurementTracker`: request lifecycle and automatic generation.
   - `MaintenanceScheduler`: work order generation/lifecycle and calendar views.

4. **Manager Orchestration** (`services/maintenance/manager.py`)
   - `MaintenanceManager`: end-to-end coordination for telemetry -> prediction -> work order -> procurement.

5. **API Layer** (`src/api/maintenance_routes.py`, `src/api/maintenance_models.py`)
   - 22 maintenance endpoints for assets, telemetry, prediction, scheduling, procurement, inventory, readiness, and health.

## Predictive Engine Details

### RUL Estimation

`RULEstimator` backend order:

1. LSTM (`models/maintenance/rul_lstm.pt`)
2. GBM (`models/maintenance/rul_gbm.pkl`)
3. RF (`models/maintenance/rul_rf.pkl`)
4. Rules fallback

Rule-based CMAPSS-inspired thresholds:

- Temperature > 500C -> RUL constrained below 50h
- Vibration > 5g -> RUL constrained below 100h
- Pressure drop > 20% baseline -> RUL constrained below 200h
- Otherwise linear degradation based on asset type max life minus operating hours

Risk bands:

- `critical`: RUL < 50h
- `high`: RUL < 200h
- `medium`: RUL < 500h
- `low`: otherwise

### Condition Monitoring

Default sensor thresholds:

- `temperature_c`: warning 450, critical 520
- `vibration_g`: warning 3.5, critical 5.0
- `pressure_psi`: warning_low 25, critical_low 20
- `oil_temp_c`: warning 110, critical 130
- `rpm_deviation_pct`: warning 5, critical 10

Trend detection computes per-sensor slope over a rolling window and flags degrading channels when slope approaches critical threshold by >1% per reading.

### Failure Classification Modes

Implemented failure modes and signatures:

- `bearing_degradation`: high temp + high vibration
- `combustion_issue`: high temp + normal vibration
- `seal_leak`: low pressure + high oil temp
- `blade_imbalance` (air) / `alignment_issue` (ground/naval): high vibration + normal temp
- `control_system_fault`: high RPM deviation
- `gradual_wear`: default for normal readings

## Asset Registry and Saudi Fleet Template

`AssetRegistry.create_saudi_fleet_template()` creates 20 assets:

- 6x F-15SA fighter jets
- 4x AH-64 Apache helicopters
- 4x M1A2 Abrams tanks
- 3x patrol boats
- 2x radar systems
- 1x MQ-9 class UAV

Template data includes realistic operating hours, maintenance windows, and condition variation to support predictive and scheduling demonstrations.

## Fleet Pipeline

Operational flow:

1. Telemetry ingested by `FleetManager`.
2. `ConditionMonitor` evaluates sensor status and alerts.
3. After 10+ telemetry records, `RULEstimator` produces RUL predictions.
4. Asset condition and RUL are persisted in `AssetRegistry`.
5. Critical condition transitions generate alert events.
6. Scheduler and procurement modules consume updated asset state.

## Procurement and Spare Parts

### Spare Parts

`SparePartsManager` supports:

- add/get/filter parts
- consume/restock
- reorder checks
- total inventory valuation
- standard 20-part military catalog bootstrap

### Procurement Tracking

`ProcurementTracker` supports:

- request creation and approval
- status updates
- filtered retrieval and pending queues
- auto-generation from missing work-order parts
- auto-generation from low-stock inventory

## Maintenance Scheduling

`MaintenanceScheduler.generate_work_orders()` creates work orders from:

1. Calendar due maintenance
2. Predictive low-RUL triggers
3. Condition-based triggers for POOR/CRITICAL assets

Priority policy:

- `EMERGENCY`: critical condition or RUL < 50h
- `URGENT`: RUL < 200h
- `ROUTINE`: calendar-driven
- `SCHEDULED`: planned work

Scheduler supports approve/start/complete lifecycle, calendar schedule views, and backlog reporting.

## ERP Integration

`ERPAdapter` probes localhost ERP backends:

- ERPNext
- Snipe-IT
- GLPI
- Dolibarr

If unavailable, backend switches to `standalone` and logs outbound sync operations in an outbox queue for deferred reconciliation.

## LLM Integration

Mistral-domain prompts are used where available for:

- condition reports
- scheduling recommendations
- fleet reports
- RUL action recommendation text

Air-gapped fallback templates are always provided to guarantee deterministic offline output.

## API Endpoints (22)

### Assets

- `POST /maintenance/assets`
- `GET /maintenance/assets`
- `GET /maintenance/assets/{id}`
- `GET /maintenance/assets/critical`
- `GET /maintenance/assets/due`
- `POST /maintenance/assets/template/saudi`

### Telemetry & Prediction

- `POST /maintenance/telemetry`
- `POST /maintenance/predict/{asset_id}`
- `GET /maintenance/predict/{asset_id}`
- `GET /maintenance/condition/{asset_id}`

### Work Orders

- `POST /maintenance/work-orders/generate`
- `GET /maintenance/work-orders`
- `PATCH /maintenance/work-orders/{id}`
- `GET /maintenance/schedule`

### Procurement

- `POST /maintenance/procurement/check`
- `GET /maintenance/procurement/requests`
- `PATCH /maintenance/procurement/requests/{id}`

### Spare Parts

- `GET /maintenance/parts`
- `POST /maintenance/parts`
- `GET /maintenance/parts/reorder`

### Fleet & Status

- `GET /maintenance/fleet/health`
- `GET /maintenance/fleet/readiness`
- `POST /maintenance/fleet/report`
- `GET /maintenance/status`

## Configuration

See `configs/maintenance.yaml` for:

- predictive backend settings
- RUL/condition thresholds
- asset maintenance intervals
- fleet readiness target
- procurement lead-time defaults
- spare-parts safety settings
- ERP connection defaults
- scheduler horizon/auto-approve behavior

## Relationship to Phase 11 Logistics

Phase 17 extends logistics-layer sustainment by coupling:

- sensor-driven degradation forecasts
- maintenance workload generation
- procurement automation

The result is tighter feedback between readiness degradation and resupply action, while preserving all Phase 1-16 packages unchanged.

## Future Direction (Phase 18)

- high-fidelity maintenance simulation and technician training loops
- learned failure progression on platform-specific telemetry signatures
- mission-aware maintenance optimization under contested logistics constraints
