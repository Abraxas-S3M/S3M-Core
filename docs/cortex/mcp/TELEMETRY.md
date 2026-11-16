# Representative telemetry - S3M Cortex MCP contract v0.1

**Status:** schema proposed; generator and one-hour sample are synthetic. Whether XiiD can
emit these aggregates **requires XiiD validation** (see ARCHITECTURE.md §8).

## 1. Why Cortex needs it

The twin can model reachability, but it cannot judge *disruption* without evidence of
use. Telemetry supplies that evidence:

- **Flow summaries** separate an unused route (safe to expire) from a lightly used one (narrow it instead).
- **Heartbeats and tunnel state** confirm that enforcement is live after a change.
- **Auth and change events** let Cortex and auditors reconcile every decision with every applied change.

## 2. Envelope (all events)

Schema: `src/cortex/mcp_contract/schemas/v0.1/telemetry.schema.json`
(`$id urn:s3m:cortex-mcp:0.1:telemetry`).

| Field | Type | Notes |
|---|---|---|
| `schema` | const `s3m.cortex.telemetry/0.1` | Versioned; breaking changes bump the minor |
| `event_id` | 32 hex characters | Deterministic in generated data; random (UUIDv4 hex) on the live server |
| `type` | enum | One of the 8 types below |
| `time` | RFC 3339 UTC | End of the window for aggregates |
| `source` | `{system, component}` | `system`: `control-plane`, `cortex` or `approval-authority` |
| `tenant`, `sandbox` | strings | `sandbox` present on events caused by a client call |
| `severity` | `debug`, `info`, `warning`, `critical` | |
| `attributes` | object | Validated per `type` (below). Names follow OpenTelemetry semantic conventions where one exists (`network.transport`, `server.port`, `client.id`), `s3m.*` otherwise. |

## 3. Event types

| Type | Emitted | Key attributes |
|---|---|---|
| `flow.summary` | Every 5 min per route | `s3m.route.id`, `s3m.window.start`, `s3m.sessions`, `s3m.unique_sources`, `s3m.bytes_in/out`, `s3m.denied_attempts`, `s3m.sealed_tunnel` |
| `stlink.heartbeat` | Every 5 min per STLink | `s3m.stlink.id`, `s3m.status`, `s3m.latency_ms`, `s3m.tunnels` |
| `tunnel.state` | Every 5 min per SealedTunnel | `s3m.tunnel.id`, `s3m.route.id`, `s3m.status`, `s3m.rekey_age_s` |
| `auth.decision` | Every allowed write | `s3m.tool`, `s3m.decision`, `s3m.code`, `client.id`, `s3m.request_id` |
| `policy.denied` | Every refusal | Same as `auth.decision`, with the refusal code |
| `change.applied` | Every applied write | `s3m.tool`, `s3m.resource`, `s3m.receipt.digest`, `s3m.approval.jti`, `client.id` |
| `change.rolled_back` | Rollback writes (reserved) | As `change.applied` |
| `anomaly.flag` | Detector output | `s3m.route.id`, `s3m.kind` (`denied_spike`, `new_source`, `volume_spike`, `tunnel_flap`), `s3m.score`, `s3m.detail` (untrusted text) |

## 4. Access over MCP

- `telemetry.flow_summary {route_id?, since?, until?, limit?}` returns 5-minute windows (≤ 24 h per call).
- `telemetry.events {types?, since?, limit?}` returns recent typed events from the server buffer.
- `telemetry.health` returns aggregate counters.

All three are class A (`cortex.read`) and allowed in every profile except
`sbx-agent-untrusted`, which gets only `telemetry.health`.

## 5. Representative sample

`docs/cortex/mcp/samples/telemetry_enterprise_200_1h.jsonl` holds one hour (06:00–07:00 UTC,
09:00–10:00 local, a working day) for the 200-host enterprise. That is 721 events: 504 flow
summaries (42 routes × 12 windows), 72 STLink heartbeats, 144 tunnel-state events, and
**1 planted anomaly**: 37 denied attempts in one window on `rt-cams-corp`, the flat
legacy route from CCTV cameras into the corporate user network.

Every event validates against the schema (tested). The generator is deterministic. Volumes
come from each route's `observed_sessions_30d` and a Sunday–Thursday office-hours duty cycle:

```bash
python - <<'PY'
import yaml, json
from datetime import datetime, timezone
from src.cortex.mcp_contract.telemetry import generate
s = yaml.safe_load(open("range/mock_xiid_mcp/scenarios/enterprise_200.yaml"))
for e in generate(s, start=datetime(2026, 11, 15, 6, tzinfo=timezone.utc), hours=1):
    print(json.dumps(e, sort_keys=True))
PY
```

## 6. Next uses in Cortex (not yet wired)

- Feed `flow.summary` into the twin in place of the static `observed_sessions_30d`.
- Treat `anomaly.flag` as a trigger for a defense cycle on the flagged route.
- Reconcile `change.applied` digests with Cortex's own receipts in the evidence bundle.
