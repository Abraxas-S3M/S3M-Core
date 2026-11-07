"""Structured planning output parsing and schema validation for Le Chonk."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

from src.quad_engine.models import CoaOption


class PlanningCoaPayload(BaseModel):
    """Expected JSON envelope for COA planning responses."""

    coa_options: List[CoaOption] = Field(default_factory=list)
    watch_priorities: List[str] = Field(default_factory=list)
    sensor_cueing: List[str] = Field(default_factory=list)
    commander_tasks: List[str] = Field(default_factory=list)


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _extract_json_blob(text: str) -> Optional[str]:
    stripped = (text or "").strip()
    if not stripped:
        return None
    fence = _JSON_FENCE.search(stripped)
    if fence:
        return fence.group(1).strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return None


def validate_planning_payload(raw_text: str) -> Tuple[Optional[PlanningCoaPayload], List[str]]:
    """Parse and validate structured planning JSON; fail closed on schema errors."""
    blob = _extract_json_blob(raw_text)
    if blob is None:
        return None, ["structured_json_missing"]
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None, ["structured_json_invalid"]
    if not isinstance(data, dict):
        return None, ["structured_json_not_object"]
    try:
        payload = PlanningCoaPayload.model_validate(data)
    except ValidationError as exc:
        return None, [f"structured_schema:{err['type']}" for err in exc.errors()[:5]]
    return payload, []


def coa_options_from_text(raw_text: str, *, live: bool) -> Tuple[Any, List[str]]:
    """
    Prefer schema-valid COA list; otherwise wrap plain text as a single labeled option.
    """
    payload, errors = validate_planning_payload(raw_text)
    if payload is not None and payload.coa_options:
        return [opt.model_dump() for opt in payload.coa_options], errors

    label = "Le Chonk planning COA" if live else "Planning text"
    option_id = "coa-lechonk-1" if live else "coa-text-1"
    return (
        [
            CoaOption(
                option_id=option_id,
                name=label,
                description=(raw_text or "").strip(),
                risk="medium",
                confidence=0.6 if live else 0.5,
            ).model_dump()
        ],
        errors,
    )


def planning_list_field(raw_text: str, field_name: str) -> Tuple[List[str], List[str]]:
    payload, errors = validate_planning_payload(raw_text)
    if payload is None:
        return [], errors
    value = getattr(payload, field_name, None)
    if isinstance(value, list) and all(isinstance(x, str) for x in value):
        return list(value), errors
    return [], errors + [f"structured_field_missing:{field_name}"]
