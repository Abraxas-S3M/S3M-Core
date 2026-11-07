"""Untrusted-data labeling for Cortex prompt injection resistance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


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
