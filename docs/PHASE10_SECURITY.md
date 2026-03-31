# Phase 10 Security & Interoperability Shell

## Overview

Phase 10 adds a **cross-cutting security and coalition interoperability shell** over S3M's existing six layers.  
No existing phase logic is rewritten. Security controls are applied at API ingress/egress and through dedicated services.

- Platform target: NVIDIA Jetson AGX Orin 64GB
- Runtime model: air-gapped/offline by default
- Security model: zero-trust request handling, tamper-evident audit, strict input checks
- Coalition interop: DIS (IEEE-1278.1), C2SIM, BML adapters

## Architecture

Phase 10 is implemented under `src/security/`:

- `middleware.py`: ingress controls (auth, rate limit, sanitization, audit, classification header)
- `input_validator.py`: path traversal, injection, payload size, file-path, classification validation
- `airgap_verifier.py`: local isolation checks (interfaces, DNS, outbound, listeners)
- `crypto/`: encryption, hash-chain audit logs, classification banner tools
- `interop/`: DIS/C2SIM/BML adapters and `InteropManager`
- `compliance/`: compliance checker, vulnerability scanner, combined report generator

Security routes are exposed via `src/api/security_routes.py` and mounted in `src/api/server.py`.

## Zero-Trust Middleware

`SecurityMiddleware` wraps all requests:

1. API key auth (optional in development, mandatory in deployment)
2. Per-IP rate limiting (requests/minute with sliding window)
3. Input sanitization checks for URL/query/path/body
4. Secure audit logging (timestamp, status, latency, auth result)
5. Classification header injection (`X-Classification`)

Bypass paths for auth:

- `/health`
- `/docs`
- `/redoc`
- `/dashboard/`

### Deployment Modes

- **Development**: `auth_enabled=false`, `cors_lockdown=false`
- **Deployment**: set `auth_enabled=true`, replace API key, lock down CORS

## Input Validation

`InputValidator` detects:

- Path traversal: `../`, `..\\`, `%2e%2e`, `/etc/`, `/proc/`, null bytes
- Injection patterns:
  - SQL: `'; DROP`, `UNION SELECT`, `OR 1=1`, suspicious terminal `--`
  - Command: `; rm`, `&& cat`, `| nc`, backticks, `$()`
  - LDAP: `)(`, `*()`
  - XSS: `<script`, `javascript:`, `onerror=`, `onload=`
- Oversized payloads (default 10MB)

Validation is **detection-first**. Input is not semantically rewritten.

### Extending Patterns

Add regex or literal checks in:

- `_INJECTION_REGEX`
- `_PATH_TRAVERSAL_PATTERNS`

Then add unit tests in `tests/test_input_validator.py`.

## Air-Gap Verification

`AirGapVerifier` performs:

1. Network interface inspection (unexpected active interfaces)
2. DNS resolution check (`example.com` should fail)
3. Outbound connectivity check (`8.8.8.8:53` should fail)
4. Listening port inspection (`/proc/net/tcp`, expected local services only)

Linux-only deep checks; non-Linux returns a skipped/inconclusive result.

Configuration:

- `airgap.allowed_interfaces`
- `airgap.allowed_ports`
- `airgap.check_interval_seconds`

## Encryption & Key Management

`DataEncryptor`:

- Key generation via `secrets.token_bytes(32)`
- Keys stored under `configs/keys/` as hex
- Preferred encryption path: `cryptography` Fernet-compatible keying
- Fallback path: XOR stream with SHA-256-derived keystream and integrity digest

> Fallback mode is for **air-gapped development/test continuity only** and is **not production-grade**.

### AES-256 Intent

Primary cryptographic mode uses modern authenticated encryption from `cryptography`.  
The stdlib fallback preserves operational continuity when optional dependency install is unavailable.

## Tamper-Evident Audit Log

`SecureAuditLog` writes JSONL entries in `data/security_audit/`:

- Each entry stores `previous_hash`
- `entry_hash` is SHA-256 over canonicalized entry payload
- Verification recomputes each hash and chain link

This supports forensic integrity and legal defensibility for mission event timelines.

## Classification System

Supported levels:

- `UNCLASSIFIED`
- `UNCLASSIFIED - FOUO`
- `CONFIDENTIAL`
- `SECRET`
- `TOP SECRET`

`ClassificationBanner` provides:

- response header injection (`X-Classification`)
- dashboard banner HTML
- response payload validation helper

Color model:

