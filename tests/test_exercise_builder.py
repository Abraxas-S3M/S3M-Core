from apps.simulation.exercises.exercise_builder import ExerciseBuilder


def _participants():
    return [{"officer_id": "off-1", "role": "commander"}]


def test_create_tabletop_has_four_phases():
    builder = ExerciseBuilder()
    ex = builder.create_tabletop("Tabletop", "Brief", _participants())
    assert len(ex.phases) == 4


def test_create_command_post_has_dis_phase():
    builder = ExerciseBuilder()
    ex = builder.create_command_post("CPX", _participants(), "blue", "red")
    assert any("DIS" in phase.description or "ORBAT" in phase.description for phase in ex.phases)


def test_create_cyber_has_soc_phase():
    builder = ExerciseBuilder()
    ex = builder.create_cyber_exercise("Cyber", _participants())
    assert any("SOC" in phase.name or "SOC" in phase.description for phase in ex.phases)


def test_templates_have_expected_phase_counts():
    builder = ExerciseBuilder()
    assert len(builder.create_tabletop("A", "B", _participants()).phases) == 4
    assert len(builder.create_command_post("A", _participants(), "b", "r").phases) == 4
    assert len(builder.create_cyber_exercise("A", _participants()).phases) == 4
