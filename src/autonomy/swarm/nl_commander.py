"""Natural-language command parser for tactical swarm command and control.

This parser converts operator intent (English or Arabic) into structured
commands while preserving a robust keyword fallback for air-gapped operation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Tuple

from src.autonomy.models import CommandType, FormationType, SwarmCommand
from src.autonomy.swarm.swarm_protocol import SwarmProtocol


class NLCommander:
    """Parse natural language mission orders into SwarmCommand messages."""

    def __init__(self) -> None:
        self.protocol = SwarmProtocol()
        self._history: List[Dict[str, Any]] = []

    def _record(self, source_text: str, language: str, command: SwarmCommand, mode: str) -> None:
        self._history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "language": language,
                "input": source_text,
                "mode": mode,
                "command": command.to_dict(),
            }
        )
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

    def _parse_grid_coordinates(self, text: str) -> Optional[Tuple[float, float, float]]:
        nums = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
        if len(nums) >= 3:
            return float(nums[0]), float(nums[1]), float(nums[2])
        if len(nums) == 2:
            return float(nums[0]), float(nums[1]), 0.0
        return None

    def _keyword_fallback(self, natural_language: str, language: str = "en") -> SwarmCommand:
        text = (natural_language or "").strip().lower()
        if not text:
            return self.protocol.create_command(
                command_type=CommandType.HOLD,
                target_agents=["all"],
                parameters={"reason": "empty command"},
                issued_by="operator",
            )

        if language == "ar":
            if "عودة للقاعدة" in text or "العودة للقاعدة" in text:
                return self.protocol.create_command(CommandType.RTB, ["all"], {}, issued_by="operator")
            if "توقف" in text:
                return self.protocol.create_emergency_stop()
            if "هجوم" in text or "اشتبك" in text:
                return self.protocol.create_command(CommandType.ENGAGE, ["all"], {}, issued_by="operator")
            if "انسحاب" in text:
                return self.protocol.create_command(CommandType.DISENGAGE, ["all"], {}, issued_by="operator")
            if "دورية" in text:
                return self.protocol.create_command(
                    CommandType.REPLAN, ["all"], {"mode": "patrol"}, issued_by="operator"
                )

        if "emergency stop" in text or "abort" in text:
            return self.protocol.create_emergency_stop()
        if "return to base" in text or "rtb" in text:
            return self.protocol.create_command(CommandType.RTB, ["all"], {}, issued_by="operator")
        if "hold position" in text or text.startswith("hold"):
            return self.protocol.create_command(CommandType.HOLD, ["all"], {}, issued_by="operator")
        if "engage target" in text or text.startswith("engage"):
            return self.protocol.create_command(CommandType.ENGAGE, ["all"], {}, issued_by="operator")
        if "move" in text and "grid" in text:
            coords = self._parse_grid_coordinates(text)
            if coords:
                return self.protocol.create_command(
                    CommandType.MOVE_TO, ["all"], {"waypoint": list(coords)}, issued_by="operator"
                )
        if "form wedge" in text:
            return self.protocol.create_command(
                CommandType.CHANGE_FORMATION, ["all"], {"formation": FormationType.WEDGE.value}, issued_by="operator"
            )
        if "form line" in text:
            return self.protocol.create_command(
                CommandType.CHANGE_FORMATION, ["all"], {"formation": FormationType.LINE.value}, issued_by="operator"
            )
        if "form diamond" in text:
            return self.protocol.create_command(
                CommandType.CHANGE_FORMATION,
                ["all"],
                {"formation": FormationType.DIAMOND.value},
                issued_by="operator",
            )
        return self.protocol.create_command(
            command_type=CommandType.HOLD,
            target_agents=["all"],
            parameters={"note": "unparsed input; default hold"},
            issued_by="operator",
        )

    def _llm_parse(self, text: str, language: str = "en") -> Optional[SwarmCommand]:
        # Tactical rationale: LLM parsing expands language flexibility but remains optional.
        try:
            from src.llm_core.orchestrator import Orchestrator, QueryRequest

            orchestrator = Orchestrator()
            valid_command_types = ", ".join([ct.value for ct in CommandType])
            prompt = (
                "You are a tactical command parser.\n"
                f"Valid command_type values: {valid_command_types}\n"
                "Return a compact response with lines:\n"
                "command_type=<value>\n"
                "target_agents=<comma-separated IDs or all>\n"
                "parameters=<json-like key:value pairs>\n"
                f"Language={language}\n"
                f"Operator command: {text}\n"
            )
            request = QueryRequest(prompt=prompt)
            response = orchestrator.process(request)
            raw = getattr(response, "text", "") or ""
            if not raw:
                return None
            cmd_match = re.search(r"command_type\s*=\s*([a-z_]+)", raw, flags=re.IGNORECASE)
            if not cmd_match:
                return None
            cmd_name = cmd_match.group(1).lower()
            command_type = None
            for candidate in CommandType:
                if candidate.value == cmd_name:
                    command_type = candidate
                    break
            if command_type is None:
                return None

            targets_match = re.search(r"target_agents\s*=\s*([a-zA-Z0-9_,\-\s]+)", raw)
            targets = ["all"]
            if targets_match:
                raw_targets = [item.strip() for item in targets_match.group(1).split(",") if item.strip()]
                targets = raw_targets or ["all"]

            params: Dict[str, Any] = {}
            waypoint = self._parse_grid_coordinates(text)
            if command_type == CommandType.MOVE_TO and waypoint:
                params["waypoint"] = list(waypoint)
            if command_type == CommandType.CHANGE_FORMATION:
                if "wedge" in text.lower():
                    params["formation"] = FormationType.WEDGE.value
                elif "line" in text.lower():
                    params["formation"] = FormationType.LINE.value
                elif "diamond" in text.lower():
                    params["formation"] = FormationType.DIAMOND.value

            return self.protocol.create_command(
                command_type=command_type,
                target_agents=targets,
                parameters=params,
                issued_by="operator",
            )
        except Exception:
            return None

    def parse_command(self, natural_language: str) -> SwarmCommand:
        """Parse English natural language into a validated SwarmCommand."""
        if not isinstance(natural_language, str):
            raise ValueError("natural_language must be a string")
        parsed = self._llm_parse(natural_language, language="en")
        if parsed is None:
            parsed = self._keyword_fallback(natural_language, language="en")
            self._record(natural_language, "en", parsed, mode="keyword_fallback")
        else:
            self._record(natural_language, "en", parsed, mode="llm")
        return parsed

    def parse_arabic_command(self, arabic_text: str) -> SwarmCommand:
        """Parse Arabic command text via ALLaM-oriented route with fallback."""
        if not isinstance(arabic_text, str):
            raise ValueError("arabic_text must be a string")
        parsed = self._llm_parse(arabic_text, language="ar")
        if parsed is None:
            parsed = self._keyword_fallback(arabic_text, language="ar")
            self._record(arabic_text, "ar", parsed, mode="keyword_fallback")
        else:
            self._record(arabic_text, "ar", parsed, mode="llm")
        return parsed

    def get_command_history(self) -> List[Dict[str, Any]]:
        """Return NL parsing history for operator traceability."""
        return list(self._history)

