"""Taint handling for untrusted SOC telemetry before LLM and automation consumption."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Dict, Generic, Mapping, Optional, Set, TypeVar, Union

T = TypeVar("T")

_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)
_IPV6_RE = re.compile(r"^[0-9a-fA-F:]+$")
_PORT_RE = re.compile(r"^[1-9]\d{0,4}$")
_MD5_RE = re.compile(r"^[a-fA-F0-9]{32}$")
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
)

_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?prior\s+(?:rules|instructions)", re.IGNORECASE),
    re.compile(r"expire\s+route[-\w]*", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
)

_TAINT_LABEL_PREFIX = "cortex.taint"
_INSTRUCTION_MARKERS = re.compile(
    r"(?i)\b(ignore\s+previous|system\s*:\s*|you\s+must\s+now|execute\s+shell|run\s+command)\b"
)


class TaintSource(str, Enum):
    """Provenance classes for data that must never be treated as instructions."""

    LOG = "log"
    ALERT = "alert"
    FILE = "file"
    TICKET = "ticket"
    WEB = "web"
    TOOL_OUTPUT = "tool_output"


@dataclass(frozen=True, slots=True)
class TaintedPayload:
    """Text bound to explicit taint labels before model consumption."""

    text: str
    source: TaintSource
    labels: tuple[str, ...]

    def for_model_context(self) -> str:
        """Render wrapped content that cannot be mistaken for operator orders."""
        label_path = "/".join(self.labels)
        return (
            f"<{_TAINT_LABEL_PREFIX} source={self.source.value} labels={label_path}>"
            f"{self.text}</{_TAINT_LABEL_PREFIX}>"
        )


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

    marked_lines = [f"{datamark_prefix}{line}" for line in raw_text.splitlines()]
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
    """Merge typed untrusted fields into one spotlighted block for the user prompt."""
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


class Trust(str, Enum):
    """How much automation may rely on a value when proposing write actions."""

    OBSERVED = "OBSERVED"
    UNTRUSTED = "UNTRUSTED"
    VERIFIED = "VERIFIED"


@dataclass(frozen=True)
class Labeled(Generic[T]):
    """A value tagged with trust and kept tied to its originating field."""

    value: Optional[T]
    trust: Trust
    source: str
    raw: Optional[str] = None

    def is_usable(self) -> bool:
        return self.value is not None


def quarantine_extract_typed(
    raw: object,
    kind: str,
    *,
    source: str,
    trust: Trust = Trust.UNTRUSTED,
) -> Labeled[Any]:
    """Coerce raw sensor text into a typed value; never widen trust on failure."""
    text = "" if raw is None else str(raw).strip()
    if not text:
        return Labeled(value=None, trust=trust, source=source, raw=text or None)

    normalized_kind = kind.lower().strip()
    if normalized_kind == "ip":
        if _IPV4_RE.match(text) or (_IPV6_RE.match(text) and ":" in text):
            return Labeled(value=text, trust=trust, source=source, raw=text)
        return Labeled(value=None, trust=Trust.UNTRUSTED, source=source, raw=text)
    if normalized_kind == "port":
        if _PORT_RE.match(text):
            port = int(text)
            if 1 <= port <= 65535:
                return Labeled(value=port, trust=trust, source=source, raw=text)
        return Labeled(value=None, trust=Trust.UNTRUSTED, source=source, raw=text)
    if normalized_kind in {"md5", "hash_md5"}:
        if _MD5_RE.match(text):
            return Labeled(value=text.lower(), trust=trust, source=source, raw=text)
        return Labeled(value=None, trust=Trust.UNTRUSTED, source=source, raw=text)
    if normalized_kind in {"sha256", "hash_sha256"}:
        if _SHA256_RE.match(text):
            return Labeled(value=text.lower(), trust=trust, source=source, raw=text)
        return Labeled(value=None, trust=Trust.UNTRUSTED, source=source, raw=text)
    if normalized_kind == "cve":
        candidate = text.upper()
        if _CVE_RE.match(candidate):
            return Labeled(value=candidate, trust=trust, source=source, raw=text)
        return Labeled(value=None, trust=Trust.UNTRUSTED, source=source, raw=text)
    if normalized_kind in {"hostname", "domain"}:
        if _HOSTNAME_RE.match(text):
            return Labeled(value=text.lower(), trust=trust, source=source, raw=text)
        return Labeled(value=None, trust=Trust.UNTRUSTED, source=source, raw=text)
    return Labeled(value=None, trust=Trust.UNTRUSTED, source=source, raw=text)


def injection_signal(text: object) -> bool:
    """Detect likely prompt-injection phrasing in free-text evidence."""
    if text is None:
        return False
    blob = str(text)
    if not blob.strip():
        return False
    if contains_instruction_markers(blob):
        return True
    return any(pattern.search(blob) for pattern in _INJECTION_PATTERNS)


def endorse(labeled: Labeled[T], *, verified: bool) -> Labeled[T]:
    """Upgrade trust to VERIFIED only when inventory confirms the typed value."""
    if not verified or labeled.value is None:
        return labeled
    if labeled.trust == Trust.UNTRUSTED:
        return labeled
    return replace(labeled, trust=Trust.VERIFIED)


class AssetInventory(Mapping[str, Set[str]]):
    """Minimal authoritative inventory slice for endorsement checks."""

    def __init__(self, **buckets: Set[str] | list[str]) -> None:
        self._buckets: Dict[str, Set[str]] = {}
        for key, values in buckets.items():
            if isinstance(values, set):
                self._buckets[key] = set(values)
            else:
                self._buckets[key] = {str(v).strip() for v in values if str(v).strip()}

    def __getitem__(self, key: str) -> Set[str]:
        return self._buckets.get(key, set())

    def __iter__(self):
        return iter(self._buckets)

    def __len__(self) -> int:
        return len(self._buckets)

    def contains(self, bucket: str, value: object) -> bool:
        if value is None:
            return False
        bucket_set = self._buckets.get(bucket, set())
        if value in bucket_set:
            return True
        return str(value) in bucket_set


def endorse_against_inventory(event: Any, inventory: Union[AssetInventory, Mapping[str, Set[str]]]) -> Any:
    """Re-label typed ThreatEvent fields that match authoritative inventory."""
    from src.cortex.threat_event import endorse_threat_event_inventory

    inv = inventory if isinstance(inventory, AssetInventory) else AssetInventory(**dict(inventory))
    return endorse_threat_event_inventory(event, inv)
