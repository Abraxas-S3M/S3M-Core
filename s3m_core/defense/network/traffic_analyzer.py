"""Traffic anomaly analysis for containment escape detection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
import ipaddress
from statistics import mean, pstdev
from typing import Iterable, List
from urllib.parse import urlparse

from .dns_guard import DNSQuery
from .egress_proxy import TrafficEntry


@dataclass(slots=True)
class ThreatIndicator:
    """One suspicious behavior indicator with bilingual operator context."""

    type: str
    evidence: str
    confidence: float
    description_en: str
    description_ar: str


@dataclass(slots=True)
class ThreatAssessment:
    """Risk assessment result for one mission session."""

    risk_level: str
    indicators: List[ThreatIndicator] = field(default_factory=list)
    recommended_action: str = "continue_monitoring"


class TrafficAnalyzer:
    """Analyze traffic and DNS telemetry for containment bypass behaviors."""

    _FILE_SHARING_DOMAINS = {
        "pastebin.com",
        "ghostbin.com",
        "hastebin.com",
        "gist.github.com",
        "transfer.sh",
        "file.io",
        "dropbox.com",
    }

    def analyze_session(
        self,
        session_id: str,
        traffic_log: List[TrafficEntry],
        dns_log: List[DNSQuery],
    ) -> ThreatAssessment:
        """Analyze one session's telemetry and return risk indicators."""
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            raise ValueError("session_id must be non-empty")

        indicators: List[ThreatIndicator] = []
        session_traffic = [entry for entry in traffic_log if entry.session_id == normalized_session]
        session_dns = [entry for entry in dns_log if entry.session_id == normalized_session]

        indicators.extend(self._detect_scanning_behavior(session_traffic))
        indicators.extend(self._detect_credential_exfiltration(session_traffic))
        indicators.extend(self._detect_data_staging(session_traffic))
        indicators.extend(self._detect_c2_beaconing(session_traffic))
        indicators.extend(self._detect_dns_tunneling(session_dns))
        indicators.extend(self._detect_protocol_abuse(session_traffic))
        indicators.extend(self._detect_unexpected_destinations(session_traffic))

        risk_level = self._derive_risk_level(indicators)
        recommended_action = self._recommend_action(risk_level, indicators)
        return ThreatAssessment(
            risk_level=risk_level,
            indicators=indicators,
            recommended_action=recommended_action,
        )

    def _detect_scanning_behavior(self, traffic: List[TrafficEntry]) -> List[ThreatIndicator]:
        ports = sorted({self._extract_port(entry.url) for entry in traffic if self._extract_port(entry.url) > 0})
        hosts = [self._extract_host(entry.url) for entry in traffic if self._extract_host(entry.url)]
        unique_hosts = sorted(set(hosts))

        if len(ports) >= 8 and self._has_long_sequential_run(ports, minimum_run=6):
            return [
                ThreatIndicator(
                    type="scanning_behavior",
                    evidence=f"Sequential ports observed: {ports[:12]}",
                    confidence=0.82,
                    description_en="Likely host/port probing indicates reconnaissance before escape attempts.",
                    description_ar="سلوك الفحص المتسلسل للمنافذ يدل على استطلاع قبل محاولة تجاوز الاحتواء.",
                )
            ]

        blocked_ratio = self._blocked_ratio(traffic)
        if len(unique_hosts) >= 8 and blocked_ratio > 0.6:
            return [
                ThreatIndicator(
                    type="scanning_behavior",
                    evidence=f"Unique hosts={len(unique_hosts)}, blocked_ratio={blocked_ratio:.2f}",
                    confidence=0.74,
                    description_en="High-volume destination probing was mostly blocked and appears malicious.",
                    description_ar="تم رصد فحص واسع للوجهات ومعظم المحاولات محجوبة مما يشير إلى نشاط ضار.",
                )
            ]
        return []

    def _detect_credential_exfiltration(self, traffic: List[TrafficEntry]) -> List[ThreatIndicator]:
        flagged = [entry for entry in traffic if "credential" in entry.content_flags]
        if not flagged:
            return []
        evidence = f"{len(flagged)} outbound requests flagged with credential patterns."
        return [
            ThreatIndicator(
                type="credential_exfiltration",
                evidence=evidence,
                confidence=0.95,
                description_en="Outbound traffic matched credential signatures consistent with key leakage.",
                description_ar="حركة الخروج تطابقت مع أنماط بيانات اعتماد وتشير إلى تسريب مفاتيح محتمل.",
            )
        ]

    def _detect_data_staging(self, traffic: List[TrafficEntry]) -> List[ThreatIndicator]:
        suspicious = []
        for entry in traffic:
            host = self._extract_host(entry.url)
            if entry.request_size >= 5_000_000 and self._host_matches_set(host, self._FILE_SHARING_DOMAINS):
                suspicious.append((host, entry.request_size))
        if not suspicious:
            return []
        host, size = suspicious[0]
        return [
            ThreatIndicator(
                type="data_staging",
                evidence=f"Large upload ({size} bytes) toward file-sharing domain '{host}'.",
                confidence=0.88,
                description_en="Large transfer to file-sharing infrastructure suggests data staging for exfiltration.",
                description_ar="رفع كبير إلى خدمة مشاركة ملفات يوحي بتجهيز البيانات للتهريب الخارجي.",
            )
        ]

    def _detect_c2_beaconing(self, traffic: List[TrafficEntry]) -> List[ThreatIndicator]:
        by_host: dict[str, List[datetime]] = defaultdict(list)
        for entry in traffic:
            host = self._extract_host(entry.url)
            if not host:
                continue
            timestamp = self._parse_timestamp(entry.timestamp)
            if timestamp is None:
                continue
            by_host[host].append(timestamp)

        for host, timestamps in by_host.items():
            if len(timestamps) < 4:
                continue
            timestamps.sort()
            intervals = [
                (timestamps[idx] - timestamps[idx - 1]).total_seconds()
                for idx in range(1, len(timestamps))
            ]
            if not intervals:
                continue
            avg_interval = mean(intervals)
            jitter = pstdev(intervals) if len(intervals) > 1 else 0.0
            if 10 <= avg_interval <= 180 and jitter <= 3.0 and not self._is_expected_host(host):
                return [
                    ThreatIndicator(
                        type="c2_beaconing",
                        evidence=(
                            f"Periodic intervals to {host}: avg={avg_interval:.1f}s, jitter={jitter:.2f}s, "
                            f"events={len(timestamps)}"
                        ),
                        confidence=0.79,
                        description_en="Periodic low-jitter callbacks resemble command-and-control beaconing.",
                        description_ar="الاستدعاءات الدورية منخفضة التذبذب تشبه إشارات قيادة وتحكم.",
                    )
                ]
        return []

    def _detect_dns_tunneling(self, dns_entries: List[DNSQuery]) -> List[ThreatIndicator]:
        if not dns_entries:
            return []
        high_score = [entry for entry in dns_entries if entry.tunnel_score > 0.7]
        txt_count = sum(1 for entry in dns_entries if entry.query_type.upper() == "TXT")
        if high_score or txt_count >= 6:
            evidence = (
                f"high_score_queries={len(high_score)}, txt_queries={txt_count}, "
                f"max_score={max((entry.tunnel_score for entry in dns_entries), default=0):.2f}"
            )
            return [
                ThreatIndicator(
                    type="dns_tunneling",
                    evidence=evidence,
                    confidence=0.86 if high_score else 0.73,
                    description_en="DNS query morphology indicates possible tunnel-based data exfiltration.",
                    description_ar="خصائص استعلامات DNS تشير إلى احتمال تهريب بيانات عبر نفق DNS.",
                )
            ]
        return []

    def _detect_protocol_abuse(self, traffic: List[TrafficEntry]) -> List[ThreatIndicator]:
        suspicious = []
        for entry in traffic:
            parsed = urlparse(entry.url)
            scheme = parsed.scheme.lower()
            if scheme in {"http", "https"} and entry.request_size >= 2_000_000 and "source_code" in entry.content_flags:
                suspicious.append(entry)
        if not suspicious:
            return []
        return [
            ThreatIndicator(
                type="protocol_abuse",
                evidence=f"{len(suspicious)} large HTTP(S) payload(s) carried code-like content.",
                confidence=0.77,
                description_en="HTTP channel appears abused for non-standard tunneled payload movement.",
                description_ar="تبدو قناة HTTP مستخدمة بشكل غير اعتيادي لنقل حمولات نفقية.",
            )
        ]

    def _detect_unexpected_destinations(self, traffic: List[TrafficEntry]) -> List[ThreatIndicator]:
        unexpected_hosts = sorted(
            {
                host
                for host in (self._extract_host(entry.url) for entry in traffic)
                if host and not self._is_expected_host(host)
            }
        )
        if not unexpected_hosts:
            return []
        sample = ", ".join(unexpected_hosts[:4])
        return [
            ThreatIndicator(
                type="unexpected_destinations",
                evidence=f"Connections observed to unscoped hosts: {sample}",
                confidence=0.62,
                description_en="Traffic targeted hosts outside mission scope allowlist assumptions.",
                description_ar="تم رصد اتصالات إلى عناوين خارج نطاق المهمة المتوقع.",
            )
        ]

    @staticmethod
    def _derive_risk_level(indicators: List[ThreatIndicator]) -> str:
        if not indicators:
            return "low"
        max_confidence = max(indicator.confidence for indicator in indicators)
        indicator_types = {indicator.type for indicator in indicators}
        if max_confidence >= 0.92 or (
            "credential_exfiltration" in indicator_types and "dns_tunneling" in indicator_types
        ):
            return "critical"
        if max_confidence >= 0.8 or len(indicators) >= 4:
            return "high"
        if max_confidence >= 0.6:
            return "medium"
        return "low"

    @staticmethod
    def _recommend_action(risk_level: str, indicators: List[ThreatIndicator]) -> str:
        if risk_level == "critical":
            return (
                "Immediately isolate session network namespace, preserve packet logs, "
                "and escalate to security operations."
            )
        if risk_level == "high":
            return "Throttle outbound traffic, require human approval, and run forensic review."
        if risk_level == "medium":
            return "Increase monitoring cadence and tighten destination allowlist for this session."
        return "Continue baseline monitoring with containment controls active."

    @staticmethod
    def _extract_port(url: str) -> int:
        parsed = urlparse(url)
        if parsed.port is not None:
            return parsed.port
        if parsed.scheme == "https":
            return 443
        if parsed.scheme == "http":
            return 80
        return -1

    @staticmethod
    def _extract_host(url: str) -> str:
        return (urlparse(url).hostname or "").lower()

    @staticmethod
    def _has_long_sequential_run(values: Iterable[int], minimum_run: int) -> bool:
        sorted_values = sorted(set(values))
        if not sorted_values:
            return False
        run_length = 1
        for idx in range(1, len(sorted_values)):
            if sorted_values[idx] == sorted_values[idx - 1] + 1:
                run_length += 1
                if run_length >= minimum_run:
                    return True
            else:
                run_length = 1
        return False

    @staticmethod
    def _parse_timestamp(timestamp: str) -> datetime | None:
        try:
            return datetime.fromisoformat(timestamp)
        except ValueError:
            return None

    @staticmethod
    def _blocked_ratio(entries: List[TrafficEntry]) -> float:
        if not entries:
            return 0.0
        blocked = sum(1 for entry in entries if entry.blocked)
        return blocked / len(entries)

    @staticmethod
    def _host_matches_set(host: str, values: set[str]) -> bool:
        return any(host == value or host.endswith(f".{value}") for value in values)

    @staticmethod
    def _is_expected_host(host: str) -> bool:
        if host in {"localhost"} or host.endswith(".s3m.local"):
            return True
        try:
            ip_obj = ipaddress.ip_address(host)
        except ValueError:
            return False
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
