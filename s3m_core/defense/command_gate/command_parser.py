"""Command parser for the S3M tactical execution gate.

Military/tactical context:
This parser transforms raw shell text into a structured graph so the
defensive gate can inspect intent across chained and obfuscated command paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import shlex
from typing import Dict, List, Literal, Tuple


RedirectMode = Literal["write", "append", "read"]


@dataclass(frozen=True)
class Redirect:
    """I/O redirect metadata for a parsed shell command."""

    fd: int
    target: str
    mode: RedirectMode


@dataclass
class CommandAST:
    """Normalized command AST for gate analysis."""

    raw: str
    executable: str
    arguments: List[str] = field(default_factory=list)
    pipes: List["CommandAST"] = field(default_factory=list)
    redirects: List[Redirect] = field(default_factory=list)
    background: bool = False
    subshells: List["CommandAST"] = field(default_factory=list)
    environment_vars: Dict[str, str] = field(default_factory=dict)
    chained: List[Tuple[str, "CommandAST"]] = field(default_factory=list)


class CommandParser:
    """Parse shell commands into a graph for threat inspection."""

    _ENV_ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=(.*)$")
    _SHELL_EXECUTABLES = {
        "bash",
        "sh",
        "zsh",
        "dash",
        "ksh",
        "fish",
    }
    _SCRIPT_WRAPPERS = {
        "python",
        "python3",
        "python3.11",
        "perl",
        "ruby",
        "node",
    }
    _REDIRECT_TOKENS = {
        ">": (1, "write"),
        ">>": (1, "append"),
        "<": (0, "read"),
        "1>": (1, "write"),
        "1>>": (1, "append"),
        "2>": (2, "write"),
        "2>>": (2, "append"),
    }
    _REDIRECT_INLINE_PATTERN = re.compile(r"^(?:(\d+)?(>>|>|<))(.*)$")
    _PROCESS_SUBSTITUTION_PATTERN = re.compile(r"^[<>]\((.+)\)$")

    def parse(self, command: str) -> CommandAST:
        """Parse shell command text into a structured AST."""
        if command is None:
            raise ValueError("command is required")
        return self._parse_command(command, recursion_depth=0)

    def extract_all_executables(self, ast: CommandAST) -> List[str]:
        """Recursively gather every executable reachable from a command AST."""
        executables: List[str] = []

        def walk(node: CommandAST) -> None:
            if node.executable:
                executables.append(node.executable)
            for piped in node.pipes:
                walk(piped)
            for subshell in node.subshells:
                walk(subshell)
            for _, chained in node.chained:
                walk(chained)
            for redirect in node.redirects:
                process_substitution = self._extract_process_substitution(redirect.target)
                if process_substitution:
                    walk(self.parse(process_substitution))

        walk(ast)
        return executables

    def detect_shell_in_shell(self, ast: CommandAST) -> bool:
        """Detect shell execution wrappers and eval-like indirection."""

        def walk(node: CommandAST) -> bool:
            executable = node.executable.lower()
            arguments = [arg.lower() for arg in node.arguments]
            joined_arguments = " ".join(node.arguments)

            if executable in self._SHELL_EXECUTABLES and "-c" in arguments:
                return True
            if executable in self._SCRIPT_WRAPPERS and any(flag in arguments for flag in ("-c", "-e")):
                return True
            if executable in {"eval", "exec"}:
                return True
            if re.search(r"\b(os\.system|subprocess\.(?:run|call|popen)|exec\()", joined_arguments):
                return True

            for child in node.pipes:
                if walk(child):
                    return True
            for child in node.subshells:
                if walk(child):
                    return True
            for _, child in node.chained:
                if walk(child):
                    return True
            return False

        return walk(ast)

    def _parse_command(self, command: str, recursion_depth: int) -> CommandAST:
        if recursion_depth > 6:
            return CommandAST(raw=command, executable="", arguments=[])

        normalized = command.strip()
        if not normalized:
            return CommandAST(raw=command, executable="", arguments=[])

        background = self._ends_with_background(normalized)
        command_without_background = self._strip_trailing_background(normalized)

        chain_segments, operators = self._split_top_level(command_without_background, ("&&", "||"))
        lead = self._parse_pipeline(chain_segments[0], recursion_depth=recursion_depth)
        lead.background = background
        lead.raw = command
        for operator, segment in zip(operators, chain_segments[1:]):
            lead.chained.append((operator, self._parse_pipeline(segment, recursion_depth=recursion_depth)))
        return lead

    def _parse_pipeline(self, segment: str, recursion_depth: int) -> CommandAST:
        parts, _ = self._split_top_level(segment, ("|",))
        lead = self._parse_simple_command(parts[0], recursion_depth=recursion_depth)
        for part in parts[1:]:
            lead.pipes.append(self._parse_simple_command(part, recursion_depth=recursion_depth))
        return lead

    def _parse_simple_command(self, segment: str, recursion_depth: int) -> CommandAST:
        text = segment.strip()
        if not text:
            return CommandAST(raw=segment, executable="", arguments=[])

        try:
            tokens = shlex.split(text, posix=True)
        except ValueError:
            tokens = text.split()

        env_vars: Dict[str, str] = {}
        index = 0
        while index < len(tokens):
            match = self._ENV_ASSIGNMENT_PATTERN.match(tokens[index])
            if not match:
                break
            name, value = tokens[index].split("=", 1)
            env_vars[name] = value
            index += 1

        args: List[str] = []
        redirects: List[Redirect] = []
        while index < len(tokens):
            token = tokens[index]
            parsed = self._parse_redirect(token, tokens[index + 1] if index + 1 < len(tokens) else None)
            if parsed is not None:
                redirect, consumed = parsed
                redirects.append(redirect)
                index += consumed
                continue
            args.append(token)
            index += 1

        executable = args[0] if args else ""
        arguments = args[1:] if len(args) > 1 else []
        subshells = self._extract_subshells(text, recursion_depth=recursion_depth)

        return CommandAST(
            raw=text,
            executable=executable,
            arguments=arguments,
            pipes=[],
            redirects=redirects,
            background=False,
            subshells=subshells,
            environment_vars=env_vars,
            chained=[],
        )

    def _parse_redirect(self, token: str, next_token: str | None) -> tuple[Redirect, int] | None:
        if token in self._REDIRECT_TOKENS:
            fd, mode = self._REDIRECT_TOKENS[token]
            if not next_token:
                return None
            return Redirect(fd=fd, target=next_token, mode=mode), 2

        if token == "2>&1":
            return Redirect(fd=2, target="&1", mode="write"), 1

        inline_match = self._REDIRECT_INLINE_PATTERN.match(token)
        if not inline_match:
            return None

        fd_raw, op, trailing = inline_match.groups()
        fd = int(fd_raw) if fd_raw else (0 if op == "<" else 1)
        mode: RedirectMode = "append" if op == ">>" else ("read" if op == "<" else "write")
        target = trailing or (next_token or "")
        if not target:
            return None
        return Redirect(fd=fd, target=target, mode=mode), (1 if trailing else 2)

    def _extract_subshells(self, text: str, recursion_depth: int) -> List[CommandAST]:
        subshells: List[CommandAST] = []

        for inner in self._extract_dollar_parentheses(text):
            if inner:
                subshells.append(self._parse_command(inner, recursion_depth=recursion_depth + 1))
        for inner in self._extract_backticks(text):
            if inner:
                subshells.append(self._parse_command(inner, recursion_depth=recursion_depth + 1))

        for process_inner in self._extract_process_substitutions_from_text(text):
            if process_inner:
                subshells.append(self._parse_command(process_inner, recursion_depth=recursion_depth + 1))

        return subshells

    def _split_top_level(self, text: str, operators: tuple[str, ...]) -> tuple[List[str], List[str]]:
        if not text:
            return [""], []
        segments: List[str] = []
        found_operators: List[str] = []
        buffer: List[str] = []
        operators_by_length = sorted(operators, key=len, reverse=True)

        in_single = False
        in_double = False
        backtick = False
        escape = False
        paren_depth = 0
        index = 0

        while index < len(text):
            char = text[index]
            if escape:
                buffer.append(char)
                escape = False
                index += 1
                continue
            if char == "\\" and not in_single:
                escape = True
                buffer.append(char)
                index += 1
                continue

            if char == "'" and not in_double and not backtick:
                in_single = not in_single
                buffer.append(char)
                index += 1
                continue
            if char == '"' and not in_single and not backtick:
                in_double = not in_double
                buffer.append(char)
                index += 1
                continue
            if char == "`" and not in_single:
                backtick = not backtick
                buffer.append(char)
                index += 1
                continue

            if not in_single and not in_double and not backtick:
                if text.startswith("$(", index):
                    paren_depth += 1
                    buffer.append("$(")
                    index += 2
                    continue
                if char == "(" and paren_depth > 0:
                    paren_depth += 1
                elif char == ")" and paren_depth > 0:
                    paren_depth -= 1

                if paren_depth == 0:
                    matched_operator = None
                    for operator in operators_by_length:
                        if text.startswith(operator, index):
                            matched_operator = operator
                            break
                    if matched_operator is not None:
                        segments.append("".join(buffer).strip())
                        found_operators.append(matched_operator)
                        buffer = []
                        index += len(matched_operator)
                        continue

            buffer.append(char)
            index += 1

        segments.append("".join(buffer).strip())
        return segments, found_operators

    @staticmethod
    def _ends_with_background(text: str) -> bool:
        return bool(re.search(r"(?<!&)&\s*$", text))

    @staticmethod
    def _strip_trailing_background(text: str) -> str:
        return re.sub(r"(?<!&)&\s*$", "", text).strip()

    def _extract_dollar_parentheses(self, text: str) -> List[str]:
        commands: List[str] = []
        index = 0
        while index < len(text):
            if not text.startswith("$(", index):
                index += 1
                continue
            index += 2
            depth = 1
            start = index
            in_single = False
            in_double = False
            escape = False
            while index < len(text) and depth > 0:
                char = text[index]
                if escape:
                    escape = False
                    index += 1
                    continue
                if char == "\\" and not in_single:
                    escape = True
                    index += 1
                    continue
                if char == "'" and not in_double:
                    in_single = not in_single
                    index += 1
                    continue
                if char == '"' and not in_single:
                    in_double = not in_double
                    index += 1
                    continue
                if not in_single and not in_double:
                    if text.startswith("$(", index):
                        depth += 1
                        index += 2
                        continue
                    if char == "(":
                        depth += 1
                    elif char == ")":
                        depth -= 1
                        if depth == 0:
                            commands.append(text[start:index].strip())
                            index += 1
                            break
                index += 1
        return commands

    @staticmethod
    def _extract_backticks(text: str) -> List[str]:
        commands: List[str] = []
        starts: List[int] = []
        escape = False
        for index, char in enumerate(text):
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == "`":
                if starts:
                    start = starts.pop()
                    commands.append(text[start + 1 : index].strip())
                else:
                    starts.append(index)
        return commands

    def _extract_process_substitutions_from_text(self, text: str) -> List[str]:
        command_texts: List[str] = []
        for match in re.finditer(r"[<>]\(([^)]+)\)", text):
            inner = match.group(1).strip()
            if inner:
                command_texts.append(inner)
        return command_texts

    def _extract_process_substitution(self, target: str) -> str | None:
        match = self._PROCESS_SUBSTITUTION_PATTERN.match(target.strip())
        if not match:
            return None
        return match.group(1).strip()
