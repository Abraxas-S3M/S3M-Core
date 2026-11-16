# Capability 13 - QuantumWatch

**Status:** implemented and tested. Code discovery runs on real source (this repository).
Fabric discovery and planning run on the synthetic enterprise_200 range. The CRQC
timeline is a customer-owned assumption, not a forecast. Code: `src/cortex/quantumwatch/`.

## What it does

| Stage | Method |
|---|---|
| Discover: code | AST scan of Python (never executed). It recognises crypto API use: `cryptography`, `hashlib`/`hmac`, PyJWT algorithm strings, `ssl`, liboqs. It records `file:line` evidence and honours `usedforsecurity=False`. |
| Discover: fabric | Each XiiD route's service implies its protocol and usual key exchange (confidence `inferred`). SealedTunnel routes are recorded as the vendor's *claimed* PQ profile. |
| Discover: declared | The customer inventory (`configs/cortex/cbom_inventory.yaml`) plus range declarations (PKI, VPN IKE, firmware signing, backup encryption). |
| Reconcile | Declared-but-not-found vs found-but-not-declared. |
| Classify | One catalogue (`catalog.py`): broken by Shor, Grover-reduced, PQ, hybrid, or classically broken. It is checked against an approved profile: **NIST IR 8547 final** (all quantum-vulnerable public-key crypto deprecated after 2030, disallowed after 2035) or **CNSA 2.0** (ML-KEM-1024, ML-DSA-87, AES-256, SHA-384/512; networking and software signing exclusive by 2030; web, cloud, OS and custom applications by 2033). Profile facts were checked on 16 Nov 2026 (`configs/cortex/quantum_profiles.yaml`). |
| Risk | Mosca's inequality integrated over time. For confidentiality, traffic captured each quarter is lost if a CRQC arrives within its secrecy lifetime (value × capture × F(t + x)). For signatures, forgery becomes possible once a CRQC exists (value × trust lifetime × F(t)). |
| Plan | CP-SAT over 36 quarters (2027–2035). Inputs: engineer-week capacity, effort spread for large items, dependencies (root CA before issuing CA), hard profile deadlines. Two options: **native migration**, or a **XiiD SealedTunnel overlay** for transport confidentiality (0.5 week per route; mitigates harvest-now-decrypt-later, does not count for compliance). |
| Output | CycloneDX 1.6 CBOM with primitive, security levels, evidence, source, confidence and quantum status per asset. |

## Measured (tests/cortex/test_quantumwatch.py, 11 tests)

**On this repository's real code:**
- Ed25519 signing in the MCP token service, contract manifest and ProofGuard ledger: quantum-vulnerable, to migrate by 2030 (deprecation) / 2035 (disallowance).
- Six MD5 uses outside Cortex: to be marked `usedforsecurity=False` or replaced.
- **Inventory gap:** the declared CBOM says AES-256-GCM for sealed audit entries, but the code uses Fernet (AES-128-CBC + HMAC). Under CNSA 2.0 that is below profile.
- liboqs use is found, but its parameter set is chosen at run time and cannot be confirmed statically, so it is not counted as compliant.

**On the range:**
- Three cleartext paths are broken today (RTSP cameras → NVR, LDAP CI → DC, IPP printing).
- 12 SealedTunnel routes are `claimed_pq_unverified`.

**Plan vs deadline-first practice** (native only, earliest deadline then highest risk; both meet every deadline):

| Profile, capacity | Optimised risk | Baseline risk | Reduction |
|---|---|---|---|
| NIST IR 8547, 12 wk/quarter | 4.15 | 7.25 | 43% |
| CNSA 2.0, 12 wk/quarter | 4.15 | 13.11 | 68% |
| CNSA 2.0, 6 wk/quarter | 9.32 | 31.56 | 70% |

**How much rests on the XiiD claim:** with the overlay available, risk is 4.15. Without it,
risk is 6.82, which is still better than the baseline. If the overlay's PQ protection turns
out not to hold (residual 1.0), the plan converges to the no-overlay result (tested). The
overlay is the fastest harvest-now-decrypt-later mitigation *if* XiiD documents a PQ
profile.

When deadlines cannot be met, the plan says so (`DEADLINES_INFEASIBLE`, with the misses
listed) instead of returning a schedule that quietly ignores them.

## Limits

- Fabric crypto is inferred from service type. Production needs handshake probes (TLS/SSH
  key-exchange groups) or XiiD reporting each tunnel's crypto profile (**REQUIRES XIID
  VALIDATION**).
- The code scanner covers Python only. Java, Go, C and configuration files (TLS cipher
  strings, sshd) are follow-ups.
- Risk is relative. The CRQC CDF and data lifetimes are placeholders the customer's risk
  owner must set.
