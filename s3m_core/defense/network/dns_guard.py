"""DNS containment guard with allowlist resolution and tunnel detection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import math
from typing import DefaultDict, List


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class DNSQuery:
    """One DNS query record captured for mission-session intelligence."""

    timestamp: str
    session_id: str
    query_name: str
    query_type: str
    resolved: bool
    response_ip: str
    tunnel_score: float


class DNSGuard:
    """Allowlist DNS resolver that denies unknown names with NXDOMAIN behavior."""

    def __init__(self, allowed_domains: List[str], upstream_dns: str = "1.1.1.1") -> None:
        normalized_allowed = [domain.strip().lower() for domain in allowed_domains if domain.strip()]
        if not normalized_allowed:
            raise ValueError("allowed_domains must contain at least one domain")
        self.allowed_domains = sorted(set(normalized_allowed))
        self.upstream_dns = str(upstream_dns).strip()
        if not self.upstream_dns:
            raise ValueError("upstream_dns must be non-empty")

        self._running = False
        self._listen_port = 53
        self._query_log: List[DNSQuery] = []
        self._per_session_queries: DefaultDict[str, List[tuple[datetime, str]]] = defaultdict(list)
        self._domain_frequency: DefaultDict[str, List[datetime]] = defaultdict(list)

    def start(self, listen_port: int = 53) -> None:
        """Start DNS guard control plane."""
        if not isinstance(listen_port, int) or not 1 <= listen_port <= 65535:
            raise ValueError("listen_port must be an integer in range 1..65535")
        self._listen_port = listen_port
        self._running = True

    def resolve_query(self, session_id: str, query_name: str, query_type: str = "A") -> DNSQuery:
        """
        Resolve one query using allowlist policy and return recorded result.

        Tactical context:
        Denying unauthorized DNS names blocks a major exfiltration path before
        connections can be established to unknown infrastructure.
        """
        normalized_session = str(session_id or "").strip()
        normalized_name = str(query_name or "").strip().lower().rstrip(".")
        normalized_type = str(query_type or "A").strip().upper()

        if not normalized_session:
            raise ValueError("session_id must be non-empty")
        if not normalized_name:
            raise ValueError("query_name must be non-empty")

        resolved = self._is_domain_allowed(normalized_name)
        response_ip = self._synthetic_resolve(normalized_name, normalized_type) if resolved else ""
        tunnel_score = self._score_tunneling_attempt(
            session_id=normalized_session,
            query_name=normalized_name,
            query_type=normalized_type,
        )

        query = DNSQuery(
            timestamp=_utc_now().isoformat(),
            session_id=normalized_session,
            query_name=normalized_name,
            query_type=normalized_type,
            resolved=resolved,
            response_ip=response_ip,
            tunnel_score=tunnel_score,
        )
        self._query_log.append(query)
        self._per_session_queries[normalized_session].append((_utc_now(), normalized_name))
        self._domain_frequency[self._registrable_domain(normalized_name)].append(_utc_now())
        return query

    def get_query_log(self) -> List[DNSQuery]:
        """Return all DNS query records, including blocked lookups."""
        return list(self._query_log)

    def detect_tunneling(self, session_id: str) -> bool:
        """Return True when query behavior suggests likely DNS-based exfiltration."""
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            raise ValueError("session_id must be non-empty")

        recent_cutoff = _utc_now() - timedelta(minutes=1)
        recent_queries = [
            query
            for query in self._query_log
            if query.session_id == normalized_session
            and datetime.fromisoformat(query.timestamp) >= recent_cutoff
        ]
        if not recent_queries:
            return False

        high_risk_scores = [query for query in recent_queries if query.tunnel_score > 0.7]
        txt_queries = [query for query in recent_queries if query.query_type == "TXT"]
        unresolved_ratio = sum(1 for query in recent_queries if not query.resolved) / len(recent_queries)

        return bool(
            high_risk_scores
            or len(txt_queries) >= 6
            or unresolved_ratio > 0.6
            or self._single_domain_burst(recent_queries) >= 20
        )

    def _score_tunneling_attempt(self, *, session_id: str, query_name: str, query_type: str) -> float:
        labels = query_name.split(".")
        first_label = labels[0] if labels else query_name
        score = 0.0

        if len(first_label) >= 45:
            score += 0.35
        if self._entropy(first_label) >= 3.5:
            score += 0.3
        if query_type == "TXT":
            score += 0.2

        root_domain = self._registrable_domain(query_name)
        now = _utc_now()
        cutoff = now - timedelta(minutes=1)
        domain_hits = [timestamp for timestamp in self._domain_frequency[root_domain] if timestamp >= cutoff]
        if len(domain_hits) >= 20:
            score += 0.25

        session_cutoff = now - timedelta(minutes=1)
        session_hits = [
            item
            for item in self._per_session_queries[session_id]
            if item[0] >= session_cutoff and item[1].endswith(root_domain)
        ]
        if len(session_hits) >= 25:
            score += 0.2

        return min(1.0, round(score, 3))

    def _is_domain_allowed(self, query_name: str) -> bool:
        return any(
            query_name == allowed or query_name.endswith(f".{allowed}") for allowed in self.allowed_domains
        )

    @staticmethod
    def _registrable_domain(query_name: str) -> str:
        labels = query_name.split(".")
        if len(labels) < 2:
            return query_name
        return ".".join(labels[-2:])

    @staticmethod
    def _synthetic_resolve(query_name: str, query_type: str) -> str:
        """
        Return deterministic synthetic IP for offline test environments.

        Tactical context:
        A synthetic resolver prevents accidental external dependency while still
        allowing mission software to test resolution-dependent control flows.
        """
        digest = hashlib.sha256(f"{query_name}:{query_type}".encode("utf-8")).digest()
        if query_type == "AAAA":
            parts = [f"{digest[idx]:02x}{digest[idx + 1]:02x}" for idx in range(0, 16, 2)]
            return ":".join(parts)
        return f"198.18.{digest[0]}.{digest[1]}"

    @staticmethod
    def _entropy(text: str) -> float:
        if not text:
            return 0.0
        counts = {}
        for char in text:
            counts[char] = counts.get(char, 0) + 1
        length = len(text)
        entropy = 0.0
        for count in counts.values():
            probability = count / length
            entropy -= probability * math.log2(probability)
        return entropy

    @staticmethod
    def _single_domain_burst(recent_queries: List[DNSQuery]) -> int:
        frequencies: dict[str, int] = {}
        for query in recent_queries:
            root = DNSGuard._registrable_domain(query.query_name)
            frequencies[root] = frequencies.get(root, 0) + 1
        return max(frequencies.values(), default=0)
