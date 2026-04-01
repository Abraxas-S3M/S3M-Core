from apps.simulation.training.course_manager import CourseManager
from apps.simulation.training.officer_manager import OfficerManager


def test_create_standard_courses_generates_five():
    cm = CourseManager()
    courses = cm.create_standard_courses()
    assert len(courses) == 5


def test_course_modules_have_types():
    cm = CourseManager()
    courses = cm.create_standard_courses()
    for course in courses:
        assert all("type" in m for m in course.modules)


def test_prerequisites_checking():
    om = OfficerManager()
    cm = CourseManager(officer_manager=om)
    c1 = cm.create_course(
        "Base",
        "wargaming",
        "d",
        [{"module_id": "m", "name": "n", "type": "lecture", "duration_minutes": 30, "required": True}],
    )
    c2 = cm.create_course(
        "Advanced",
        "wargaming",
        "d",
        [{"module_id": "m2", "name": "n", "type": "lecture", "duration_minutes": 30, "required": True}],
        prerequisites=[c1.course_id],
    )
    off = om.register_officer("A", "Captain", "U", "infantry")
    assert cm.get_prerequisites_met(off.officer_id, c2.course_id) is False
    om.record_course(off.officer_id, c1.course_id, 90)
    assert cm.get_prerequisites_met(off.officer_id, c2.course_id) is True


def test_total_hours_computation():
    cm = CourseManager()
    c = cm.create_course(
        "C",
        "wargaming",
        "d",
        [{"module_id": "m", "name": "n", "type": "lecture", "duration_minutes": 120, "required": True}],
    )
    assert c.total_hours() == 2.0
