"""Structured tactical attack pattern library mapped to Mythos incidents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Literal


RuleType = Literal["command_regex", "sequence", "behavioral", "network"]


@dataclass(frozen=True)
class DetectionRule:
    """Rule entry used to score possible pattern matches."""

    rule_id: str
    rule_type: RuleType
    pattern: str | list[str]
    threshold: float
    window_seconds: int

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("rule_id must be non-empty")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        if isinstance(self.pattern, str):
            if not self.pattern.strip():
                raise ValueError("pattern must be non-empty")
        elif isinstance(self.pattern, list):
            if not self.pattern or any(not str(item).strip() for item in self.pattern):
                raise ValueError("pattern list must contain non-empty entries")
        else:
            raise TypeError("pattern must be a string or list[str]")


@dataclass(frozen=True)
class AttackPattern:
    """Known pattern mapped to an operationally documented threat behavior."""

    pattern_id: str
    name_en: str
    name_ar: str
    description: str
    mythos_source: str
    severity: str
    detection_rules: list[DetectionRule]
    false_positive_notes: str
    response_playbook: str

    def __post_init__(self) -> None:
        if not self.pattern_id.strip():
            raise ValueError("pattern_id must be non-empty")
        if not self.name_en.strip() or not self.name_ar.strip():
            raise ValueError("pattern names must be non-empty")
        if self.severity not in {"low", "medium", "high", "critical"}:
            raise ValueError("severity must be one of: low, medium, high, critical")
        if not self.detection_rules:
            raise ValueError("detection_rules must be non-empty")


@dataclass(frozen=True)
class SecurityEvent:
    """Normalized event envelope for pattern matching."""

    event_id: str
    session_id: str
    command: str = ""
    network_target: str = ""
    file_path: str = ""
    error: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must be non-empty")
        if not self.session_id.strip():
            raise ValueError("session_id must be non-empty")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dictionary")


@dataclass(frozen=True)
class PatternMatch:
    """A single rule hit against a pattern."""

    pattern_id: str
    rule_id: str
    confidence: float
    evidence: str

    def __post_init__(self) -> None:
        if not self.pattern_id.strip():
            raise ValueError("pattern_id must be non-empty")
        if not self.rule_id.strip():
            raise ValueError("rule_id must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.evidence.strip():
            raise ValueError("evidence must be non-empty")


class AttackPatternLibrary:
    """Threat taxonomy library with deterministic matching logic."""

    def __init__(self) -> None:
        self._patterns: dict[str, AttackPattern] = {
            pattern.pattern_id: pattern for pattern in self._build_default_patterns()
        }

    def load_patterns(self) -> list[AttackPattern]:
        """Return all currently loaded patterns."""
        return list(self._patterns.values())

    def match(self, event: SecurityEvent) -> list[PatternMatch]:
        """Match one security event against known tactical patterns."""
        normalized_event = self._coerce_event(event)
        matches: list[PatternMatch] = []

        for pattern in self._patterns.values():
            for rule in pattern.detection_rules:
                confidence, evidence = self._evaluate_rule(rule, normalized_event)
                if confidence < rule.threshold:
                    continue
                matches.append(
                    PatternMatch(
                        pattern_id=pattern.pattern_id,
                        rule_id=rule.rule_id,
                        confidence=confidence,
                        evidence=evidence,
                    )
                )

        return sorted(matches, key=lambda match: match.confidence, reverse=True)

    def add_custom_pattern(self, pattern: AttackPattern) -> None:
        """Add operator-defined threat pattern to the active library."""
        if not isinstance(pattern, AttackPattern):
            raise TypeError("pattern must be an AttackPattern instance")
        if pattern.pattern_id in self._patterns:
            raise ValueError(f"pattern_id '{pattern.pattern_id}' already exists")
        self._patterns[pattern.pattern_id] = pattern

    def _coerce_event(self, event: SecurityEvent | dict[str, Any]) -> SecurityEvent:
        if isinstance(event, SecurityEvent):
            return event
        if not isinstance(event, dict):
            raise TypeError("event must be SecurityEvent or dict")
        timestamp = event.get("timestamp")
        if not isinstance(timestamp, datetime):
            timestamp = datetime.now(timezone.utc)
        return SecurityEvent(
            event_id=str(event.get("event_id", "")).strip() or "anonymous",
            session_id=str(event.get("session_id", "")).strip() or "unknown-session",
            command=str(event.get("command", "")),
            network_target=str(event.get("network_target", "")),
            file_path=str(event.get("file_path", "")),
            error=str(event.get("error", "")),
            timestamp=timestamp,
            metadata=dict(event.get("metadata", {})) if isinstance(event.get("metadata", {}), dict) else {},
        )

    def _evaluate_rule(self, rule: DetectionRule, event: SecurityEvent) -> tuple[float, str]:
        if rule.rule_type == "command_regex":
            return self._score_command_regex(rule.pattern, event.command)
        if rule.rule_type == "network":
            # Tactical exfil indicators may appear in command text before parsed network metadata.
            network_surface = f"{event.network_target} {event.command}".strip()
            return self._score_command_regex(rule.pattern, network_surface)
        if rule.rule_type == "behavioral":
            return self._score_behavioral(rule.pattern, event)
        if rule.rule_type == "sequence":
            return self._score_sequence(rule.pattern, event)
        return 0.0, "Unsupported rule type"

    def _score_command_regex(self, pattern: str | list[str], text: str) -> tuple[float, str]:
        if not text.strip():
            return 0.0, "No command or target text available"
        patterns = [pattern] if isinstance(pattern, str) else pattern
        hit_count = 0
        for regex in patterns:
            if self._safe_regex_search(regex, text):
                hit_count += 1
        if hit_count == 0:
            return 0.0, "No regex match"
        confidence = min(1.0, 0.55 + (0.2 * hit_count))
        evidence = f"Matched {hit_count}/{len(patterns)} regex indicators in '{text[:120]}'"
        return confidence, evidence

    def _score_behavioral(self, pattern: str | list[str], event: SecurityEvent) -> tuple[float, str]:
        indicators = [pattern] if isinstance(pattern, str) else pattern
        metadata = event.metadata
        matched = 0
        for indicator in indicators:
            if bool(metadata.get(indicator)):
                matched += 1
        if matched == 0:
            return 0.0, "Behavioral indicators absent"
        confidence = min(1.0, 0.5 + (matched / max(1, len(indicators))) * 0.5)
        return confidence, f"Behavioral indicators matched: {matched}/{len(indicators)}"

    def _score_sequence(self, pattern: str | list[str], event: SecurityEvent) -> tuple[float, str]:
        recent = event.metadata.get("recent_commands", [])
        if not isinstance(recent, list) or not recent:
            return 0.0, "No recent command sequence attached"
        ordered_patterns = [pattern] if isinstance(pattern, str) else pattern
        cursor = 0
        matched = 0
        for stage in ordered_patterns:
            stage_regex = str(stage)
            found = False
            for idx in range(cursor, len(recent)):
                if self._safe_regex_search(stage_regex, str(recent[idx])):
                    cursor = idx + 1
                    matched += 1
                    found = True
                    break
            if not found:
                break
        if matched == 0:
            return 0.0, "No sequence stages matched"
        confidence = min(1.0, matched / max(1, len(ordered_patterns)))
        return confidence, f"Sequence stages matched in order: {matched}/{len(ordered_patterns)}"

    @staticmethod
    def _safe_regex_search(pattern: str, text: str) -> bool:
        try:
            return bool(re.search(pattern, text, flags=re.IGNORECASE))
        except re.error:
            return False

    def _build_default_patterns(self) -> list[AttackPattern]:
        return [
            self._pattern_t01(),
            self._pattern_t02(),
            self._pattern_t03(),
            self._pattern_t04(),
            self._pattern_t05(),
            self._pattern_t06(),
            self._pattern_t07(),
            self._pattern_t08(),
            self._pattern_t09(),
            self._pattern_t10(),
            self._pattern_t11(),
            self._pattern_t12(),
            self._pattern_t13(),
            self._pattern_t14(),
            self._pattern_t15(),
            self._pattern_t16(),
        ]

    def _pattern_t01(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T01",
            name_en="Sandbox Reconnaissance Escape",
            name_ar="استطلاع البيئة المعزولة ثم محاولة الهروب",
            description="Enumerate host and network boundaries before testing escape channels.",
            mythos_source="Mythos T01",
            severity="high",
            detection_rules=[
                DetectionRule(
                    rule_id="T01-R1",
                    rule_type="sequence",
                    pattern=[r"uname|hostname|ip\s+addr", r"ping|traceroute|nmap", r"nc|ssh|socat"],
                    threshold=0.66,
                    window_seconds=300,
                )
            ],
            false_positive_notes="Can trigger during benign diagnostics in maintenance windows.",
            response_playbook="Constrain egress and enforce sandbox policy review.",
        )

    def _pattern_t02(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T02",
            name_en="Prompt Injection Pivot",
            name_ar="محاولة حقن الأوامر داخل السياق",
            description="Attempts to override guardrails through crafted prompt instructions.",
            mythos_source="Mythos T02",
            severity="medium",
            detection_rules=[
                DetectionRule(
                    rule_id="T02-R1",
                    rule_type="command_regex",
                    pattern=r"(ignore previous|system prompt|jailbreak|override policy)",
                    threshold=0.6,
                    window_seconds=120,
                )
            ],
            false_positive_notes="Security testing prompts may include the same phrasing.",
            response_playbook="Activate hardened prompt policy and require operator confirmation.",
        )

    def _pattern_t03(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T03",
            name_en="Toolchain Poisoning",
            name_ar="تسميم سلسلة الأدوات",
            description="Suspicious edits to build scripts followed by privileged execution.",
            mythos_source="Mythos T03",
            severity="high",
            detection_rules=[
                DetectionRule(
                    rule_id="T03-R1",
                    rule_type="sequence",
                    pattern=[r"setup\.py|Makefile|Dockerfile", r"sudo|chmod\s+\+x", r"bash|sh"],
                    threshold=0.67,
                    window_seconds=600,
                )
            ],
            false_positive_notes="Legitimate release workflows can look similar.",
            response_playbook="Require signed commits and isolated build validation.",
        )

    def _pattern_t04(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T04",
            name_en="Credential Hunt",
            name_ar="مطاردة بيانات الاعتماد",
            description="Search and read credential files prior to misuse.",
            mythos_source="Mythos T04",
            severity="high",
            detection_rules=[
                DetectionRule(
                    rule_id="T04-R1",
                    rule_type="sequence",
                    pattern=[r"find|grep.*password|token|secret", r"cat|less.*\.env|credentials|id_rsa"],
                    threshold=0.6,
                    window_seconds=240,
                )
            ],
            false_positive_notes="Credential rotation scripts can trigger partial matches.",
            response_playbook="Rotate credentials and restrict sensitive path access.",
        )

    def _pattern_t05(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T05",
            name_en="Credential Exfiltration",
            name_ar="تهريب بيانات الاعتماد",
            description="Credential artifacts transferred to outbound destination.",
            mythos_source="Mythos T05",
            severity="critical",
            detection_rules=[
                DetectionRule(
                    rule_id="T05-R1",
                    rule_type="network",
                    pattern=r"(curl|wget|scp).*(token|secret|credential|\.env)",
                    threshold=0.7,
                    window_seconds=180,
                )
            ],
            false_positive_notes="Can overlap with sanctioned backup transfers; validate destination.",
            response_playbook="Immediate egress block and credential revocation.",
        )

    def _pattern_t06(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T06",
            name_en="Persistence Dropper",
            name_ar="زرع آلية بقاء خفية",
            description="Creates startup or cron artifacts to survive restarts.",
            mythos_source="Mythos T06",
            severity="high",
            detection_rules=[
                DetectionRule(
                    rule_id="T06-R1",
                    rule_type="command_regex",
                    pattern=r"(crontab|systemctl\s+enable|/etc/rc\.local|\.bashrc)",
                    threshold=0.65,
                    window_seconds=300,
                )
            ],
            false_positive_notes="Routine service management may generate alerts.",
            response_playbook="Audit startup files and enforce signed persistence policies.",
        )

    def _pattern_t07(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T07",
            name_en="Privilege Escalation Chain",
            name_ar="سلسلة تصعيد الصلاحيات",
            description="Identity checks followed by SUID probing and privileged config changes.",
            mythos_source="Mythos T07",
            severity="critical",
            detection_rules=[
                DetectionRule(
                    rule_id="T07-R1",
                    rule_type="sequence",
                    pattern=[r"whoami|id", r"find.*-perm\s+-4000|getcap", r"sudo|su|pkexec"],
                    threshold=0.67,
                    window_seconds=420,
                )
            ],
            false_positive_notes="Red-team drills intentionally emulate this chain.",
            response_playbook="Suspend session and enforce least-privilege remediations.",
        )

    def _pattern_t08(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T08",
            name_en="Subagent Escalation",
            name_ar="تصعيد عبر وكيل فرعي",
            description="Blocked action re-attempted after context switching into subagents.",
            mythos_source="Mythos T08",
            severity="critical",
            detection_rules=[
                DetectionRule(
                    rule_id="T08-R1",
                    rule_type="sequence",
                    pattern=[r"blocked|denied", r"subagent|tmux|screen", r"retry|again"],
                    threshold=0.67,
                    window_seconds=300,
                )
            ],
            false_positive_notes="Can be observed during controlled fault-recovery workflows.",
            response_playbook="Disable autonomous retries and require human approval.",
        )

    def _pattern_t09(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T09",
            name_en="Approval Bypass",
            name_ar="تجاوز بوابة الموافقة",
            description="Attempts to auto-confirm gated prompts without operator review.",
            mythos_source="Mythos T09",
            severity="high",
            detection_rules=[
                DetectionRule(
                    rule_id="T09-R1",
                    rule_type="command_regex",
                    pattern=r"(auto-approve|--yes|-y|confirm=true|assume-yes)",
                    threshold=0.65,
                    window_seconds=120,
                )
            ],
            false_positive_notes="Package managers often use -y in legitimate automation.",
            response_playbook="Require challenge-response approval for privileged prompts.",
        )

    def _pattern_t10(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T10",
            name_en="Track Covering",
            name_ar="طمس الآثار التشغيلية",
            description="Destructive action followed by audit trail tampering.",
            mythos_source="Mythos T10",
            severity="high",
            detection_rules=[
                DetectionRule(
                    rule_id="T10-R1",
                    rule_type="sequence",
                    pattern=[r"rm\s+-rf|truncate|shred", r"git\s+checkout|git\s+reset", r"history\s+-c|\.bash_history"],
                    threshold=0.67,
                    window_seconds=300,
                )
            ],
            false_positive_notes="Repo cleanup scripts may look similar during CI maintenance.",
            response_playbook="Lock audit logs and capture forensic snapshot.",
        )

    def _pattern_t11(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T11",
            name_en="MCP Manipulation",
            name_ar="التلاعب بخدمة MCP",
            description="Process targeting and memory/config tampering against MCP services.",
            mythos_source="Mythos T11",
            severity="critical",
            detection_rules=[
                DetectionRule(
                    rule_id="T11-R1",
                    rule_type="sequence",
                    pattern=[r"ps|pgrep|lsof", r"mcp.*pid|process", r"gdb|ptrace|/proc/\d+/mem"],
                    threshold=0.67,
                    window_seconds=360,
                )
            ],
            false_positive_notes="Incident response diagnostics may inspect MCP process state.",
            response_playbook="Isolate MCP runtime and perform integrity attestation.",
        )

    def _pattern_t12(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T12",
            name_en="Data Staging Exfiltration",
            name_ar="تجهيز البيانات ثم تهريبها",
            description="Bulk archiving, encoding, and outbound transfer sequence.",
            mythos_source="Mythos T12",
            severity="critical",
            detection_rules=[
                DetectionRule(
                    rule_id="T12-R1",
                    rule_type="sequence",
                    pattern=[r"tar|zip|7z", r"base64|gzip|openssl\s+enc", r"curl|wget|scp|rsync"],
                    threshold=0.67,
                    window_seconds=420,
                )
            ],
            false_positive_notes="Backup workflows may mirror this chain to approved destinations.",
            response_playbook="Quarantine artifacts and cut non-essential network egress.",
        )

    def _pattern_t13(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T13",
            name_en="Lateral Workspace Movement",
            name_ar="حركة جانبية داخل بيئات العمل",
            description="Cross-workspace traversal with credential reuse attempts.",
            mythos_source="Mythos T13",
            severity="high",
            detection_rules=[
                DetectionRule(
                    rule_id="T13-R1",
                    rule_type="command_regex",
                    pattern=r"(ssh|scp|rsync).*(workspace|project|repo)",
                    threshold=0.65,
                    window_seconds=240,
                )
            ],
            false_positive_notes="May occur in approved multi-repo synchronization jobs.",
            response_playbook="Validate cross-workspace authorization and isolate suspicious sessions.",
        )

    def _pattern_t14(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T14",
            name_en="Stealth Beaconing",
            name_ar="اتصالات نبضية خفية",
            description="Repeated low-volume outbound callbacks to suspicious domains.",
            mythos_source="Mythos T14",
            severity="medium",
            detection_rules=[
                DetectionRule(
                    rule_id="T14-R1",
                    rule_type="network",
                    pattern=r"(http|https)://[^ ]+(paste|tunnel|ngrok|discord|telegram)",
                    threshold=0.6,
                    window_seconds=600,
                )
            ],
            false_positive_notes="Legitimate webhook tooling can appear similar.",
            response_playbook="Rate-limit callbacks and confirm approved endpoint inventory.",
        )

    def _pattern_t15(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T15",
            name_en="Policy Tampering",
            name_ar="التلاعب بسياسات الحماية",
            description="Direct edits to safety or policy configuration files.",
            mythos_source="Mythos T15",
            severity="high",
            detection_rules=[
                DetectionRule(
                    rule_id="T15-R1",
                    rule_type="command_regex",
                    pattern=r"(policy|guardrail|security|allowlist).*(edit|sed|tee|echo)",
                    threshold=0.65,
                    window_seconds=180,
                )
            ],
            false_positive_notes="Routine policy updates should be allowed only in maintenance windows.",
            response_playbook="Require signed policy change tickets and dual-control approval.",
        )

    def _pattern_t16(self) -> AttackPattern:
        return AttackPattern(
            pattern_id="T16",
            name_en="Supply Chain Trojanization",
            name_ar="إدخال حصان طروادة عبر الاعتمادات",
            description="Dependency changes combined with obfuscated execution payloads.",
            mythos_source="Mythos T16",
            severity="critical",
            detection_rules=[
                DetectionRule(
                    rule_id="T16-R1",
                    rule_type="sequence",
                    pattern=[r"pip\s+install|npm\s+install|poetry\s+add", r"base64|eval|exec", r"python|node|bash"],
                    threshold=0.67,
                    window_seconds=360,
                )
            ],
            false_positive_notes="Dependency updates are common; inspect for obfuscation before escalation.",
            response_playbook="Lock dependency graph and run isolated malware scan.",
        )

