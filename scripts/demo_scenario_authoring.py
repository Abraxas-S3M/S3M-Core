#!/usr/bin/env python3
"""Layer 12 scenario authoring demonstration."""

from __future__ import annotations

from apps.simulation.scenario_author import ScenarioAuthor


def main() -> None:
    author = ScenarioAuthor()

    brief = (
        "Saudi 1st Armored Brigade defends against a battalion-sized enemy assault "
        "from the northeast in desert terrain with limited air support"
    )
    scenario_from_brief = author.create_from_brief(brief)
    print("=== SCENARIO FROM BRIEF ===")
    print(scenario_from_brief)

    scenario_from_orbat = author.create_from_orbat("saudi-1st-armored", "enemy-battalion", terrain="desert")
    print("=== SCENARIO FROM ORBAT ===")
    print(scenario_from_orbat)

    print("=== TEMPLATES ===")
    for template in author.get_scenario_templates():
        print(template)

    xml = author.export_to_msdl(scenario_from_orbat)
    print("=== MSDL EXPORT ===")
    print(xml)


if __name__ == "__main__":
    main()
