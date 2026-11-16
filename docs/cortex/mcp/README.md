# S3M Cortex control-plane MCP contract v0.1

Abraxas-owned MCP server/client contract between Cortex (S3M) and a security control
plane (first target: XiiD). It is implemented end to end in the synthetic range.
Nothing here is validated against a live XiiD deployment; tools marked *proposed*
**require XiiD validation**.

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Components, trust boundaries, three-key model, write sequence, manifest, measured results, questions for XiiD |
| [TOOLS.md](TOOLS.md) | All 30 tools (contract 0.1.2): class, scope, status, arguments, returns, approvals, inverse (generated) |
| [AUTH.md](AUTH.md) | Authentication (private_key_jwt, DPoP-bound access tokens), scopes, approval tokens, decision order, errors, key management |
| [SANDBOXES.md](SANDBOXES.md) | Five permission profiles, read/write matrix, hypothetical XiiD sandbox deployment and entry criteria |
| [TELEMETRY.md](TELEMETRY.md) | Event envelope, 8 event types, MCP access, representative one-hour sample |

Machine-readable contract: `src/cortex/mcp_contract/schemas/v0.1/`
(`manifest.json`, `common.schema.json`, `telemetry.schema.json`).

```bash
python -m src.cortex.mcp_contract.contract_spec     # regenerate schemas + TOOLS.md
python -m range.run_contract_cycle --scenario all   # SIM-002 and SIM-005 over the contract
python -m pytest tests/cortex/test_mcp_contract.py -q
```
