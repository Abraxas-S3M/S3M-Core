"""Unit tests for Layer 07 cyber training manager."""

from __future__ import annotations

from services.cyber.soc_manager import SOCManager
from services.cyber.training import CyberTrainingManager


def test_create_exercise_generates_counts():
    mgr = CyberTrainingManager(auto_create_manager=False)
    brute = mgr.create_exercise("brute_force")
    malware = mgr.create_exercise("malware")
    exfil = mgr.create_exercise("data_exfil")
    ransom = mgr.create_exercise("ransomware")
    assert len(brute["events"]) == 50
    assert len(malware["events"]) > 0
    assert len(exfil["events"]) > 0
    assert len(ransom["events"]) > 0


def test_brute_force_contains_ssh_signatures():
    mgr = CyberTrainingManager(auto_create_manager=False)
    exercise = mgr.create_exercise("brute_force")
    assert any("ssh" in event.description.lower() for event in exercise["events"])


def test_malware_contains_file_hash():
    mgr = CyberTrainingManager(auto_create_manager=False)
    exercise = mgr.create_exercise("malware")
    assert any("sha256" in event.raw_data for event in exercise["events"])


def test_run_exercise_through_soc_manager():
    soc = SOCManager()
    mgr = CyberTrainingManager(soc_manager=soc, auto_create_manager=False)
    exercise = mgr.create_exercise("brute_force")
    scorecard = mgr.run_exercise(exercise["events"][:5])
    assert scorecard["events_processed"] == 5
    assert "pipeline" in scorecard


def test_list_exercise_types():
    mgr = CyberTrainingManager(auto_create_manager=False)
    kinds = mgr.list_exercise_types()
    assert set(kinds) == {"brute_force", "malware", "data_exfil", "ransomware"}
