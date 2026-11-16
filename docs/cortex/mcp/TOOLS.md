# Tool reference - S3M Cortex control-plane MCP contract v0.1

Generated from `src/cortex/mcp_contract/schemas/v0.1/manifest.json` by
`python -m src.cortex.mcp_contract.contract_spec`. Do not edit by hand.

`?` marks an optional argument. Full JSON Schemas (self-contained, 2020-12) are in the manifest.
**proposed** = Abraxas proposal, REQUIRES XIID VALIDATION; **range-implemented** = exists in the S1 mock.

| Tool | Class | Scope | Status | Arguments | Returns | Approvals | Inverse |
|---|---|---|---|---|---|---|---|
| `contract.manifest` | A | `cortex.read` | proposed | none | `contract`, `version`, `manifest_sha256`, `signature_b64`, `key_id` | - | - |
| `inventory.list_routes` | A | `cortex.read` | range-implemented | `cursor`?, `limit`?, `status`? | `routes`, `next_cursor`?, `as_of` | - | - |
| `inventory.list_stlinks` | A | `cortex.read` | range-implemented | `cursor`?, `limit`? | `stlinks`, `next_cursor`?, `as_of` | - | - |
| `inventory.list_tunnels` | A | `cortex.read` | proposed | `cursor`?, `limit`? | `tunnels`, `next_cursor`?, `as_of` | - | - |
| `inventory.list_hosts` | A | `cortex.read` | proposed | `cursor`?, `limit`?, `group`? | `hosts`, `next_cursor`?, `as_of` | - | - |
| `inventory.list_sessions` | A | `cortex.read` | proposed | `cursor`?, `limit`? | `sessions`, `next_cursor`?, `as_of` | - | - |
| `vuln.findings.list` | A | `cortex.read` | range-implemented | `cursor`?, `limit`?, `min_cvss`?, `host`? | `findings`, `next_cursor`?, `as_of` | - | - |
| `telemetry.health` | A | `cortex.read` | range-implemented | none | `scenario_id`?, `stlinks_active`, `routes_active`, `hosts_quarantined`, `as_of` | - | - |
| `telemetry.flow_summary` | A | `cortex.read` | proposed | `route_id`?, `since`?, `until`?, `limit`? | `windows`, `as_of` | - | - |
| `telemetry.events` | A | `cortex.read` | proposed | `types`?, `since`?, `limit`? | `events`, `as_of` | - | - |
| `audit.verify_chain` | A | `cortex.read` | range-implemented | none | `chain_length`, `intact`, `head_digest`? | - | - |
| `change.impact` | B | `cortex.simulate` | range-implemented | `changes` | `affected_routes`, `affected_sessions_30d`, `irreversible`, `as_of` | - | - |
| `policy.simulate` | B | `cortex.simulate` | range-implemented | `changes` | `results`, `as_of` | - | - |
| `route.draft` | B | `cortex.simulate` | range-implemented | `source`, `target`, `service`, `port`, `prefix` | `draft_id`, `status` | - | - |
| `route.narrow` | C | `cortex.write.c` | range-implemented | `route_id`, `prefix`, `approval`, `idempotency_key` | `receipt`, `route` | 1 | `route.restore` |
| `route.restore` | C | `cortex.write.c` | proposed | `route_id`, `approval`, `idempotency_key` | `receipt`, `route` | 1 | self |
| `route.expire` | C | `cortex.write.c` | range-implemented | `route_id`, `approval`, `idempotency_key` | `receipt`, `route` | 1 | `route.restore` |
| `stlink.deploy` | C | `cortex.write.c` | range-implemented | `stlink_id`, `endpoint`, `approval`, `idempotency_key` | `receipt`, `stlink` | 1 | `stlink.disable` |
| `access.create_temporary` | C | `cortex.write.c` | range-implemented | `principal`, `route_id`, `ttl_seconds`, `grant_id`, `approval`, `idempotency_key` | `receipt`, `grant` | 1 | `access.revoke` |
| `access.revoke` | C | `cortex.write.c` | proposed | `grant_id`, `approval`, `idempotency_key` | `receipt`, `grant` | 1 | self |
| `stlink.disable` | D | `cortex.write.d` | range-implemented | `stlink_id`, `approval`, `idempotency_key` | `receipt`, `stlink` | 2 | `stlink.enable` |
| `stlink.enable` | D | `cortex.write.d` | proposed | `stlink_id`, `approval`, `idempotency_key` | `receipt`, `stlink` | 2 | self |
| `session.terminate` | D | `cortex.write.d` | range-implemented | `session_id`, `approval`, `idempotency_key` | `receipt`, `session` | 2 | none |
| `host.quarantine` | D | `cortex.write.d` | range-implemented | `host_id`, `approval`, `idempotency_key` | `receipt`, `host` | 2 | `host.release` |
| `host.release` | D | `cortex.write.d` | proposed | `host_id`, `approval`, `idempotency_key` | `receipt`, `host` | 2 | self |

Error codes: `UNAUTHENTICATED`, `TOKEN_EXPIRED`, `DPOP_INVALID`, `FORBIDDEN_SCOPE`, `SANDBOX_DENIED`, `RESOURCE_DENIED`, `APPROVAL_REQUIRED`, `APPROVAL_INVALID`, `APPROVAL_INSUFFICIENT`, `APPROVAL_REPLAYED`, `SCHEMA_INVALID`, `NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`, `WRITE_BUDGET_EXHAUSTED`, `KILL_SWITCH_ENGAGED`, `INTERNAL`
