# S3M Phase 20 — Personnel & Readiness (Layer 14)

Phase 20 introduces the **Personnel & Readiness** layer, the human-readiness dimension of military capability. This final layer completes the 14-layer sovereign stack by tracking whether units have trained, medically fit, and properly cleared people assigned to mission-critical roles.

## Architecture Overview

The layer is implemented in `apps/readiness/` with these subsystems:

- `PersonnelRegistry`: bilingual personnel records with Saudi military rank and branch structures.
- `CertificationManager`: military training certification issuance, lifecycle, renewal, and sync adapters.
- `UnitManningManager`: TO&E slot management, vacancy tracking, and priority auto-fill.
- `EligibilityEngine`: rule-based deployment eligibility and readiness categorization.
- `ReadinessCalculator`: unit and force readiness scoring.
- `CoalitionPersonnelBridge`: GCC partner roster interoperability and certification equivalence checks.
- `HRAdapter`: standalone mode with ERP adapter shape for ERPNext/Odoo/OrangeHRM integration.
- `ReadinessDashboardProvider`: overview, manning board, member profile, and unit detail aggregation.
- `ReadinessManager`: single orchestration facade for API and demos.

## Personnel Registry

Personnel records include:

- Saudi-aligned rank ladder: `PRIVATE` through `GENERAL`
- Branch taxonomy: Army, Air Force, Navy, Royal Guard, Special Forces, Cyber, Logistics, Medical, Intelligence, Joint
- MOS, clearance, medical status, deployment status, specializations, and languages
- Bilingual fields (`name_en`, `name_ar`, `unit_name_en`, `unit_name_ar`, `mos_description_en`, `mos_description_ar`)

### Sensitive Data Protection

Personnel contact data is encrypted through Phase 10 crypto (`DataEncryptor`) and changes are audit-logged through `SecureAuditLog`. Operational views use `to_safe_dict()` to avoid exposing contact payloads.

## Saudi Battalion Template

`create_saudi_battalion_template()` produces 45 bilingual personnel:

- 1 × Lieutenant Colonel
- 3 × Major
- 6 × Captain
- 12 × First/Second Lieutenant
- 8 × Staff/First Sergeant
- 15 × Sergeant/Corporal

Status mix is represented for realistic readiness:

- 38 active duty
- 3 deployed
- 2 training
- 1 medical leave
- 1 administrative leave

## Certification System

Ten standard certification types are provided (5 S3M-specific + 5 traditional military):

1. `S3M_WARGAMING_L1`
2. `S3M_CYBER_DEFENDER`
3. `S3M_MARITIME_WATCH`
4. `S3M_AUTONOMY_CMD`
5. `S3M_COALITION_COORD`
6. `UAV_OPERATOR`
7. `NBC_QUALIFIED`
8. `COMBAT_MEDIC`
9. `JUMPMASTER`
10. `SIGNALS_OPERATOR`

Lifecycle operations:

- issue
- renew
- suspend
- revoke
- expiring/expired scans
- requirement checks (`met`, `missing`, `expired`)

## Unit Manning

Unit manning uses slot-based TO&E tables:

- required rank
- required MOS
- required clearance
- required certifications

Auto-fill prioritization enforces tactical leadership continuity:

1. Officer slots
2. NCO slots
3. Enlisted slots

`create_from_orbat()` supports ORBAT-driven structure when available and uses deterministic fallback structure when not.

## Deployment Eligibility

Seven rules are implemented:

- Mandatory (3)
  - `active_duty`
  - `medical_fit`
  - `clearance_valid`
- Optional (4)
  - `no_pending_evaluation`
  - `time_since_last_deployment`
  - `training_current`
  - `min_time_in_grade`

Output:

- `eligible` boolean
- checks with pass/fail details
- readiness color (`green` / `amber` / `red`)
- disqualifiers and recommendations

## Readiness Calculation

Readiness weighting:

- Personnel readiness: 40%
- Training readiness: 30%
- Equipment readiness: 30%

Thresholds:

- GREEN: >= 80
- AMBER: >= 60
- RED: < 60

Equipment readiness attempts integration with maintenance fleet readiness and falls back to 75% when unavailable in offline mode.

## Coalition Bridge

Coalition interoperability supports GCC partner codes:

- 178 Saudi Arabia
- 223 United Arab Emirates
- 117 Kuwait
- 16 Bahrain
- 164 Qatar
- 154 Oman

It includes certification equivalence mapping and compatibility gap reporting for coalition operations.

## HR Adapter

`HRAdapter` models backend detection and sync flow for:

- ERPNext
- Odoo
- OrangeHRM
- standalone fallback

In air-gapped deployments, standalone mode remains authoritative and no external API calls are required.

## Arabic Bilingual Coverage

Bilingual output is present in:

- personnel names
- MOS descriptions
- unit names
- certification names
- eligibility reports
- readiness and manning reports

## Integration With Existing Layers

- Layer 10 (Interop/ORBAT): optional ORBAT-to-manning bridge
- Layer 11 (Maintenance): equipment readiness contribution
- Layer 12/13 references: training-sync adapter pattern for completion-derived cert issuance
- Layer 06 dashboard: readiness overlay via `ReadinessDashboardProvider`

## API Endpoints

The readiness API exposes personnel, certifications, unit manning, eligibility, force readiness, coalition, reporting, and health endpoints under `/readiness/*` via `src/api/readiness_routes.py`.

## Configuration

`configs/readiness.yaml` includes:

- personnel limits and auditing controls
- certification validity defaults
- manning critical ranks
- eligibility rule sets
- readiness weighting and thresholds
- coalition partner definitions
- HR adapter backend settings

## Completion Statement

**THE 14-LAYER STACK IS COMPLETE** with Personnel & Readiness as Layer 14, providing sovereign, bilingual, and air-gapped-ready force readiness orchestration for Saudi MOD operational context.
