"""Scenario management for large-scale behavioral audits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping


SCENARIO_CATEGORIES = (
    "misuse_cooperation",
    "system_prompt_manipulation",
    "prefill_susceptibility",
    "reckless_tool_use",
    "deception",
    "sycophancy",
    "self_preservation",
    "power_seeking",
    "evaluation_awareness",
    "overrefusal",
    "honesty",
    "character_stability",
    "sovereignty_alignment",
)

REQUIRED_LANGUAGE_KEYS = ("en", "ar")


@dataclass(frozen=True)
class Scenario:
    """Single probe case with bilingual prompts and expected behavior boundaries."""

    id: str
    category: str
    description: Dict[str, str]
    desired_behavior: Dict[str, str]
    undesired_behavior: Dict[str, str]
    tools_available: List[str]
    risk_level: str
    investigator_instructions: Dict[str, str]

    def __post_init__(self) -> None:
        if self.category not in SCENARIO_CATEGORIES:
            raise ValueError(f"Unsupported category: {self.category}")
        for field_name in ("description", "desired_behavior", "undesired_behavior", "investigator_instructions"):
            field_value = getattr(self, field_name)
            missing_languages = [language for language in REQUIRED_LANGUAGE_KEYS if language not in field_value]
            if missing_languages:
                raise ValueError(f"{field_name} is missing language keys: {missing_languages}")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "Scenario":
        def _bilingual(value: object, field_name: str) -> Dict[str, str]:
            if isinstance(value, str):
                return {"en": value, "ar": value}
            if not isinstance(value, Mapping):
                raise ValueError(f"{field_name} must be a string or language map.")
            result = {key: str(text) for key, text in value.items() if key in REQUIRED_LANGUAGE_KEYS}
            missing = [language for language in REQUIRED_LANGUAGE_KEYS if language not in result]
            if missing:
                raise ValueError(f"{field_name} missing {missing}")
            return result

        raw_tools = payload.get("tools_available", [])
        if raw_tools is None:
            raw_tools = []
        if not isinstance(raw_tools, list):
            raise ValueError("tools_available must be a list of tool names")

        return cls(
            id=str(payload["id"]),
            category=str(payload["category"]),
            description=_bilingual(payload["description"], "description"),
            desired_behavior=_bilingual(payload["desired_behavior"], "desired_behavior"),
            undesired_behavior=_bilingual(payload["undesired_behavior"], "undesired_behavior"),
            tools_available=[str(tool) for tool in raw_tools],
            risk_level=str(payload.get("risk_level", "medium")),
            investigator_instructions=_bilingual(
                payload["investigator_instructions"],
                "investigator_instructions",
            ),
        )


class ScenarioLibrary:
    """Loads, validates, and serves scenario definitions for audits."""

    def __init__(self) -> None:
        self._scenarios: Dict[str, Scenario] = {}

    def load_scenarios(self, path: str) -> None:
        """Load and validate a scenario set from JSON or JSONL."""

        source_path = Path(path)
        if not source_path.exists():
            raise FileNotFoundError(f"Scenario file not found: {source_path}")

        loaded_scenarios = list(self._load_payload(source_path))
        self._validate_minimum_coverage(loaded_scenarios)
        self._scenarios = {scenario.id: scenario for scenario in loaded_scenarios}

    def get_scenario(self, id: str) -> Scenario:
        """Retrieve a scenario by stable ID."""

        try:
            return self._scenarios[id]
        except KeyError as error:
            raise KeyError(f"Scenario {id!r} was not found") from error

    def list_scenarios(self) -> List[Scenario]:
        """Return all loaded scenarios sorted by identifier."""

        return [self._scenarios[scenario_id] for scenario_id in sorted(self._scenarios)]

    def _load_payload(self, source_path: Path) -> Iterable[Scenario]:
        if source_path.suffix.lower() == ".jsonl":
            for line_number, line in enumerate(source_path.read_text(encoding="utf-8").splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid JSONL at line {line_number}: {error}") from error
                yield Scenario.from_mapping(payload)
            return

        raw_content = json.loads(source_path.read_text(encoding="utf-8"))
        if isinstance(raw_content, Mapping):
            payloads = raw_content.get("scenarios")
            if payloads is None:
                raise ValueError("JSON scenario documents must include a top-level 'scenarios' list.")
        elif isinstance(raw_content, list):
            payloads = raw_content
        else:
            raise ValueError("Scenario file must contain a list or {'scenarios': [...]} structure.")

        if not isinstance(payloads, list):
            raise ValueError("Scenario collection must be a list.")
        for payload in payloads:
            if not isinstance(payload, Mapping):
                raise ValueError("Each scenario entry must be an object.")
            yield Scenario.from_mapping(payload)

    def _validate_minimum_coverage(self, scenarios: List[Scenario]) -> None:
        if len(scenarios) < 1150:
            raise ValueError("Behavioral audit requires at least 1,150 scenarios.")

        by_category: Dict[str, int] = {category: 0 for category in SCENARIO_CATEGORIES}
        scenario_ids: set[str] = set()
        for scenario in scenarios:
            if scenario.id in scenario_ids:
                raise ValueError(f"Duplicate scenario ID detected: {scenario.id}")
            scenario_ids.add(scenario.id)
            by_category[scenario.category] += 1

        underfilled = {
            category: count
            for category, count in by_category.items()
            if count < 50
        }
        if underfilled:
            raise ValueError(
                "Each Mythos category must contain at least 50 scenarios. "
                f"Current coverage: {underfilled}"
            )
