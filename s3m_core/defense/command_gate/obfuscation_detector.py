"""Obfuscation detection for command-gate defense.

Military/tactical context:
This detector surfaces encoded or disguised payloads used to hide intent in
command streams before they reach the execution layer.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import re
import shlex
import unicodedata


@dataclass(frozen=True)
class ObfuscationReport:
    """Detection result for command obfuscation."""

    obfuscated: bool
    technique: str
    decoded_command: str
    confidence: float


class ObfuscationDetector:
    """Detect and decode obfuscated shell command payloads."""

    _SCRIPT_WRAPPERS = {"python", "python3", "python3.11", "perl", "ruby"}

    def detect(self, command: str) -> ObfuscationReport:
        """Detect command obfuscation and best-effort decode to plaintext."""
        if command is None:
            raise ValueError("command is required")
        text = command.strip()
        if not text:
            return ObfuscationReport(False, "", "", 0.0)

        candidates = [
            self._detect_base64(text),
            self._detect_hex(text),
            self._detect_octal(text),
            self._detect_variable_substitution(text),
            self._detect_string_concatenation(text),
            self._detect_rev_or_tac(text),
            self._detect_unicode_homoglyphs(text),
            self._detect_environment_abuse(text),
            self._detect_alias_abuse(text),
            self._detect_heredoc_injection(text),
            self._detect_process_substitution(text),
            self._detect_script_wrapper(text),
            self._detect_escaped_characters(text),
        ]
        matched = [candidate for candidate in candidates if candidate is not None]
        if not matched:
            return ObfuscationReport(False, "", text, 0.0)
        matched.sort(key=lambda report: report.confidence, reverse=True)
        return matched[0]

    def _detect_base64(self, text: str) -> ObfuscationReport | None:
        # Tactical note: base64 payloads are common staging for command smuggling.
        match = re.search(
            r"(?:echo|printf)\s+['\"]?([A-Za-z0-9+/=\s]{8,})['\"]?\s*\|\s*base64\s+(?:-d|--decode)",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        blob = "".join(match.group(1).split())
        try:
            decoded = base64.b64decode(blob, validate=True).decode("utf-8", errors="replace").strip()
        except (binascii.Error, ValueError):
            return None
        return ObfuscationReport(True, "base64_encoding", decoded, 0.98)

    def _detect_hex(self, text: str) -> ObfuscationReport | None:
        match = re.search(
            r"(?:echo|printf)\s+['\"]?([0-9a-fA-F]{8,})['\"]?\s*\|\s*xxd\s+-r\s+-p",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        blob = match.group(1)
        if len(blob) % 2 != 0:
            return None
        try:
            decoded = bytes.fromhex(blob).decode("utf-8", errors="replace").strip()
        except ValueError:
            return None
        return ObfuscationReport(True, "hex_encoding", decoded, 0.95)

    def _detect_octal(self, text: str) -> ObfuscationReport | None:
        if "printf" not in text.lower():
            return None
        octal_sequences = re.findall(r"\\([0-7]{3})", text)
        if not octal_sequences:
            return None
        decoded = "".join(chr(int(item, 8)) for item in octal_sequences).strip()
        if not decoded:
            return None
        return ObfuscationReport(True, "octal_encoding", decoded, 0.9)

    def _detect_variable_substitution(self, text: str) -> ObfuscationReport | None:
        assignments = dict(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)=([^\s;]+)", text))
        expansions = re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", text)
        if not assignments or not expansions:
            return None
        resolved = text
        replaced = False
        for variable in expansions:
            if variable in assignments:
                resolved = resolved.replace(f"${variable}", assignments[variable])
                replaced = True
        if not replaced or resolved == text:
            return None
        return ObfuscationReport(True, "variable_substitution", resolved.strip(), 0.72)

    def _detect_string_concatenation(self, text: str) -> ObfuscationReport | None:
        if not re.search(r"(\"[^\"]*\"\s*\"[^\"]*\"|'[^']*'\s*'[^']*')", text):
            return None
        try:
            tokens = shlex.split(text, posix=True)
        except ValueError:
            return None
        if not tokens:
            return None
        decoded = " ".join(tokens)
        return ObfuscationReport(True, "string_concatenation", decoded, 0.7)

    def _detect_rev_or_tac(self, text: str) -> ObfuscationReport | None:
        match = re.search(r"(?:echo|printf)\s+['\"]([^'\"]+)['\"]\s*\|\s*(rev|tac)\b", text)
        if not match:
            return None
        payload, mode = match.groups()
        if mode == "rev":
            decoded = payload[::-1].strip()
        else:
            decoded = " ".join(reversed(payload.split())).strip()
        return ObfuscationReport(True, "reverse_text_obfuscation", decoded, 0.86)

    def _detect_unicode_homoglyphs(self, text: str) -> ObfuscationReport | None:
        if text.isascii():
            return None
        normalized = unicodedata.normalize("NFKD", text).encode("ascii", errors="ignore").decode("ascii")
        if not normalized or normalized == text:
            return None
        return ObfuscationReport(True, "unicode_homoglyphs", normalized.strip(), 0.8)

    def _detect_environment_abuse(self, text: str) -> ObfuscationReport | None:
        if re.search(r"\bPATH\s*=\s*[^;|&]*\$\{?PATH\}?", text):
            return ObfuscationReport(True, "environment_variable_abuse", text, 0.74)
        return None

    def _detect_alias_abuse(self, text: str) -> ObfuscationReport | None:
        match = re.search(r"\balias\s+([A-Za-z0-9_]+)=['\"]([^'\"]+)['\"]", text)
        if not match:
            return None
        name, value = match.groups()
        decoded = re.sub(rf"\b{name}\b", value, text).strip()
        return ObfuscationReport(True, "alias_abuse", decoded, 0.83)

    def _detect_heredoc_injection(self, text: str) -> ObfuscationReport | None:
        if re.search(r"<<\s*([A-Za-z0-9_]+)", text) and re.search(r"\|\s*(bash|sh)\b", text):
            return ObfuscationReport(True, "heredoc_injection", text, 0.82)
        return None

    def _detect_process_substitution(self, text: str) -> ObfuscationReport | None:
        match = re.search(r"\b(?:bash|sh)\b[^\n]*<\((.+)\)", text)
        if not match:
            return None
        return ObfuscationReport(True, "process_substitution", match.group(1).strip(), 0.9)

    def _detect_script_wrapper(self, text: str) -> ObfuscationReport | None:
        try:
            tokens = shlex.split(text, posix=True)
        except ValueError:
            return None
        if len(tokens) < 3:
            return None
        executable = tokens[0].lower()
        if executable not in self._SCRIPT_WRAPPERS:
            return None
        if tokens[1] not in {"-c", "-e"}:
            return None
        script_body = " ".join(tokens[2:])
        match = re.search(r"(?:os\.system|subprocess\.(?:run|call|popen)|system)\(([^)]+)\)", script_body)
        if not match:
            return None
        decoded = match.group(1).strip("'\" ")
        return ObfuscationReport(True, "script_wrapper_shell_exec", decoded, 0.89)

    def _detect_escaped_characters(self, text: str) -> ObfuscationReport | None:
        if not re.search(r"[A-Za-z]\\[A-Za-z]", text):
            return None
        decoded = re.sub(r"\\([A-Za-z])", r"\1", text)
        if decoded == text:
            return None
        return ObfuscationReport(True, "escaped_character_obfuscation", decoded.strip(), 0.68)
