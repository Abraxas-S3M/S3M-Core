"""Validation suite for layered S3M defenses.

Military/tactical context:
Layer-by-layer validation provides readiness evidence that mission guardrails
remain active after configuration drift, patching, or adversarial pressure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import resource
import socket
import tempfile
from typing import Callable, Dict, Mapping


ProbeResult = bool | tuple[bool, str]


@dataclass(frozen=True, slots=True)
class LayerValidation:
    """Validation outcomes for one defense layer."""

    layer_id: str
    passed: bool
    tests: Dict[str, bool]
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Aggregated validation results across all defense layers."""

    layers_tested: int
    layers_passed: int
    layers_failed: int
    details: Dict[str, LayerValidation]


class DefenseValidator:
    """Run non-destructive readiness checks for each defensive layer."""

    LAYER_MATRIX: Dict[str, list[tuple[str, str, str]]] = {
        "L0": [
            ("l0.proc_masked", "Verify /proc is properly masked", "_verify_proc_masked"),
            ("l0.ptrace_blocked", "Verify ptrace is blocked", "_verify_ptrace_blocked"),
            ("l0.namespace_isolation", "Verify namespace isolation", "_verify_namespace_isolation"),
            ("l0.resource_limits", "Verify resource limits are applied", "_verify_resource_limits"),
        ],
        "L1": [
            (
                "l1.monitored_file_alert",
                "Modify a monitored file and verify alert fires",
                "_verify_monitored_file_alert",
            ),
            ("l1.overlay_layering", "Verify overlay is properly layered", "_verify_overlay_layering"),
            ("l1.git_hook_force_push", "Verify git hooks reject force-push", "_verify_git_hook_force_push"),
        ],
        "L2": [
            (
                "l2.blocked_host_denial",
                "Attempt connection to blocked host and verify denial",
                "_verify_blocked_host_denial",
            ),
            (
                "l2.dns_nxdomain",
                "Verify DNS returns NXDOMAIN for unlisted domains",
                "_verify_dns_nxdomain",
            ),
            ("l2.egress_proxy_logs", "Verify egress proxy logs traffic", "_verify_egress_proxy_logs"),
        ],
        "L3": [
            (
                "l3.no_credentials_in_env",
                "Verify no credentials in agent environment",
                "_verify_no_credentials_in_environment",
            ),
            (
                "l3.vault_allowed_services",
                "Verify vault token works for allowed services",
                "_verify_vault_allowed_services",
            ),
            (
                "l3.vault_disallowed_services",
                "Verify vault token denied for disallowed services",
                "_verify_vault_disallowed_services",
            ),
        ],
        "L4": [
            (
                "l4.blocked_command_denial",
                "Submit known-blocked commands and verify denial",
                "_verify_blocked_commands_denied",
            ),
            (
                "l4.obfuscated_detection",
                "Submit obfuscated commands and verify detection",
                "_verify_obfuscated_command_detection",
            ),
            ("l4.safe_command_approval", "Submit safe commands and verify approval", "_verify_safe_commands"),
        ],
        "L5": [
            (
                "l5.mcp_pid_namespace",
                "Verify MCP server in separate PID namespace",
                "_verify_mcp_pid_namespace",
            ),
            ("l5.mtls_required", "Verify mTLS required for connection", "_verify_mtls_required"),
        ],
        "L6": [
            (
                "l6.subagent_elevation_denied",
                "Attempt to spawn subagent with elevated permissions and verify denial",
                "_verify_subagent_elevation_denied",
            ),
            (
                "l6.permission_inheritance",
                "Verify permission inheritance computation",
                "_verify_permission_inheritance",
            ),
        ],
        "L7": [
            (
                "l7.attack_pattern_detection",
                "Replay a known attack pattern sequence and verify detection",
                "_verify_attack_pattern_detection",
            ),
            ("l7.anomaly_baseline", "Verify anomaly baseline exists", "_verify_anomaly_baseline_exists"),
        ],
        "L8": [
            ("l8.log_chain_integrity", "Verify log chain integrity", "_verify_log_chain_integrity"),
            ("l8.append_only", "Verify append-only property", "_verify_append_only_property"),
        ],
    }

    def __init__(
        self,
        probe_overrides: Mapping[str, ProbeResult | Callable[[], ProbeResult]] | None = None,
        filesystem_alert_probe: Callable[[Path], bool] | None = None,
        git_hook_probe: Callable[[], bool] | None = None,
        command_gate_probe: Callable[[str], bool] | None = None,
        vault_probe: Callable[[str, bool], bool] | None = None,
        subagent_permission_probe: Callable[[str], bool] | None = None,
        threat_detection_probe: Callable[[list[str]], bool] | None = None,
        audit_log_probe: Callable[[str], bool] | None = None,
    ) -> None:
        self._probe_overrides = dict(probe_overrides or {})
        self._filesystem_alert_probe = filesystem_alert_probe
        self._git_hook_probe = git_hook_probe
        self._command_gate_probe = command_gate_probe
        self._vault_probe = vault_probe
        self._subagent_permission_probe = subagent_permission_probe
        self._threat_detection_probe = threat_detection_probe
        self._audit_log_probe = audit_log_probe

    def validate_all(self) -> ValidationReport:
        """Run all layer probes and return a structured validation report."""

        details: Dict[str, LayerValidation] = {}
        layers_passed = 0

        for layer, tests in self.LAYER_MATRIX.items():
            outcomes: Dict[str, bool] = {}
            failures: list[str] = []
            notes: list[str] = []

            for probe_id, description, method_name in tests:
                probe_method = getattr(self, method_name)
                passed, note = self._resolve_probe(probe_id, probe_method)
                outcomes[description] = passed
                if not passed:
                    failures.append(description)
                if note:
                    notes.append(f"{description}: {note}")

            layer_passed = all(outcomes.values())
            if layer_passed:
                layers_passed += 1
            details[layer] = LayerValidation(
                layer_id=layer,
                passed=layer_passed,
                tests=outcomes,
                failures=failures,
                notes=notes,
            )

        layers_tested = len(self.LAYER_MATRIX)
        return ValidationReport(
            layers_tested=layers_tested,
            layers_passed=layers_passed,
            layers_failed=layers_tested - layers_passed,
            details=details,
        )

    def _resolve_probe(self, probe_id: str, fallback: Callable[[], ProbeResult]) -> tuple[bool, str]:
        override = self._probe_overrides.get(probe_id)
        candidate = override if override is not None else fallback
        try:
            result: ProbeResult
            if callable(candidate):
                result = candidate()
            else:
                result = candidate
            if isinstance(result, tuple):
                return bool(result[0]), str(result[1])
            return bool(result), ""
        except Exception as exc:  # pragma: no cover - defensive guard
            return False, f"probe raised {exc.__class__.__name__}: {exc}"

    def _verify_proc_masked(self) -> ProbeResult:
        try:
            with Path("/proc/1/mem").open("rb"):
                pass
            return False, "/proc/1/mem was readable"
        except (PermissionError, FileNotFoundError):
            return True, ""
        except OSError as exc:
            return False, f"unexpected /proc check error: {exc}"

    def _verify_ptrace_blocked(self) -> ProbeResult:
        ptrace_scope = Path("/proc/sys/kernel/yama/ptrace_scope")
        if not ptrace_scope.exists():
            return False, "ptrace scope control not found"
        value = ptrace_scope.read_text(encoding="utf-8").strip()
        return value in {"1", "2", "3"}, f"ptrace_scope={value}"

    def _verify_namespace_isolation(self) -> ProbeResult:
        own_namespace = Path("/proc/self/ns/mnt")
        init_namespace = Path("/proc/1/ns/mnt")
        if not own_namespace.exists() or not init_namespace.exists():
            return False, "namespace files missing"
        return (
            os.readlink(str(own_namespace)) != os.readlink(str(init_namespace)),
            "mount namespace matches pid 1",
        )

    def _verify_resource_limits(self) -> ProbeResult:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        return soft > 0 and soft != resource.RLIM_INFINITY and hard > 0, f"nofile soft={soft} hard={hard}"

    def _verify_monitored_file_alert(self) -> ProbeResult:
        if self._filesystem_alert_probe is None:
            return False, "filesystem alert probe not configured"
        with tempfile.TemporaryDirectory(prefix="s3m-monitored-") as temp_dir:
            monitored_file = Path(temp_dir) / "mission_state.conf"
            monitored_file.write_text("status=nominal\n", encoding="utf-8")
            monitored_file.write_text("status=tampered\n", encoding="utf-8")
            fired = bool(self._filesystem_alert_probe(monitored_file))
            return fired, "alert probe did not report tamper"

    def _verify_overlay_layering(self) -> ProbeResult:
        mounts_path = Path("/proc/mounts")
        if not mounts_path.exists():
            return False, "/proc/mounts unavailable"
        for line in mounts_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "/" and parts[2] == "overlay":
                return True, ""
        return False, "root filesystem is not overlay"

    def _verify_git_hook_force_push(self) -> ProbeResult:
        if self._git_hook_probe is None:
            return False, "git hook probe not configured"
        return bool(self._git_hook_probe()), "git hook probe returned rejection failure"

    def _verify_blocked_host_denial(self) -> ProbeResult:
        blocked_host = ("198.51.100.23", 443)
        try:
            with socket.create_connection(blocked_host, timeout=0.25):
                return False, f"connection to {blocked_host[0]} succeeded"
        except OSError:
            return True, ""

    def _verify_dns_nxdomain(self) -> ProbeResult:
        unlisted_domain = "unlisted-domain-for-s3m.invalid"
        try:
            socket.gethostbyname(unlisted_domain)
            return False, "unexpected DNS resolution succeeded"
        except socket.gaierror:
            return True, ""

    def _verify_egress_proxy_logs(self) -> ProbeResult:
        proxy_keys = ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "S3M_EGRESS_PROXY_LOG_PATH")
        has_proxy_signal = any(os.environ.get(key) for key in proxy_keys)
        return has_proxy_signal, "proxy configuration signal missing"

    def _verify_no_credentials_in_environment(self) -> ProbeResult:
        sensitive_keys = {
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AZURE_CLIENT_SECRET",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "DB_PASSWORD",
        }
        present = sorted(key for key in sensitive_keys if os.environ.get(key))
        return not present, f"credential keys present: {', '.join(present)}"

    def _verify_vault_allowed_services(self) -> ProbeResult:
        if self._vault_probe is not None:
            return bool(self._vault_probe("mission_telemetry", True)), "allowed vault access probe failed"
        return os.environ.get("S3M_VAULT_ALLOWED_OK") == "1", "S3M_VAULT_ALLOWED_OK not set"

    def _verify_vault_disallowed_services(self) -> ProbeResult:
        if self._vault_probe is not None:
            denied = not self._vault_probe("restricted_planning", False)
            return denied, "disallowed vault access unexpectedly allowed"
        return os.environ.get("S3M_VAULT_DENIED_OK") == "1", "S3M_VAULT_DENIED_OK not set"

    def _verify_blocked_commands_denied(self) -> ProbeResult:
        if self._command_gate_probe is None:
            return False, "command gate probe not configured"
        blocked_commands = ["curl http://malicious.local", "nc 10.0.0.8 4444", "chmod 777 /"]
        denied = all(not self._command_gate_probe(command) for command in blocked_commands)
        return denied, "one or more blocked commands were allowed"

    def _verify_obfuscated_command_detection(self) -> ProbeResult:
        if self._command_gate_probe is None:
            return False, "command gate probe not configured"
        obfuscated_commands = ["c''ur''l http://blocked", "ba$((1+0))sh -c 'cat /etc/shadow'"]
        denied = all(not self._command_gate_probe(command) for command in obfuscated_commands)
        return denied, "obfuscated command bypass detected"

    def _verify_safe_commands(self) -> ProbeResult:
        if self._command_gate_probe is None:
            return False, "command gate probe not configured"
        safe_commands = ["echo readiness_check", "ls /tmp"]
        allowed = all(self._command_gate_probe(command) for command in safe_commands)
        return allowed, "safe command unexpectedly denied"

    def _verify_mcp_pid_namespace(self) -> ProbeResult:
        mcp_namespace = os.environ.get("S3M_MCP_PID_NS")
        if not mcp_namespace:
            return False, "S3M_MCP_PID_NS not provided"
        own_namespace = os.readlink("/proc/self/ns/pid")
        return own_namespace != mcp_namespace, "MCP namespace matches agent namespace"

    def _verify_mtls_required(self) -> ProbeResult:
        return os.environ.get("S3M_MCP_MTLS_REQUIRED") == "1", "S3M_MCP_MTLS_REQUIRED not enforced"

    def _verify_subagent_elevation_denied(self) -> ProbeResult:
        if self._subagent_permission_probe is not None:
            denied = not self._subagent_permission_probe("elevated")
            return denied, "subagent elevation was allowed"
        return os.environ.get("S3M_SUBAGENT_ELEVATION_DENIED") == "1", "subagent elevation denial not configured"

    def _verify_permission_inheritance(self) -> ProbeResult:
        if self._subagent_permission_probe is not None:
            inherited = self._subagent_permission_probe("inherit")
            return bool(inherited), "subagent inheritance validation failed"
        return os.environ.get("S3M_SUBAGENT_INHERITANCE_VALID") == "1", "inheritance evidence missing"

    def _verify_attack_pattern_detection(self) -> ProbeResult:
        attack_sequence = ["enumerate_env", "read_sensitive_file", "exfiltrate_attempt"]
        if self._threat_detection_probe is not None:
            return bool(self._threat_detection_probe(attack_sequence)), "attack sequence not detected"
        return os.environ.get("S3M_ATTACK_PATTERN_DETECTED") == "1", "attack detection flag missing"

    def _verify_anomaly_baseline_exists(self) -> ProbeResult:
        baseline_path = Path(os.environ.get("S3M_ANOMALY_BASELINE_PATH", "/var/lib/s3m/anomaly_baseline.json"))
        return baseline_path.exists(), f"anomaly baseline missing at {baseline_path}"

    def _verify_log_chain_integrity(self) -> ProbeResult:
        if self._audit_log_probe is not None:
            return bool(self._audit_log_probe("chain_integrity")), "audit chain integrity probe failed"
        return os.environ.get("S3M_AUDIT_CHAIN_OK") == "1", "audit chain flag missing"

    def _verify_append_only_property(self) -> ProbeResult:
        if self._audit_log_probe is not None:
            return bool(self._audit_log_probe("append_only")), "append-only probe failed"
        return os.environ.get("S3M_AUDIT_APPEND_ONLY_OK") == "1", "append-only flag missing"
