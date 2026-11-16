# Authentication and authorization - S3M Cortex MCP contract v0.1

**Status:** proposed; reference implementation in `src/cortex/mcp_contract/tokens.py`
and `authz.py`. Algorithm and lifetimes below are what the reference enforces.

## 1. Principles

1. **Authorization lives outside any model.** A model can propose; only signed human
   approval plus control-plane policy can authorize.
2. **Least privilege per session.** One token = one client, one sandbox, the minimum scopes.
3. **Sender-constrained credentials.** A copied token is useless without the client's private key.
4. **Defense in depth.** The client pre-checks; the control plane decides authoritatively; both use the same rules.
5. **Fail closed.** Unknown sandbox, missing claim, unverifiable signature → refuse with a specific code.

## 2. Authentication (who is calling)

| Element | Specification |
|---|---|
| Client credential | Ed25519 key pair generated and held by the Cortex deployment. Registered with the AS by public key (no shared secrets). |
| Client authentication to AS | `private_key_jwt` (RFC 7523): JWT `{iss=sub=client_id, aud=token endpoint, iat, exp ≤ 60 s, jti}`, EdDSA. `jti` single-use. |
| Access token | JWT, `typ: at+jwt` (RFC 9068), EdDSA. Claims: `iss, sub, client_id, aud (= MCP resource URL, RFC 8707), iat, nbf, exp (iat + 300 s), jti, scope, sandbox, tenant, cnf.jkt`. |
| Sender constraint | DPoP (RFC 9449). Each HTTP request carries `Authorization: DPoP <token>` and a `DPoP` proof JWT (`typ: dpop+jwt`, public JWK in header) with `htm, htu, iat, jti, ath`. Server checks: the JWK thumbprint equals `cnf.jkt`; `htm` and `htu` match; `iat` within 60 s; `ath` = SHA-256 of the token; `jti` not replayed. |
| Transport | TLS 1.3 in any non-range deployment; mTLS optional, in addition to DPoP. |
| Bearer tokens | Refused (401). The contract has no unbound-token mode. |

Production: the AS role is played by the customer's or XiiD's identity provider, which
must issue the same token profile. The reference AS is in-process and range-only.

## 3. Scopes (what class of action)

| Scope | Tool class | Examples |
|---|---|---|
| `cortex.read` | A | inventory, findings, telemetry, audit, manifest |
| `cortex.simulate` | B | `change.impact`, `policy.simulate`, `route.draft` |
| `cortex.write.c` | C | `route.narrow`, `route.restore`, `route.expire`, `stlink.deploy`, `access.*` |
| `cortex.write.d` | D | `stlink.disable/enable`, `session.terminate`, `host.quarantine/release` |

The AS grants the intersection of: the scopes requested, the client's registration, and
the sandbox profile.

## 4. Approval tokens (whether this change happens)

Minted by the **Approval Authority**, only after the Approval Service records enough
distinct approvals from registered devices. Those approvals are Ed25519-signed, carry a
nonce and a freshness window, exclude the proposer, and honour the duress PIN and the
two-person kill switch.

| Claim | Meaning |
|---|---|
| `typ: approval+jwt`, EdDSA | Distinct key from the AS |
| `iss`, `aud` | Approval Authority; the MCP resource URL |
| `sub` | The Cortex client id the approval is for (must equal the access token's client) |
| `act` | Exact tool name |
| `args_sha256` | SHA-256 of canonical JSON of the arguments, excluding `approval` and `idempotency_key` |
| `approvals`, `approval_ids` | Count and ids of distinct device approvals |
| `iat`, `exp` | Lifetime ≤ 900 s |
| `jti` | Single use. A second write with the same token gets `APPROVAL_REPLAYED`. |

Minimum approvals: 1 for reversible class C; **2 for class D and for anything with no
inverse**. A sandbox may raise the minimum (`min_approvals`), never lower it.

## 5. Policy decision order (first failure wins)

1. Kill switch engaged (writes) → `KILL_SWITCH_ENGAGED`
2. Token bound to a known sandbox → `SANDBOX_DENIED`
3. Scope covers the tool class → `FORBIDDEN_SCOPE`
4. Sandbox allows the class and tool name → `SANDBOX_DENIED`
5. Write targets match sandbox resource selectors (default deny) → `RESOURCE_DENIED`
6. Sandbox requires an inverse → `SANDBOX_DENIED`
7. Approval present, valid, for this client, tool and arguments → `APPROVAL_REQUIRED` / `APPROVAL_INVALID`
8. Enough distinct approvals → `APPROVAL_INSUFFICIENT`
9. Per-client and per-tool rate limits → `RATE_LIMITED`
10. Approval not previously used → `APPROVAL_REPLAYED`
11. Sandbox write budget in window → `WRITE_BUDGET_EXHAUSTED`

Input schema validation precedes the PDP (`SCHEMA_INVALID`). An idempotent replay of an
already-applied write returns the cached signed receipt (`replayed: true`), only if rules
2–6 still pass. Every allow-on-write and every deny is emitted as telemetry
(`auth.decision`, `policy.denied`).

## 6. Error model

Errors are MCP tool errors whose text is JSON:
`{"error": {"code", "message", "request_id", "retryable"}}`. Codes are enumerated in
`common.schema.json#/$defs/Error`. Messages never echo token or approval contents.

## 7. Key management (production expectations)

| Key | Storage | Rotation |
|---|---|---|
| Client key | HSM or OS keystore on the Cortex host; never exported | 90 days, or on suspicion |
| AS signing key | IdP HSM | Per IdP policy; publish JWKS with `kid` overlap |
| Approval Authority key | HSM, separate operator group from Cortex operators | 180 days |
| Receipt key | Control-plane HSM | Per vendor; public key pinned by Cortex |
| Contract authority key | Abraxas release HSM | Per contract version |

None of these keys, or any example of them, belong in source control.
