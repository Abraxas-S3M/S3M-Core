"""Tests for S3M Quad-Engine Registry"""

import sys
sys.path.insert(0, ".")

from src.llm_core.engine_registry import EngineRegistry, EngineID, TaskDomain, DOMAIN_ROUTING


def test_all_engines_registered():
    registry = EngineRegistry()
    engines = registry.get_all_engines()
    assert len(engines) == 4
    print("PASS: All 4 engines registered")


def test_engine_names():
    registry = EngineRegistry()
    names = [e.name for e in registry.get_all_engines()]
    assert "Phi-3 Medium" in names
    assert "Grok-1" in names
    assert "Mixtral 8x7B" in names
    assert "ALLaM-7B" in names
    print("PASS: All engine names correct")


def test_domain_routing():
    assert DOMAIN_ROUTING[TaskDomain.TACTICAL] == EngineID.PHI3_MEDIUM
    assert DOMAIN_ROUTING[TaskDomain.REASONING] == EngineID.GROK1
    assert DOMAIN_ROUTING[TaskDomain.PLANNING] == EngineID.MIXTRAL
    assert DOMAIN_ROUTING[TaskDomain.ARABIC_NLP] == EngineID.ALLAM
    print("PASS: Domain routing correct")


def test_engine_status():
    registry = EngineRegistry()
    status = registry.get_status()
    assert all(v == False for v in status.values())
    registry.mark_loaded(EngineID.PHI3_MEDIUM)
    status = registry.get_status()
    assert status["phi3-medium"] == True
    print("PASS: Engine status tracking works")


if __name__ == "__main__":
    test_all_engines_registered()
    test_engine_names()
    test_domain_routing()
    test_engine_status()
    print("\nAll engine registry tests passed")
