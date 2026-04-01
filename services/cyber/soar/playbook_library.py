"""YAML-backed playbook library for Layer 07 SOC response automation."""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Dict, List, Optional

import yaml

from services.cyber.models import CaseSeverity, IncidentCase, Playbook, PlaybookAction, PlaybookStep


class PlaybookLibrary:
    """Loads and matches playbooks against incident context."""

    def __init__(self, playbooks_dir: str = "configs/cyber/playbooks/") -> None:
        self.playbooks_dir = playbooks_dir
        self._playbooks: Dict[str, Playbook] = {}

    def load_from_yaml(self, filepath: str) -> Playbook:
        with open(filepath, "r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        pb = payload.get("playbook", {})
        steps = [
            PlaybookStep(
                step_id=int(step.get("step_id")),
                name=str(step.get("name", f"Step {idx+1}")),
                action=PlaybookAction.from_value(step.get("action", "CUSTOM")),
                parameters=dict(step.get("parameters", {})),
                condition=step.get("condition"),
                timeout_seconds=float(step.get("timeout_seconds", 30)),
                on_failure=str(step.get("on_failure", "continue")),
            )
            for idx, step in enumerate(pb.get("steps", []))
        ]
        playbook = Playbook(
            playbook_id=str(pb.get("id", "")),
            name=str(pb.get("name", "")),
            description=str(pb.get("description", "")),
            trigger_conditions=list(pb.get("trigger_conditions", [])),
            steps=steps,
            author=str(pb.get("author", "S3M SOC")),
            version=str(pb.get("version", "1.0")),
            mitre_techniques=list(pb.get("mitre_techniques", [])),
            tags=list(pb.get("tags", [])),
        )
        self._playbooks[playbook.playbook_id] = playbook
        return playbook

    def load_all(self) -> List[Playbook]:
        loaded: List[Playbook] = []
        if not os.path.isdir(self.playbooks_dir):
            return loaded
        for name in sorted(os.listdir(self.playbooks_dir)):
            if not name.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(self.playbooks_dir, name)
            try:
                loaded.append(self.load_from_yaml(path))
            except Exception:
                continue
        return loaded

    def get_playbook(self, playbook_id: str) -> Optional[Playbook]:
        return self._playbooks.get(playbook_id)

    def list_playbooks(self, mitre_technique: str = None, tag: str = None) -> List[dict]:
        items = list(self._playbooks.values())
        if mitre_technique:
            items = [pb for pb in items if mitre_technique in pb.mitre_techniques]
        if tag:
            items = [pb for pb in items if tag in pb.tags]
        return [pb.to_dict() for pb in items]

    def _evaluate_condition(self, case: IncidentCase, condition: str) -> bool:
        expr = condition.strip()
        if not expr:
            return True
        sev_order = {
            "INFORMATIONAL": 1,
            "LOW": 2,
            "MEDIUM": 3,
            "HIGH": 4,
            "CRITICAL": 5,
        }
        if expr.startswith("severity >="):
            target = expr.split(">=", 1)[1].strip().upper()
            return sev_order[case.severity.value] >= sev_order.get(target, 99)
        if expr.startswith("mitre_technique =="):
            target = expr.split("==", 1)[1].strip()
            return target in case.mitre_techniques
        if expr.startswith("mitre_technique in"):
            vals = re.findall(r"T\d{4}", expr)
            return any(v in case.mitre_techniques for v in vals)
        if expr.startswith("enrichment_verdict =="):
            target = expr.split("==", 1)[1].strip().lower()
            verdicts = [
                str(item.get("verdict", "")).lower()
                for item in case.enrichments
                if isinstance(item, dict)
            ]
            return target in verdicts
        if expr.startswith("enrichment_verdict !="):
            target = expr.split("!=", 1)[1].strip().lower()
            verdicts = [
                str(item.get("verdict", "")).lower()
                for item in case.enrichments
                if isinstance(item, dict)
            ]
            return any(v != target for v in verdicts) if verdicts else True
        if expr.startswith("category =="):
            # Layer 07 cases are cyber by design when generated from threat_detection.
            target = expr.split("==", 1)[1].strip().upper()
            return target == "CYBER"
        if "description contains" in expr.lower():
            clauses = re.split(r"\s+OR\s+", expr, flags=re.IGNORECASE)
            desc = case.description.lower()
            for clause in clauses:
                m = re.search(r"description contains\s+(.+)$", clause, flags=re.IGNORECASE)
                if m and m.group(1).strip().lower() in desc:
                    return True
            return False
        if expr.startswith("tag =="):
            target = expr.split("==", 1)[1].strip()
            return target in case.tags
        return False

    def match_playbook(self, case: IncidentCase) -> Optional[Playbook]:
        candidates: List[tuple[int, Playbook]] = []
        for playbook in self._playbooks.values():
            if not playbook.trigger_conditions:
                continue
            matches = [self._evaluate_condition(case, cond) for cond in playbook.trigger_conditions]
            score = sum(1 for ok in matches if ok)
            if score == len(playbook.trigger_conditions):
                # Higher score and step count favor richer tactical responses.
                candidates.append((score * 100 + playbook.step_count(), playbook))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def get_stats(self) -> dict:
        by_tactic = Counter()
        by_tag = Counter()
        for playbook in self._playbooks.values():
            for technique in playbook.mitre_techniques:
                by_tactic[technique] += 1
            for tag in playbook.tags:
                by_tag[tag] += 1
        return {
            "total_playbooks": len(self._playbooks),
            "by_mitre_tactic": dict(by_tactic),
            "by_tag": dict(by_tag),
        }
