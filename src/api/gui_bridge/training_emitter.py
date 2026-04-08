"""Training data emitter for GUI bridge adapter interactions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.training.data_lake import DataLake

TRAINING_DATA_DIR = Path("/mnt/s3m-weights/datasets")


def _get_data_lake() -> DataLake:
    return DataLake(base_dir=TRAINING_DATA_DIR, source="gui_bridge")


def _normalize_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {str(k): _normalize_payload(v) for k, v in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_normalize_payload(item) for item in payload]
    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload
    if hasattr(payload, "model_dump"):
        try:
            return payload.model_dump()
        except Exception:
            return str(payload)
    if hasattr(payload, "__dict__"):
        return _normalize_payload(vars(payload))
    return str(payload)


def emit_training_record(
    domain: str,
    input_context: dict,
    output_data: dict,
    language: str = "en",
) -> None:
    try:
        safe_domain = "".join(ch for ch in str(domain) if ch.isalnum() or ch in ("_", "-")).strip() or "unknown"
        _get_data_lake().write(
            safe_domain,
            json.dumps(_normalize_payload(input_context)),
            json.dumps(_normalize_payload(output_data)),
            language=str(language),
        )
    except Exception:
        # Training capture must never interrupt tactical GUI workflows.
        return