- Green: UNCLASSIFIED
- Amber: FOUO
- Red: SECRET/TOP SECRET

## DIS Protocol (IEEE-1278.1)

`DISAdapter` supports:

- Entity State PDU (type 1) encode/decode
- Fire PDU (type 2) encode
- Detonation PDU (type 3) encode

Entity mapping includes Saudi country code **178** for friendly assets.

## C2SIM Protocol

`C2SIMAdapter` supports:

- Mission -> Order XML
- Order XML -> mission dictionary
- AAR -> Report XML
- Initialization XML -> scenario dictionary
- Online and offline modes

Offline mode stores outbound messages in:

- `data/interop/c2sim_outbox/`

And reads inbound staging files from:

- `data/interop/c2sim_inbox/`

## BML Protocol

`BMLAdapter` supports:

- WHO/WHAT/WHERE/WHEN/WHY extraction from order XML
- Task mapping to internal command vocabulary
- SITREP/SPOTREP/INTREP generation
- AAR report generation
- Structural validation

### WHAT Mapping

- MOVE, ADVANCE -> MOVE_TO
- DEFEND, HOLD -> HOLD
- ATTACK, ENGAGE -> ENGAGE
- WITHDRAW, RETREAT -> RTB
- PATROL, RECON -> MOVE_TO (+ patrol flag)

## InteropManager

`InteropManager` coordinates all adapters:

- enable/disable protocol adapters
- message send/receive fan-out
- protocol-level counters
- unified message history
- health check

## Compliance Checker

`ComplianceChecker` executes 12 controls:

- SEC-001 auth configured
- SEC-002 rate limiting enabled
- SEC-003 input validation active
- SEC-004 no hardcoded credentials
- SEC-005 model checksum integrity
- SEC-006 air-gap verification
- SEC-007 audit chain validity
- SEC-008 classification set
- SEC-009 CORS policy coherence
- SEC-010 no traversal patterns in configs
- SEC-011 encryption keys exist
- SEC-012 audit file size/rotation health

Output status: `PASS`, `FAIL`, or `PARTIAL`.

## Vulnerability Scanner

`VulnerabilityScanner` includes:

- targeted local port scan
- config risk checks
- key file permissions checks
- dependency version threshold checks
- model artifact checks (pickle/checksum/size/permissions)

Output includes finding counts by severity and detailed remediation hints.

## Security Report Generation

`SecurityReportGenerator` combines compliance and vulnerability output and computes:

- overall risk (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
- critical findings list
- recommended actions

If available, it also queries local S3M LLM orchestrator for narrative analysis.

## API Endpoints (Phase 10)

### Security Core

- `GET /security/status`
- `GET /security/audit`
- `GET /security/audit/verify`
- `POST /security/airgap/verify`
- `GET /security/airgap/status`

### Compliance

- `POST /security/compliance/check`
- `GET /security/compliance/report`
- `POST /security/vulnerability/scan`
- `GET /security/vulnerability/report`
- `POST /security/report/generate`
- `GET /security/report`

### Encryption

- `POST /security/encrypt`
- `POST /security/decrypt`
- `GET /security/classification`

### Interoperability

- `GET /security/interop/status`
- `POST /security/interop/{protocol}/connect`
- `POST /security/interop/{protocol}/disconnect`
- `GET /security/interop/messages`

## Configuration Reference

- `configs/security.yaml`: middleware/auth/classification/encryption/airgap/audit/compliance/vuln/interop settings
- `configs/interop.yaml`: entity/task mapping for DIS/C2SIM/BML

## Deployment Checklist

Before production deployment:

1. Set `middleware.auth_enabled=true`
2. Replace `middleware.api_key` with strong key material
3. Set `middleware.cors_lockdown=true`
4. Generate encryption keys under `configs/keys/`
5. Validate `airgap.allowed_interfaces` and `airgap.allowed_ports`
6. Run compliance + vulnerability scans
7. Verify audit hash chain
8. Confirm classification level matches mission policy

## Integration with Phases 1-9

- Existing phase modules are consumed by import and adapter conversion logic
- API integration occurs through router inclusion and middleware wrapping
- No internal rewrites required for earlier phase subsystems

## Future Work (Phases 11-12)

- Hardware-rooted attestation and secure boot telemetry
- Signed model manifest enforcement with automated quarantine
- Coalition policy engine with mission-specific disclosure controls
- Expanded protocol coverage and schema validation strictness
