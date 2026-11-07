"""Taint handling for untrusted SOC telemetry before LLM consumption.

Military/tactical context: alert and log text may contain adversarial prompt
injection. Content is datamarked and spotlighted so engines treat it as data, not
operator orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Dict, Mapping, Optional


class TaintSource(str, Enum):
    """Provenance classes for data that must never be treated as instructions."""

    LOG = "log"
    ALERT = "alert"
    FILE = "file"
    TICKET = "ticket"
    WEB = "web"
    TOOL_OUTPUT = "tool_output"


_TAINT_LABEL_PREFIX = "cortex.taint"
_INSTRUCTION_MARKERS = re.compile(
    r"(?i)\b(ignore\s+previous|system\s*:\s*|you\s+must\s+now|execute\s+shell|run\s+command)\b"
)


@dataclass(frozen=True, slots=True)
class TaintedPayload:
    """Text bound to explicit taint labels before model consumption."""

    text: str
    source: TaintSource
    labels: tuple[str, ...]

    def for_model_context(self) -> str:
        """Render wrapped content that cannot be mistaken for operator orders."""
        label_path = "/".join(self.labels)
        return f"<{_TAINT_LABEL_PREFIX} source={self.source.value} labels={label_path}>{self.text}</{_TAINT_LABEL_PREFIX}>"


def wrap_untrusted(text: str, source: TaintSource) -> TaintedPayload:
    """Wrap external text with stable taint labels (fail-safe for empty input)."""
    normalized = str(text or "")
    return TaintedPayload(
        text=normalized,
        source=source,
        labels=(f"{_TAINT_LABEL_PREFIX}/{source.value}", "untrusted_data"),
    )


def contains_instruction_markers(text: str) -> bool:
    """Detect common prompt-injection phrasing inside untrusted channels."""
    return bool(_INSTRUCTION_MARKERS.search(str(text or "")))


@dataclass(frozen=True)
class QuarantineExtractResult:
    """Typed extraction output safe to pass toward engine user prompts."""

    fields: Dict[str, str]
    datamarked_block: str
    system_doctrine: str


def spotlight_datamark(
    raw_text: str,
    *,
    datamark_prefix: str,
    untrusted_begin: str,
    untrusted_end: str,
) -> str:
    """Wrap untrusted text in delimiters with a datamark prefix on every line."""
    if not raw_text:
        return f"{untrusted_begin}\n{untrusted_end}"

    marked_lines = []
    for line in raw_text.splitlines():
        marked_lines.append(f"{datamark_prefix}{line}")
    body = "\n".join(marked_lines)
    return f"{untrusted_begin}\n{body}\n{untrusted_end}"


def quarantine_extract(
    untrusted_fields: Mapping[str, str],
    *,
    datamark_prefix: str,
    untrusted_begin: str,
    untrusted_end: str,
    system_data_doctrine: str,
) -> QuarantineExtractResult:
    """
    Merge typed untrusted fields into one spotlighted block for the user prompt.

    Tactical context: field names (alert_id, raw_log, etc.) are trusted labels;
    values are never copied into the system prompt.
    """
    sections: list[str] = []
    typed: Dict[str, str] = {}
    for field_name, value in untrusted_fields.items():
        safe_name = str(field_name).strip()
        if not safe_name:
            continue
        typed[safe_name] = value
        sections.append(
            spotlight_datamark(
                value,
                datamark_prefix=datamark_prefix,
                untrusted_begin=untrusted_begin,
                untrusted_end=untrusted_end,
            )
        )

    combined = "\n\n".join(sections)
    return QuarantineExtractResult(
        fields=typed,
        datamarked_block=combined,
        system_doctrine=system_data_doctrine.strip(),
    )


def build_engine_prompts(
    *,
    system_data_doctrine: str,
    mission_system: str,
    trusted_context: str,
    datamarked_block: Optional[str] = None,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt); untrusted content stays in user only."""
    system_prompt = f"{mission_system.strip()}\n\n{system_data_doctrine.strip()}".strip()
    user_parts = [trusted_context.strip()] if trusted_context.strip() else []
    if datamarked_block:
        user_parts.append(datamarked_block)
    user_prompt = "\n\n".join(user_parts).strip()
    return system_prompt, user_prompt
