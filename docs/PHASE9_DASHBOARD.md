# S3M Phase 9 - Layer 06 Dashboard

## Overview

Phase 9 introduces Layer 06, the operator-facing dashboard for S3M. The dashboard provides a single tactical surface with read-only visibility into Layers 01 through 05, while preserving command authority and secure routing for any state-changing actions through existing API endpoints.

Key goals:
- Unified command center view of all tactical subsystems.
- Human-machine teaming with review queue support.
- Bilingual Arabic/English interface with RTL capability.
- Air-gapped, static frontend deployment compatible with Jetson edge environments.

## Architecture

### Aggregator Pattern

`DashboardAggregator` in `src/dashboard/aggregator.py` coordinates provider classes:

- `COPDataProvider`
- `LLMMonitorProvider`
- `ThreatDashProvider`
- `AutonomyDashProvider`
- `SystemHealthProvider`
- `AlertManager`

The aggregator returns multi-layer overview payloads and health diagnostics. Providers use lazy imports and safe fallback defaults so missing modules do not crash the dashboard.

### Provider Responsibilities

- **COP provider**: agents, threats, tracks, paths, formation context.
- **LLM monitor**: quad-engine status, request metrics, audit feed, routing.
- **Threat dashboard**: threat feed, category/level/source stats, heatmap, sensor health.
- **Autonomy dashboard**: roster, missions, decision feed, review queue, explanation and NL command parsing.
- **System health**: layer-level status, Jetson stats, edge model table, GPS, simulation, API reachability.
- **Alert manager**: cross-layer deduplicated severity-sorted alert stream.

### WebSocket

`WebSocketManager` (`src/dashboard/websocket_manager.py`) tracks active connections and emits JSON messages:

```json
{
  "type": "alert",
  "data": {},
  "timestamp": "2026-03-31T12:00:00+00:00"
}
```

Supported event types:
- `alert`
- `agent_update`
- `threat_event`
- `metrics_update`
- `decision_review`
- `system_warning`

The client auto-reconnects on disconnect and updates status indicators accordingly.

## Frontend Design

Frontend is a single static HTML file:

- File: `src/dashboard/frontend/index.html`
- No npm, no bundler, no external CDN dependencies.
- Embedded CSS + JavaScript only.
- Tactical dark command-center palette optimized for high-contrast displays.

### Views

1. **COP**
   - SVG tactical map with grid, agents, threats, tracks, path overlays.
   - Side panel for agent roster and quick readiness details.

2. **LLM Monitor**
   - Four engine cards.
   - Throughput/latency/uptime metrics.
   - Audit table and routing map.

3. **Threat Intelligence**
   - Threat feed with severity badges and confidence bars.
   - Level/category filters.
   - Distribution bars and event summaries.

4. **Autonomy & Swarm**
   - Agent and mission panels.
   - Decision feed.
   - Human review queue with approve/reject controls.
   - Natural-language command input with EN/AR toggle.

5. **System Health**
   - Layer status matrix.
   - Jetson utilization and thermal indicators.
   - Edge model table, GPS panel, simulation status, API health summary.

## Human-Machine Teaming

Human oversight is central to tactical safety:

- Review queue exposes decisions requiring human authorization.
- `APPROVE` and `REJECT` actions are routed via existing API endpoints:
  - `POST /autonomy/decisions/{id}/approve`
  - `POST /autonomy/decisions/{id}/reject`
- Decision explanation endpoint:
  - `GET /dashboard/autonomy/decisions/{id}/explanation`

NL command support:
- `POST /dashboard/autonomy/command`
- Request body: `{ "text": "...", "language": "en|ar" }`

## Bilingual and RTL

The UI includes an in-browser labels dictionary for English and Arabic. Toggling language:
- switches text labels,
- updates `<html dir>` between `ltr` and `rtl`,
- preserves functional parity across tabs.

## Alert System

AlertManager performs:
- cross-layer collection,
- deduplication using content hashes,
- severity-first sorting,
- active count summaries by critical/high/medium.

Alert inputs include:
- high/critical threat events,
- autonomy decisions requiring review,
- system warnings (thermal/GPS/engine availability).

## API Reference (Dashboard)

### Aggregated
- `GET /dashboard/status`
- `GET /dashboard/overview`
- `GET /dashboard/alerts`
- `GET /dashboard/alerts/count`

### COP
- `GET /dashboard/cop`
- `GET /dashboard/cop/agents`
- `GET /dashboard/cop/threats`
- `GET /dashboard/cop/tracks`
- `GET /dashboard/cop/paths`

### LLM
- `GET /dashboard/llm/status`
- `GET /dashboard/llm/metrics`
- `GET /dashboard/llm/audit`

### Threats
- `GET /dashboard/threats/feed`
- `GET /dashboard/threats/stats`
- `GET /dashboard/threats/heatmap`

### Autonomy
- `GET /dashboard/autonomy/agents`
- `GET /dashboard/autonomy/missions`
- `GET /dashboard/autonomy/decisions/feed`
- `GET /dashboard/autonomy/decisions/review`
- `GET /dashboard/autonomy/decisions/{decision_id}/explanation`
- `POST /dashboard/autonomy/command`

### Review actions (existing workflow routes)
- `POST /autonomy/decisions/{decision_id}/approve`
- `POST /autonomy/decisions/{decision_id}/reject`

### System
- `GET /dashboard/system/health`
- `GET /dashboard/system/jetson`
- `GET /dashboard/system/edge-models`

### WebSocket
- `WS /dashboard/ws`

## Configuration

Dashboard runtime settings live in:
- `configs/dashboard.yaml`

Includes:
- refresh intervals,
- alert thresholds and behavior,
- websocket limits,
- COP bounds and grid behavior,
- display cardinality limits.

## Security Model

- Read-only data collection from layer managers where available.
- Input validation on all API request models.
- Safe fallback defaults if a layer is unavailable.
- No external API calls or cloud dependencies.
- Static frontend with no telemetry, no external assets, no local storage requirement.

## Deployment

Start API + dashboard:

```bash
python scripts/start_dashboard.py
```

Default URLs:
- Dashboard: `http://localhost:8080/dashboard/`
- API docs: `http://localhost:8080/docs`
- WebSocket: `ws://localhost:8080/dashboard/ws`

## Demo Data

Populate representative tactical data:

```bash
python scripts/demo_dashboard_data.py
```

This seeds runtime fallback stores with agents, missions, decisions, threat events, sensor metadata, paths, Jetson stats, edge model rows, and GPS/simulation status.

## Browser Compatibility

Validated target browsers on Jetson command terminals:
- Chromium
- Firefox

No build pipeline required.

## Integration with Previous Phases

Layer 06 imports existing Layer 01/02 modules where present and uses graceful fallback behavior for unavailable Layer 03/04/05 modules. This preserves deployment continuity across phased rollouts.

## Future Work (Phases 10-12)

Potential roadmap areas:
- Advanced geospatial overlays and terrain semantics.
- Mission playback timeline and AAR coupling.
- Operator role-based access and event acknowledgment workflows.
- Hardened WebSocket event auth for multi-tenant command nodes.
