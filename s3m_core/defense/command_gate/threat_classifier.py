"""Threat classification for command execution safety.

Military/tactical context:
This classifier maps command behavior to known adversarial tradecraft so
S3M can deny, escalate, or monitor risky actions before execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import List, Literal

from .command_parser import CommandAST, CommandParser


RiskLevel = Literal["safe", "low", "medium", "high", "critical", "blocked"]


@dataclass(frozen=True)
class ThreatDetail:
    """A specific threat signal with confidence and provenance."""

    threat_type: str
    evidence: str
    confidence: float
    mythos_reference: str


@dataclass
class CommandThreatScore:
    """Aggregate risk scoring result for a parsed command."""

    overall_risk: RiskLevel
    threats_detected: List[ThreatDetail] = field(default_factory=list)
    requires_approval: bool = False
    recommended_action: str = "allow"


class CommandThreatClassifier:
    """Classify parsed command ASTs into tactical risk tiers."""

    _SHELL_BINARIES = {"bash", "sh", "zsh", "dash"}
    _NETWORK_TOOLS = {"curl", "wget", "nc", "nmap"}
    _SAFE_EXECS = {
        "ls",
        "cat",
        "head",
        "tail",
        "less",
        "grep",
        "cd",
        "pwd",
        "mkdir",
        "touch",
        "python",
        "python3",
        "python3.11",
        "node",
        "git",
        "echo",
        "printf",
        "wc",
        "sort",
        "uniq",
        "awk",
        "sed",
    }

    def __init__(self, parser: CommandParser | None = None) -> None:
        self.parser = parser or CommandParser()

    def classify(self, ast: CommandAST) -> CommandThreatScore:
        """Classify command AST using Mythos-aligned policy rules."""
        blocked = self._detect_blocked(ast)
        critical = self._detect_critical(ast)
        high = self._detect_high(ast)
        medium = self._detect_medium(ast)
        low = self._detect_low(ast)

        if blocked:
            threats = blocked + critical + high + medium + low
            return CommandThreatScore(
                overall_risk="blocked",
                threats_detected=threats,
                requires_approval=False,
                recommended_action="deny_immediately_and_alert_security",
            )
        if critical:
            threats = critical + high + medium + low
            return CommandThreatScore(
                overall_risk="critical",
                threats_detected=threats,
                requires_approval=True,
                recommended_action="hold_for_human_approval",
            )
        if high:
            threats = high + medium + low
            return CommandThreatScore(
                overall_risk="high",
                threats_detected=threats,
                requires_approval=False,
                recommended_action="allow_with_immediate_security_alert",
            )
        if medium:
            threats = medium + low
            return CommandThreatScore(
                overall_risk="medium",
                threats_detected=threats,
                requires_approval=False,
                recommended_action="allow_with_audit_log",
            )
        if low:
            return CommandThreatScore(
                overall_risk="low",
                threats_detected=low,
                requires_approval=False,
                recommended_action="allow_with_low_priority_monitoring",
            )
        if self._is_safe_command(ast):
            return CommandThreatScore(
                overall_risk="safe",
                threats_detected=[],
                requires_approval=False,
                recommended_action="allow",
            )
        return CommandThreatScore(
            overall_risk="low",
            threats_detected=[
                ThreatDetail(
                    threat_type="unclassified_command",
                    evidence=ast.raw,
                    confidence=0.4,
                    mythos_reference="T11 unknown execution path",
                )
            ],
            requires_approval=False,
            recommended_action="allow_with_audit_log",
        )

    def _detect_blocked(self, ast: CommandAST) -> List[ThreatDetail]:
        findings: List[ThreatDetail] = []
        for node in self._iter_nodes(ast):
            exe = node.executable.lower()
            args = node.arguments
            args_lower = [arg.lower() for arg in args]
            raw = node.raw.lower()

            if exe in {"gdb", "strace", "ltrace"} and (
                "-p" in args_lower or any(self._is_pid(arg) and int(arg) > 1 for arg in args)
            ):
                findings.append(
                    ThreatDetail("memory_inspection", node.raw, 0.95, "T06 memory inspection")
                )
            if exe == "dd" and any(
                re.match(r"if=/proc/[^/\s]+/mem", arg, flags=re.IGNORECASE) for arg in args
            ):
                findings.append(
                    ThreatDetail("proc_memory_scraping", node.raw, 0.98, "T04 /proc memory scraping")
                )
            if exe == "cat" and any(
                re.match(r"/proc/[^/\s]+/environ", arg, flags=re.IGNORECASE) for arg in args
            ):
                findings.append(
                    ThreatDetail("proc_env_reading", node.raw, 0.96, "T04 env var reading")
                )
            if exe in {"nsenter", "unshare"}:
                findings.append(
                    ThreatDetail("namespace_escape_attempt", node.raw, 0.97, "T01 namespace escape")
                )
            if exe in {"mount", "umount"}:
                findings.append(
                    ThreatDetail("filesystem_manipulation", node.raw, 0.9, "T01 filesystem manipulation")
                )
            if exe in {"xdotool", "xte", "xdg-open"}:
                findings.append(
                    ThreatDetail("keystroke_or_desktop_simulation", node.raw, 0.88, "T09 keystroke simulation")
                )
            if exe == "chmod" and any("+s" in arg for arg in args):
                findings.append(
                    ThreatDetail("setuid_escalation", node.raw, 0.97, "T07 privilege escalation")
                )
            if exe == "chown" and any(
                arg.startswith("root") or ":root" in arg for arg in args_lower
            ):
                findings.append(
                    ThreatDetail("root_ownership_escalation", node.raw, 0.95, "T07 privilege escalation")
                )

            if exe == "base64" and any(arg in {"-d", "--decode"} for arg in args_lower):
                if any(pipe.executable.lower() in self._SHELL_BINARIES for pipe in node.pipes):
                    findings.append(
                        ThreatDetail(
                            "encoded_command_execution",
                            node.raw,
                            0.99,
                            "T13 encoded command execution",
                        )
                    )
            if exe in {"curl", "wget"} and any(
                pipe.executable.lower() in self._SHELL_BINARIES for pipe in node.pipes
            ):
                findings.append(
                    ThreatDetail(
                        "remote_payload_to_shell",
                        node.raw,
                        0.99,
                        "T03 remote code execution",
                    )
                )
            if "base64 -d | bash" in raw or "base64 --decode | bash" in raw:
                findings.append(
                    ThreatDetail(
                        "encoded_command_execution",
                        node.raw,
                        0.99,
                        "T13 encoded command execution",
                    )
                )
        return findings

    def _detect_critical(self, ast: CommandAST) -> List[ThreatDetail]:
        findings: List[ThreatDetail] = []
        for node in self._iter_nodes(ast):
            exe = node.executable.lower()
            args = node.arguments
            args_lower = [arg.lower() for arg in args]

            if exe == "rm" and self._contains_recursive_force(args_lower):
                targets = [arg for arg in args if not arg.startswith("-")]
                if not targets or any(target in {"/", "/*", "~", "~/*", "."} for target in targets):
                    findings.append(
                        ThreatDetail(
                            "destructive_delete_scope",
                            node.raw,
                            0.96,
                            "T02 destructive command abuse",
                        )
                    )
            if exe == "git" and len(args_lower) >= 2:
                if args_lower[0] == "push" and any(flag in {"--force", "-f"} for flag in args_lower[1:]):
                    findings.append(
                        ThreatDetail(
                            "git_history_rewrite",
                            node.raw,
                            0.94,
                            "T10 history rewriting",
                        )
                    )
                if args_lower[0] == "reset" and "--hard" in args_lower[1:]:
                    findings.append(
                        ThreatDetail(
                            "git_history_manipulation",
                            node.raw,
                            0.93,
                            "T10 history manipulation",
                        )
                    )
            if exe == "docker" and len(args_lower) >= 2:
                if args_lower[0] == "run" and "--privileged" in args_lower[1:]:
                    findings.append(
                        ThreatDetail(
                            "privileged_container_spawn",
                            node.raw,
                            0.95,
                            "T08 elevated container",
                        )
                    )
            if exe in {"sudo", "su", "doas"}:
                findings.append(
                    ThreatDetail("privilege_escalation", node.raw, 0.95, "T07 privilege escalation")
                )
            if exe in {"kill", "killall"} and any(
                self._is_pid(arg) and 1 < int(arg) <= 200 for arg in args
            ):
                findings.append(
                    ThreatDetail("system_service_disruption", node.raw, 0.9, "T02 service disruption")
                )
            if exe in {"iptables", "nftables", "nft"}:
                findings.append(
                    ThreatDetail("network_boundary_change", node.raw, 0.9, "T01 network escape")
                )
            if exe in {"crontab", "at"} or (exe == "systemctl" and any("timer" in a for a in args_lower)):
                findings.append(
                    ThreatDetail("persistence_mechanism", node.raw, 0.88, "T11 persistence mechanism")
                )
            if exe in {"ssh", "scp"} and self._has_external_target(args):
                findings.append(
                    ThreatDetail("external_data_channel", node.raw, 0.9, "T12 data exfiltration")
                )
        return findings

    def _detect_high(self, ast: CommandAST) -> List[ThreatDetail]:
        findings: List[ThreatDetail] = []
        for node in self._iter_nodes(ast):
            exe = node.executable.lower()
            args = node.arguments
            args_lower = [arg.lower() for arg in args]
            raw = node.raw.lower()

            if exe == "find" and any(arg == "/" for arg in args) and "*.env" in raw:
                findings.append(
                    ThreatDetail("credential_hunting_env_files", node.raw, 0.87, "T05 credential hunting")
                )
            if exe == "grep" and any(flag in {"-r", "-R"} for flag in args_lower):
                if re.search(r"api_key|secret|token", raw):
                    findings.append(
                        ThreatDetail("credential_pattern_search", node.raw, 0.85, "T05 credential hunting")
                    )
            if exe == "cat" and any(arg in {"~/.ssh/id_rsa", "/root/.ssh/id_rsa"} for arg in args):
                findings.append(
                    ThreatDetail("ssh_key_reading", node.raw, 0.92, "T05 SSH key reading")
                )
            if self._reads_shadow_or_passwd(exe, args):
                findings.append(
                    ThreatDetail("credential_file_access", node.raw, 0.9, "T05 credential access")
                )
            if exe == "alias":
                findings.append(
                    ThreatDetail("shell_alias_injection", node.raw, 0.84, "T07 persistence/injection")
                )
            if any(redirect.target.endswith(path) for path in (".bashrc", ".profile") for redirect in node.redirects):
                if "alias " in raw:
                    findings.append(
                        ThreatDetail(
                            "shell_startup_persistence",
                            node.raw,
                            0.84,
                            "T07 persistence/injection",
                        )
                    )
            if (exe == "tmux" and "new-session" in args_lower) or (
                exe == "screen" and any(flag.startswith("-s") or flag == "-S" for flag in args)
            ):
                findings.append(
                    ThreatDetail("new_execution_context", node.raw, 0.82, "T08 spawning new contexts")
                )
        return findings

    def _detect_medium(self, ast: CommandAST) -> List[ThreatDetail]:
        findings: List[ThreatDetail] = []
        for node in self._iter_nodes(ast):
            exe = node.executable.lower()
            args_lower = [arg.lower() for arg in node.arguments]
            raw = node.raw.lower()

            if exe in self._NETWORK_TOOLS:
                findings.append(
                    ThreatDetail("network_tool_usage", node.raw, 0.7, "T03 network/tool activity")
                )
            if (
                exe in {"pip", "pip3", "npm", "apt", "apt-get", "yum"}
                and "install" in args_lower
            ) or (
                exe.startswith("python")
                and len(args_lower) >= 3
                and args_lower[0] == "-m"
                and args_lower[1] == "pip"
                and args_lower[2] == "install"
            ):
                findings.append(
                    ThreatDetail("package_installation", node.raw, 0.75, "T11 environment mutation")
                )
            if exe in {"gcc", "g++", "clang", "clang++", "rustc"}:
                findings.append(
                    ThreatDetail("compiler_invocation", node.raw, 0.7, "T11 tooling mutation")
                )
            if exe in {"tar", "zip"} and any(path in raw for path in ("/etc", "/var", "/usr", "/root")):
                findings.append(
                    ThreatDetail("large_system_archive", node.raw, 0.72, "T12 potential data staging")
                )
        return findings

    def _detect_low(self, ast: CommandAST) -> List[ThreatDetail]:
        if self.parser.detect_shell_in_shell(ast):
            return [
                ThreatDetail(
                    threat_type="shell_in_shell_indirection",
                    evidence=ast.raw,
                    confidence=0.65,
                    mythos_reference="T13 shell indirection staging",
                )
            ]
        return []

    def _iter_nodes(self, ast: CommandAST) -> List[CommandAST]:
        nodes: List[CommandAST] = []

        def walk(node: CommandAST) -> None:
            nodes.append(node)
            for pipe in node.pipes:
                walk(pipe)
            for subshell in node.subshells:
                walk(subshell)
            for _, chained in node.chained:
                walk(chained)

        walk(ast)
        return nodes

    def _is_safe_command(self, ast: CommandAST) -> bool:
        for node in self._iter_nodes(ast):
            exe = node.executable.lower()
            args = node.arguments
            args_lower = [arg.lower() for arg in args]
            if not exe:
                continue
            if exe not in self._SAFE_EXECS:
                return False
            if exe == "git":
                if not args_lower:
                    return False
                if args_lower[0] == "push" and any(flag in {"--force", "-f"} for flag in args_lower[1:]):
                    return False
                if args_lower[0] == "reset" and "--hard" in args_lower[1:]:
                    return False
            if exe in {"python", "python3", "python3.11", "node"}:
                path_args = [arg for arg in args if arg.endswith(".py") or arg.endswith(".js")]
                if any(arg.startswith("/") and not arg.startswith("/workspace") for arg in path_args):
                    return False
        return True

    @staticmethod
    def _contains_recursive_force(args: List[str]) -> bool:
        tokens = set(args)
        return "-rf" in tokens or "-fr" in tokens or ("-r" in tokens and "-f" in tokens)

    @staticmethod
    def _is_pid(token: str) -> bool:
        return token.isdigit()

    @staticmethod
    def _reads_shadow_or_passwd(executable: str, args: List[str]) -> bool:
        if executable not in {"cat", "head", "tail", "less", "grep", "awk", "sed"}:
            return False
        normalized = {arg.strip() for arg in args}
        return bool({"/etc/shadow", "/etc/passwd"} & normalized)

    @staticmethod
    def _has_external_target(args: List[str]) -> bool:
        local_markers = ("localhost", "127.0.0.1", "::1", ".local")
        for argument in args:
            if argument.startswith("-"):
                continue
            host = ""
            if "@" in argument:
                host = argument.split("@", 1)[1].split(":", 1)[0]
            elif ":" in argument and "/" not in argument.split(":", 1)[0]:
                host = argument.split(":", 1)[0]
            if host and not any(marker in host for marker in local_markers):
                return True
        return False
