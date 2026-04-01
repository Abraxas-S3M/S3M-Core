"""Training course catalog management for Layer 12."""

from __future__ import annotations

from typing import Dict, List, Optional
from uuid import uuid4

from apps.simulation.models import Course


class CourseManager:
    """Creates and tracks military training course offerings."""

    def __init__(self, officer_manager=None):
        self._courses: Dict[str, Course] = {}
        self._officer_manager = officer_manager

    def create_course(self, name, course_type, description, modules: List[dict], prerequisites=None, certification=None) -> Course:
        course = Course(
            course_id=f"course-{uuid4().hex[:10]}",
            name=str(name),
            description=str(description),
            course_type=str(course_type),
            modules=list(modules),
            prerequisites=list(prerequisites or []),
            certification_awarded=certification,
        )
        self._courses[course.course_id] = course
        return course

    def create_standard_courses(self) -> List[Course]:
        courses = [
            self.create_course(
                "Combined Arms Wargaming",
                "wargaming",
                "Integrated land maneuver and fire support decision training.",
                [
                    {"module_id": "m1", "name": "Doctrine Overview", "type": "lecture", "duration_minutes": 60, "required": True},
                    {"module_id": "m2", "name": "Terrain Analysis", "type": "quiz", "duration_minutes": 45, "required": True},
                    {"module_id": "m3", "name": "COA Development", "type": "wargame", "duration_minutes": 90, "required": True},
                    {"module_id": "m4", "name": "Full Exercise", "type": "exercise", "duration_minutes": 120, "required": True},
                ],
                certification="S3M Wargaming Level 1",
            ),
            self.create_course(
                "Cyber Defense Operations",
                "cyber_defense",
                "SOC operations and incident response in contested networks.",
                [
                    {"module_id": "m1", "name": "SOC Fundamentals", "type": "lecture", "duration_minutes": 60, "required": True},
                    {"module_id": "m2", "name": "Threat Analysis", "type": "quiz", "duration_minutes": 45, "required": True},
                    {"module_id": "m3", "name": "Incident Response Exercise", "type": "exercise", "duration_minutes": 90, "required": True},
                    {"module_id": "m4", "name": "Advanced Playbook Execution", "type": "exercise", "duration_minutes": 90, "required": True},
                ],
                certification="S3M Cyber Defender",
            ),
            self.create_course(
                "Maritime Domain Awareness",
                "combined_arms",
                "Maritime ISR and coastal defense tactics.",
                [
                    {"module_id": "m1", "name": "SAR/AIS Fundamentals", "type": "lecture", "duration_minutes": 60, "required": True},
                    {"module_id": "m2", "name": "Maritime Surveillance Exercise", "type": "exercise", "duration_minutes": 90, "required": True},
                    {"module_id": "m3", "name": "Border Defense Wargame", "type": "wargame", "duration_minutes": 90, "required": True},
                ],
                certification="S3M Maritime Watch",
            ),
            self.create_course(
                "Autonomous Systems Command",
                "c2",
                "Command doctrine for AI-enabled and unmanned force packages.",
                [
                    {"module_id": "m1", "name": "Swarm Doctrine", "type": "lecture", "duration_minutes": 60, "required": True},
                    {"module_id": "m2", "name": "NL Command Training", "type": "wargame", "duration_minutes": 60, "required": True},
                    {"module_id": "m3", "name": "Drone Ops Exercise", "type": "exercise", "duration_minutes": 90, "required": True},
                ],
                certification="S3M Autonomy Commander",
            ),
            self.create_course(
                "Coalition Operations",
                "c2",
                "Coalition interoperability and force coordination workflows.",
                [
                    {"module_id": "m1", "name": "DIS/C2SIM Protocols", "type": "lecture", "duration_minutes": 45, "required": True},
                    {"module_id": "m2", "name": "ORBAT Exchange Exercise", "type": "exercise", "duration_minutes": 75, "required": True},
                    {"module_id": "m3", "name": "Coalition Wargame", "type": "wargame", "duration_minutes": 90, "required": True},
                ],
                certification="S3M Coalition Coordinator",
            ),
        ]
        return courses

    def get_course(self, course_id) -> Optional[Course]:
        return self._courses.get(course_id)

    def get_courses(self, course_type=None) -> List[Course]:
        courses = list(self._courses.values())
        if course_type is not None:
            courses = [course for course in courses if course.course_type == course_type]
        return courses

    def get_prerequisites_met(self, officer_id, course_id) -> bool:
        course = self._courses.get(course_id)
        if course is None:
            return False
        if not course.prerequisites:
            return True
        if self._officer_manager is None:
            return False
        officer = self._officer_manager.get_officer(officer_id)
        if officer is None:
            return False
        completed = set(officer.courses_completed)
        return all(pr in completed for pr in course.prerequisites)
