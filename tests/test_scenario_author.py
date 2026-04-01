from apps.simulation.scenario_author import ScenarioAuthor


def test_create_from_orbat_phase7_compatible():
    author = ScenarioAuthor()
    scenario = author.create_from_orbat("blue", "red")
    payload = scenario["scenario"]
    assert "forces" in payload
    assert "objectives" in payload


def test_create_from_brief_returns_scenario():
    author = ScenarioAuthor()
    scenario = author.create_from_brief("Defend desert corridor")
    assert "scenario" in scenario


def test_templates_count_five():
    author = ScenarioAuthor()
    assert len(author.get_scenario_templates()) == 5


def test_create_from_msdl_converts_xml():
    author = ScenarioAuthor()
    xml = "<MSDL id='s1' name='x'><Forces><Force name='Blue' allegiance='friendly'><Unit type='FRIENDLY_UGV' count='2' x='10' y='20'/></Force></Forces></MSDL>"
    scenario = author.create_from_msdl(xml)
    assert scenario["scenario"]["scenario_id"] == "s1"
