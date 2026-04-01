# S3M Phase 14 — Layer 08 Secure Communications

## Overview

Layer 08 introduces a resilient, encrypted military communications subsystem for air-gapped and denied environments. It supports tactical messaging across multiple relay backends, priority-aware C2 routing, Arabic/English NLP summarization, and comms-derived intelligence extraction for downstream threat workflows.

## Architecture

Primary components:

- **CommsManager**: top-level orchestration for message send/receive, security, NLP, routing, and node management.
- **RelayManager**: backend abstraction and fallback chain execution.
- **Platform adapters**:
  - Matrix (Synapse)
  - Meshtastic (LoRa mesh)
  - XMPP (ejabberd/Prosody)
  - Rocket.Chat
  - P2P UDP relay
  - Simulated relay (always available fallback)
- **ArabicNLPEngine**: layered fallback for summarization and extraction.
- **C2MessageRouter**: priority/type/intent-aware routing logic.
- **MessageIntelExtractor**: threat/entity extraction with ThreatManager handoff.
- **CommsSecurityManager**: encryption/decryption, classification checks, key exchange/rotation.
- **CommsNodeManager**: comms node registry, heartbeat tracking, topology generation.

## Relay Backends and Use Cases

- **Matrix**: structured room-based tactical channels on base infrastructure.
- **Meshtastic**: low-bandwidth LoRa mesh in RF-contested/infrastructure-denied sectors.
- **XMPP**: federated/distributed C2 messaging where XMPP infrastructure exists.
- **Rocket.Chat**: operations-center collaboration and formatted channel traffic.
- **P2P**: direct UDP peer transport for sparse and disconnected environments.
- **Simulated**: deterministic zero-dependency backend for tests, demos, and offline validation.

## Fallback Chain

Default priority order:

1. matrix
2. xmpp
3. rocket_chat
4. meshtastic
5. p2p
6. simulated

If a backend is unavailable, Layer 08 falls through to the next backend without requiring external connectivity.

## Message Lifecycle

1. Message creation (typed metadata, priority, classification)
2. Encryption (default enabled)
3. C2 routing decision
4. Relay delivery attempt with fallback
5. NLP summarization (Arabic/English)
6. Entity/intent/urgency extraction
7. Log-safe audit entry (body redacted)
8. Optional threat feed handoff (Layer 02 ThreatManager)

## Arabic NLP Stack

Model hierarchy:

1. AraBERT local path
2. mT5 local path
3. transformers runtime
4. ALLaM via orchestrator fallback
5. keyword/text truncation fallback

Extraction features:

- Grid references (`1234,5678`)
- Callsigns (`EAGLE-01`)
- Arabic Gulf/Saudi place names
- Threat tokens (`enemy`, `عدو`, `IED`, `كمين`)
- Time references (`0600`, `في الفجر`)
- Unit references (`1st Battalion`, `الكتيبة الأولى`)

Intent classes:

- `request_support`
- `report_contact`
- `order_movement`
- `intel_update`
- `medical_emergency`
- `order_withdrawal`

## C2 Routing Rules

- FLASH priority: attempts all backends immediately.
- ORDER → COMMAND_NET
- INTEL/SITREP → INTEL_NET
- ALERT → ALERT_NET broadcast
- Auto-escalation: `request_support` with urgency > 0.8 routes to COMMAND_NET.

## Intel Extraction and Layer 02 Integration

Comms-derived indicators are mapped into:

- `threat_indicators`
- `position_reports`
- `support_requests`

Threat indicators can be converted to ThreatManager manual events through `feed_to_threat_detection()`.

## Security Controls

- Encryption enabled by default.
- Classification validation gate in routing.
- Key registry isolated under `configs/keys/comms`.
- Key exchange and rotate operations available.
- **No plaintext body in audit logs**:
  - Use `Message.to_log_safe()`
  - Preserve summary and metadata only
  - Redact payload body and include body length marker

## Node Management

Capabilities:

- Register/update/remove comms nodes
- Heartbeat/liveness tracking
- Lost node detection by timeout
- Topology output with inferred links from shared backends

## Meshtastic in Denied Environments

Meshtastic adapter is designed to run without internet/cellular dependency and is suitable for contested deployments where only local RF mesh paths are available.

## API Endpoints

Messaging:

- `POST /comms/send`
- `POST /comms/order`
- `POST /comms/sitrep`
- `POST /comms/alert`
- `GET /comms/messages`

Channels:

- `POST /comms/channels`
- `GET /comms/channels`
- `GET /comms/channels/{channel_id}/traffic`

Nodes:

- `POST /comms/nodes`
- `GET /comms/nodes`
- `POST /comms/nodes/{node_id}/heartbeat`
- `GET /comms/nodes/topology`

Network:

- `GET /comms/status`
- `GET /comms/backends`
- `GET /comms/brief`
- `GET /comms/stats`

NLP:

- `POST /comms/nlp/summarize`
- `GET /comms/nlp/model`

## Configuration Reference

See `configs/comms.yaml` for:

- relay ordering
- backend toggles
- c2 routing policy
- nlp backend strategy
- security defaults
- channels and heartbeat behavior

## Integration with Phases 1–13

- Uses `src.security.crypto.data_encryptor.DataEncryptor` for encryption.
- Uses `src.threat_detection.threat_manager.ThreatManager` for threat ingestion.
- Uses `src.llm_core` orchestrator as optional NLP fallback.
- Added API router include in `src/api/server.py` only.

## Future Direction (Phase 15)

Layer 08 outputs (summaries, entities, urgency trends, topology health) are designed to feed future sensor-analytics fusion pipelines for predictive comms quality and operational risk forecasting.
