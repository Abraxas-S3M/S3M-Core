# S3M Quad-Engine System — Phase 4 API Reference

## Overview

Phase 4 provides the REST API and Tactical CLI interface for the S3M Quad-Engine system running on NVIDIA Jetson AGX Orin 64GB.

**Base URL:** `http://localhost:8080`

---

## Endpoints

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System health check |
| GET | `/stats` | System statistics |
| GET | `/audit` | Audit log (query param: `limit`, `action`) |

### Inference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/inference` | Single engine inference |
| POST | `/consensus` | Multi-engine consensus |
| POST | `/inference/{domain}` | Domain-routed inference |

### Engine Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/engines` | List all engines |
| GET | `/engines/{name}` | Engine detail |
| POST | `/engines/{name}/load` | Load engine into memory |
| POST | `/engines/{name}/unload` | Unload engine |
| PATCH | `/engines/{name}` | Update engine config |

### Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/routing` | Get domain routing table |
| PUT | `/routing` | Update domain routing |

---

## Request/Response Examples

### POST /inference

**Request:**
```json
{
  "prompt": "Analyze the tactical situation at grid reference AB1234",
  "engine": "phi3",
  "max_tokens": 512,
  "temperature": 0.7
}
