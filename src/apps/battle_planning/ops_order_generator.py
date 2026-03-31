"""OPORD generator for battle planning vertical workflow."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional

from src.apps._shared import ensure_non_empty_text, first_non_empty, utc_now_iso
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class OpsOrderGenerator:
    """Generate and validate 5-paragraph military OPORD structures."""

    def __init__(self) -> None:
        self.orchestrator = Orchestrator()

    def _build_prompt(self, mission_brief: str, context: Optional[dict]) -> str:
        return (
            "Generate a military Operations Order (OPORD) from this mission brief. "
            "Use the standard 5-paragraph format: "
            "1) SITUATION (enemy forces, friendly forces, terrain/weather) "
            "2) MISSION (who, what, when, where, why) "
            "3) EXECUTION (concept of operations, tasks, coordinating instructions) "
            "4) SUSTAINMENT (logistics, supply, medical) "
            "5) COMMAND AND SIGNAL (command relationships, communications). "
            f"Mission brief: {mission_brief}. "
            f"Additional context: {context or {}}. "
            "Classification: UNCLASSIFIED - FOUO."
        )

    def _build_arabic_prompt(self, mission_brief: str) -> str:
        return (
            "أنشئ أمر عمليات عسكري (OPORD) من هذا الملخص. "
            "استخدم صيغة الفقرات الخمس القياسية: "
            "١) الموقف (قوات العدو، القوات الصديقة، الأرض/الطقس) "
            "٢) المهمة (من، ماذا، متى، أين، لماذا) "
            "٣) التنفيذ (مفهوم العمليات، المهام، تعليمات التنسيق) "
            "٤) الإسناد الإداري واللوجستي "
            "٥) القيادة والإشارة. "
            f"ملخص المهمة: {mission_brief}. "
            "التصنيف: UNCLASSIFIED - FOUO."
        )

    def _extract_section(self, text: str, patterns: list[str], default: str) -> str:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                if value:
                    return value
        return default

    def _parse_tasks(self, execution_text: str) -> list[str]:
        bullets = re.findall(r"(?:^|\n)\s*[-*]\s*(.+)", execution_text)
        numbered = re.findall(r"(?:^|\n)\s*\d+[\).]\s*(.+)", execution_text)
        tasks = [item.strip() for item in bullets + numbered if item.strip()]
        if tasks:
            return tasks[:8]
        sentence_tasks = [
            sentence.strip()
            for sentence in re.split(r"[.;]\s+", execution_text)
            if sentence.strip()
        ]
        return sentence_tasks[:4] if sentence_tasks else ["Conduct mission tasks as briefed."]

    def _template_opord(self, mission_brief: str, raw_llm_response: str = "") -> dict:
        brief = mission_brief.lower()
        area = "sector objective area"
        if "alpha" in brief:
            area = "Sector Alpha"
        elif "bravo" in brief:
            area = "Sector Bravo"
        elif "charlie" in brief:
            area = "Sector Charlie"
        timing = "H+0 immediate execution"
        if "tomorrow" in brief:
            timing = "D+1 execution window"
        elif "night" in brief:
            timing = "Night operations window"

        return {
            "opord_id": str(uuid.uuid4()),
            "timestamp": utc_now_iso(),
            "mission_brief": mission_brief,
            "paragraphs": {
                "situation": {
                    "enemy_forces": f"Enemy disposition unknown near {area}; expect reconnaissance elements.",
                    "friendly_forces": "Friendly patrol detachment on standby with ISR support.",
                    "terrain_weather": f"Mixed terrain around {area}; weather assessed as operationally acceptable.",
                },
                "mission": f"Friendly elements conduct mission in {area} at {timing} to achieve commander intent from brief.",
                "execution": {
                    "concept": "Phased approach: movement, observation, objective action, and controlled withdrawal.",
                    "tasks": [
                        "Stage forces and verify communications.",
                        f"Move to {area} and establish tactical posture.",
                        "Execute objective tasks with force protection.",
                        "Report status and return to base on completion.",
                    ],
                    "coordinating": "Weapons status per ROE in mission brief; maintain deconfliction and periodic SITREP updates.",
                },
                "sustainment": {
                    "logistics": "Allocate fuel, ammunition, and maintenance support for mission duration plus reserve.",
                    "supply": "Pre-stage Class I/III/V and battery resupply package at launch point.",
                    "medical": "CASEVAC route and medical team on alert during operation.",
                },
                "command_signal": {
                    "command": "Tactical lead controls mission execution under commander oversight.",
                    "signal": "Primary encrypted comms net with contingency frequency and authentication checks.",
                },
            },
            "raw_llm_response": raw_llm_response,
            "classification": "UNCLASSIFIED - FOUO",
        }

    def _parse_llm_to_opord(self, mission_brief: str, llm_text: str) -> dict:
        template = self._template_opord(mission_brief=mission_brief, raw_llm_response=llm_text)
        situation_text = self._extract_section(
            llm_text,
            [
                r"situation\s*[:\-]\s*(.*?)(?:mission\s*[:\-]|execution\s*[:\-]|$)",
                r"1\)\s*situation\s*(.*?)(?:2\)\s*mission|$)",
            ],
            "",
        )
        mission_text = self._extract_section(
            llm_text,
            [
                r"mission\s*[:\-]\s*(.*?)(?:execution\s*[:\-]|sustainment\s*[:\-]|$)",
                r"2\)\s*mission\s*(.*?)(?:3\)\s*execution|$)",
            ],
            template["paragraphs"]["mission"],
        )
        execution_text = self._extract_section(
            llm_text,
            [
                r"execution\s*[:\-]\s*(.*?)(?:sustainment\s*[:\-]|command\s*(?:and)?\s*signal\s*[:\-]|$)",
                r"3\)\s*execution\s*(.*?)(?:4\)\s*sustainment|$)",
            ],
            "",
        )
        sustainment_text = self._extract_section(
            llm_text,
            [
                r"sustainment\s*[:\-]\s*(.*?)(?:command\s*(?:and)?\s*signal\s*[:\-]|$)",
                r"4\)\s*sustainment\s*(.*?)(?:5\)\s*command|$)",
            ],
            "",
        )
        command_text = self._extract_section(
            llm_text,
            [
                r"command\s*(?:and)?\s*signal\s*[:\-]\s*(.*)$",
                r"5\)\s*command.*?\s*(.*)$",
            ],
            "",
        )

        if situation_text:
            template["paragraphs"]["situation"]["enemy_forces"] = first_non_empty(
                self._extract_section(situation_text, [r"enemy.*?[:\-]\s*(.*?)(?:friendly|terrain|$)"], ""),
                template["paragraphs"]["situation"]["enemy_forces"],
            )
            template["paragraphs"]["situation"]["friendly_forces"] = first_non_empty(
                self._extract_section(situation_text, [r"friendly.*?[:\-]\s*(.*?)(?:terrain|weather|$)"], ""),
                template["paragraphs"]["situation"]["friendly_forces"],
            )
            template["paragraphs"]["situation"]["terrain_weather"] = first_non_empty(
                self._extract_section(situation_text, [r"(terrain|weather).*?[:\-]\s*(.*)$"], ""),
                template["paragraphs"]["situation"]["terrain_weather"],
            )
        if execution_text:
            template["paragraphs"]["execution"]["concept"] = execution_text.split("\n")[0][:500]
            template["paragraphs"]["execution"]["tasks"] = self._parse_tasks(execution_text)
            template["paragraphs"]["execution"]["coordinating"] = execution_text[:700]
        if sustainment_text:
            template["paragraphs"]["sustainment"]["logistics"] = sustainment_text[:280]
            template["paragraphs"]["sustainment"]["supply"] = sustainment_text[:280]
            template["paragraphs"]["sustainment"]["medical"] = sustainment_text[:280]
        if command_text:
            template["paragraphs"]["command_signal"]["command"] = command_text[:280]
            template["paragraphs"]["command_signal"]["signal"] = command_text[:280]
        template["paragraphs"]["mission"] = mission_text
        return template

    def _llm_generate(self, prompt: str, domain: TaskDomain) -> str:
        response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=domain))
        text = getattr(response, "text", "") if response else ""
        return text if isinstance(text, str) else ""

    def _is_unavailable(self, llm_text: str) -> bool:
        marker = llm_text.lower()
        return "pending - engine not yet loaded" in marker or "consensus pending" in marker or not marker.strip()

    def generate(self, mission_brief: str, context: dict = None) -> dict:
        """Generate OPORD from mission brief with LLM fallback."""
        mission_brief = ensure_non_empty_text(mission_brief, "mission_brief")
        if context is not None and not isinstance(context, dict):
            raise ValueError("context must be a dictionary or None")
        prompt = self._build_prompt(mission_brief=mission_brief, context=context or {})
        llm_text = self._llm_generate(prompt, TaskDomain.PLANNING)
        if self._is_unavailable(llm_text):
            return self._template_opord(mission_brief=mission_brief, raw_llm_response=llm_text)
        return self._parse_llm_to_opord(mission_brief=mission_brief, llm_text=llm_text)

    def generate_arabic(self, mission_brief: str) -> dict:
        """Generate OPORD using Arabic NLP routing."""
        mission_brief = ensure_non_empty_text(mission_brief, "mission_brief")
        prompt = self._build_arabic_prompt(mission_brief)
        llm_text = self._llm_generate(prompt, TaskDomain.ARABIC_NLP)
        if self._is_unavailable(llm_text):
            return self._template_opord(mission_brief=mission_brief, raw_llm_response=llm_text)
        return self._parse_llm_to_opord(mission_brief=mission_brief, llm_text=llm_text)

    def validate_opord(self, opord: dict) -> tuple[bool, List[str]]:
        """Validate all five OPORD paragraphs are present and non-empty."""
        if not isinstance(opord, dict):
            return False, ["opord must be a dictionary"]
        paragraphs = opord.get("paragraphs", {})
        if not isinstance(paragraphs, dict):
            return False, ["paragraphs missing or invalid"]
        missing: List[str] = []

        situation = paragraphs.get("situation", {})
        if not isinstance(situation, dict):
            missing.append("situation")
        else:
            for key in ("enemy_forces", "friendly_forces", "terrain_weather"):
                if not isinstance(situation.get(key), str) or not situation.get(key, "").strip():
                    missing.append(f"situation.{key}")

        if not isinstance(paragraphs.get("mission"), str) or not paragraphs.get("mission", "").strip():
            missing.append("mission")

        execution = paragraphs.get("execution", {})
        if not isinstance(execution, dict):
            missing.append("execution")
        else:
            if not isinstance(execution.get("concept"), str) or not execution.get("concept", "").strip():
                missing.append("execution.concept")
            tasks = execution.get("tasks")
            if not isinstance(tasks, list) or not any(isinstance(t, str) and t.strip() for t in tasks):
                missing.append("execution.tasks")
            if not isinstance(execution.get("coordinating"), str) or not execution.get("coordinating", "").strip():
                missing.append("execution.coordinating")

        sustainment = paragraphs.get("sustainment", {})
        if not isinstance(sustainment, dict):
            missing.append("sustainment")
        else:
            for key in ("logistics", "supply", "medical"):
                if not isinstance(sustainment.get(key), str) or not sustainment.get(key, "").strip():
                    missing.append(f"sustainment.{key}")

        command_signal = paragraphs.get("command_signal", {})
        if not isinstance(command_signal, dict):
            missing.append("command_signal")
        else:
            for key in ("command", "signal"):
                if not isinstance(command_signal.get(key), str) or not command_signal.get(key, "").strip():
                    missing.append(f"command_signal.{key}")

        return len(missing) == 0, missing
