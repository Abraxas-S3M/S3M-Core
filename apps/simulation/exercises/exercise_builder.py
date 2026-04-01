"""Exercise template and authoring tools for Layer 12."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from apps.simulation.models import Exercise, ExercisePhase


class ExerciseBuilder:
    """Creates structured exercise plans with phase-level objectives."""

    def __init__(self):
        pass

    def create_exercise(self, name, exercise_type, description, phases: List[dict], participants: List[dict]) -> Exercise:
        phase_objects: List[ExercisePhase] = []
        for idx, phase in enumerate(phases):
            phase_objects.append(
                ExercisePhase(
                    phase_id=f"phase-{idx+1}-{uuid4().hex[:6]}",
                    name=str(phase.get("name", f"Phase {idx+1}")),
                    description=str(phase.get("description", "Exercise phase")),
                    duration_minutes=int(phase.get("duration_minutes", 30)),
                    objectives=[str(o) for o in phase.get("objectives", [])],
                    evaluation_criteria=[str(c) for c in phase.get("evaluation_criteria", [])],
                    wargame_ids=list(phase.get("wargame_ids", [])),
                    status="pending",
                )
            )

        return Exercise(
            exercise_id=f"ex-{uuid4().hex[:10]}",
            name=str(name),
            description=str(description),
            exercise_type=str(exercise_type),
            phases=phase_objects,
            participants=list(participants),
            dis_exercise_id=None,
            c2sim_session=None,
            status="created",
            created_at=datetime.now(timezone.utc),
        )

    def create_tabletop(self, name, scenario_brief: str, participants: List[dict]) -> Exercise:
        phases = [
            {
                "name": "Scenario Briefing",
                "description": f"Lecture and mission framing: {scenario_brief}",
                "duration_minutes": 30,
                "objectives": ["Understand mission context", "Identify constraints"],
                "evaluation_criteria": ["Brief comprehension", "Threat articulation"],
            },
            {
                "name": "Planning & COA Development",
                "description": "Develop COAs with LLM adversary pressure testing.",
                "duration_minutes": 60,
                "objectives": ["Develop COAs", "Select preferred COA"],
                "evaluation_criteria": ["COA quality", "Risk analysis"],
            },
            {
                "name": "Execution & Decision Making",
                "description": "Run tactical wargame with escalating adversary behavior.",
                "duration_minutes": 90,
                "objectives": ["Maintain initiative", "Control losses"],
                "evaluation_criteria": ["Decision timeliness", "Command quality"],
            },
            {
                "name": "After Action Review",
                "description": "LLM-generated AAR and instructor debrief.",
                "duration_minutes": 30,
                "objectives": ["Capture lessons", "Define remediation plan"],
                "evaluation_criteria": ["Lesson quality", "Actionability"],
            },
        ]
        return self.create_exercise(name=name, exercise_type="tabletop", description=scenario_brief, phases=phases, participants=participants)

    def create_command_post(self, name, participants, orbat_blue, orbat_red) -> Exercise:
        phases = [
            {
                "name": "Force Deployment",
                "description": "ORBAT→MSDL→DIS initialization and force verification.",
                "duration_minutes": 30,
                "objectives": ["Validate force manifests", "Publish DIS entities"],
                "evaluation_criteria": ["Interop accuracy", "Deployment speed"],
            },
            {
                "name": "Operations",
                "description": "Wargame with DIS entity publishing and C2 synchronization.",
                "duration_minutes": 120,
                "objectives": ["Maintain COP", "Execute mission plan"],
                "evaluation_criteria": ["C2 quality", "Operational tempo"],
            },
            {
                "name": "Crisis Decision",
                "description": "Inject surprise event and force commander adaptation.",
                "duration_minutes": 30,
                "objectives": ["Absorb surprise", "Re-plan quickly"],
                "evaluation_criteria": ["Adaptation speed", "Decision quality"],
            },
            {
                "name": "AAR",
                "description": "Command-post exercise debrief and scoring.",
                "duration_minutes": 30,
                "objectives": ["Document outcomes", "Assign improvements"],
                "evaluation_criteria": ["AAR completeness", "Action follow-through"],
            },
        ]
        exercise = self.create_exercise(name, "command_post", f"Blue ORBAT={orbat_blue}, Red ORBAT={orbat_red}", phases, participants)
        exercise.dis_exercise_id = 1
        exercise.c2sim_session = f"c2sim-{uuid4().hex[:8]}"
        return exercise

    def create_cyber_exercise(self, name, participants, scenario_type: str = "brute_force") -> Exercise:
        phases = [
            {
                "name": "Threat Briefing",
                "description": "Threat actor profile and attack path briefing.",
                "duration_minutes": 15,
                "objectives": ["Understand threat", "Set SOC priorities"],
                "evaluation_criteria": ["Threat model quality"],
            },
            {
                "name": "SOC Defense",
                "description": f"Phase 13 cyber exercise execution ({scenario_type}).",
                "duration_minutes": 60,
                "objectives": ["Detect and triage", "Contain threat"],
                "evaluation_criteria": ["Detection speed", "Containment quality"],
            },
            {
                "name": "Incident Response",
                "description": "Execute playbooks and command escalation process.",
                "duration_minutes": 30,
                "objectives": ["Run playbooks", "Coordinate response"],
                "evaluation_criteria": ["Playbook completion", "Escalation discipline"],
            },
            {
                "name": "AAR",
                "description": "Cyber exercise lessons learned and readiness update.",
                "duration_minutes": 15,
                "objectives": ["Document gaps", "Plan improvements"],
                "evaluation_criteria": ["Recommendation quality"],
            },
        ]
        return self.create_exercise(name, "cyber", f"Cyber scenario: {scenario_type}", phases, participants)

    def get_templates(self) -> List[str]:
        return ["tabletop", "command_post", "cyber", "combined"]
