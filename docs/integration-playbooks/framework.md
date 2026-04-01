# S3M Integration Framework Playbook

## Purpose

This playbook defines the reusable API integration framework used by all
external provider adapters in S3M-Core. The framework is built for
sovereign operations on NVIDIA Jetson AGX Orin and supports both connected
pre-deployment ingestion and fully air-gapped field deployment.

## Dual-Mode Architecture

### Online Mode

- Provider adapters may call approved external APIs.
- Data is fetched, normalized, and stored under local integration storage.
- Retries, rate limits, circuit breaking, and audit telemetry are enforced.

### Air-Gapped Mode

- No outbound network calls are allowed.
- Adapters read from local stores and caches only.
- `ResilientHTTPClient` raises `AirgapViolationError` if used in air-gapped mode.
- `AirGapVerifier` in `src/security/airgap_verifier.py` remains the runtime control.

## Adapter Lifecycle

1. Register adapter class in `ProviderRegistry`.
2. `get_manifest()` declares category, auth, schemas, limits.
3. `validate_credentials()` verifies secure secret availability.
4. `fetch()` retrieves source payloads (API or local cache depending on mode).
5. `normalize()` maps payloads to normalized schema dataclasses.
6. Store records using `LocalStorage`.
7. Optional enrichment, dedup, and entity resolution pipelines run.
8. Health status is reported via `health_check()` and registry aggregation.

## Authentication Strategy Guide

- `APIKeyAuth`: API key headers, bearer token, or query param APIs.
- `OAuth2Auth`: client credentials flow with local token caching.
- `CertificateAuth`: mTLS style credential path wiring.
- `NoAuth`: public endpoints with no authentication.
- `SecretProvider`: env/file secret resolution; secrets are never hard-coded.

## Rate Limiting and Circuit Breaking

- Token-bucket `RateLimiter(rpm)` enforces provider-level request quotas.
- `CircuitBreaker` opens after 5 consecutive failures by default.
- Open state blocks calls until recovery timeout (default 60 seconds).
- Half-open mode permits limited trial request for recovery validation.

## Normalized Schema Catalog

1. Geospatial (`NormalizedGeoObservation`)
2. Threat Intel (`NormalizedThreatIndicator`)
3. Event Intel (`NormalizedGlobalEvent`)
4. Maritime (`NormalizedVesselTrack`)
5. Flight (`NormalizedFlightTrack`)
6. Weather (`NormalizedWeatherObservation`)
7. Terrain (`NormalizedMapLayer`)
8. Identity (`ProviderAccount`, `CredentialRef`, `ConnectorHealthStatus`)

## Adding a New Provider

1. Copy `packages/providers/_mock_provider` as baseline.
2. Update manifest metadata and schema outputs.
3. Implement auth strategy using `SecretProvider` keys.
4. Implement dual-mode `fetch()` logic (online API + air-gap local read).
5. Implement normalizer mapping to one or more normalized schemas.
6. Add provider tests (credentials, fetch, normalize, health, registry).
7. Add provider config block in `configs/integrations/providers.yaml`.
8. Add runbook under `docs/provider-runbooks/`.

## Pipeline Architecture

- **Batch ingestion**: provider fetch-and-normalize persistence runs.
- **Stream listeners**: websocket/SSE base abstraction for future providers.
- **Enrichment chain**: deterministic post-processing transforms.
- **Deduplication**: content-hash based duplicate suppression.
- **Entity resolution**: cross-provider grouping by key attributes.

## Air-Gapped Deployment Workflow

1. Online staging node runs scheduled ingestion.
2. Raw and normalized datasets are exported to encrypted media.
3. Secure USB transfer moves data into air-gapped Jetson environment.
4. Air-gapped adapters read only from local integration storage.
5. AirGapVerifier continuously validates isolation posture.

## Testing Strategy

- Unit tests for auth, HTTP resilience, registry, and provider contracts.
- Fixture-driven normalization tests for deterministic mapping behavior.
- Contract tests for schema fields and required invariants.
- Integration tests for register -> validate -> fetch -> normalize flow.
