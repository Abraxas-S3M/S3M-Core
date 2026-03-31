"""
Tests that Arabic language support works across the full stack:
NL commands, OPORD generation, geopolitical analysis, dashboard labels.
"""

from __future__ import annotations

import pytest

from tests.integration._availability import has_module


AUTONOMY_NL_AVAILABLE = has_module("src.autonomy.swarm.nl_commander")
APPS_GEO_AVAILABLE = has_module("src.apps.geopolitical.event_analyzer")
APPS_BATTLE_AVAILABLE = has_module("src.apps.battle_planning")


@pytest.mark.skipif(not AUTONOMY_NL_AVAILABLE, reason="Arabic NL commander not available in this repository snapshot")
def test_arabic_nl_command_parsing() -> None:
    from src.autonomy.swarm.nl_commander import NLCommander

    commander = NLCommander()
    cmd = commander.parse_arabic_command("عودة للقاعدة")
    assert cmd is not None


@pytest.mark.skipif(not AUTONOMY_NL_AVAILABLE, reason="Arabic NL commander not available in this repository snapshot")
def test_arabic_keyword_commands() -> None:
    from src.autonomy.swarm.nl_commander import NLCommander

    commander = NLCommander()
    for text in ["توقف", "هجوم", "دورية", "انسحاب"]:
        cmd = commander.parse_arabic_command(text)
        assert cmd is not None


@pytest.mark.skipif(not APPS_GEO_AVAILABLE, reason="Geopolitical Arabic analyzer not available in this repository snapshot")
def test_arabic_geopolitical_analysis() -> None:
    from src.apps.geopolitical.event_analyzer import EventAnalyzer

    analyzer = EventAnalyzer()
    out = analyzer.analyze_arabic("تصاعد التوترات في مضيق هرمز", "الخليج العربي")
    assert isinstance(out, dict)


@pytest.mark.skipif(not APPS_BATTLE_AVAILABLE, reason="Battle planning Arabic OPORD generator not available in this repository snapshot")
def test_arabic_opord_generation() -> None:
    from src.apps.battle_planning import OpsOrderGenerator

    generator = OpsOrderGenerator()
    out = generator.generate_arabic("تنفيذ دورية بأربع طائرات بدون طيار في القطاع ألفا")
    assert isinstance(out, dict)
