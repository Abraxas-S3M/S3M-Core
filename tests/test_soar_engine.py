"""Tests for Layer 07 SOAR engine and playbook execution."""

from __future__ import annotations

from services.cyber.models import CaseSeverity, IncidentCase, Playbook, PlaybookAction, PlaybookStep
from services.cyber.soar import PlaybookExecutor, PlaybookLibrary, SOAREngine


def _build_case() -> IncidentCase:
    return IncidentCase(
        title="SSH brute force incident",
        description="Repeated SSH brute force from 203.0.113.50",
        severity=CaseSeverity.HIGH,
        source_events=["evt-1"],
        observables=[
            {
                "observable_id": "obs-1",
                "observable_type": "IP_ADDRESS",
                "value": "203.0.113.50",
                "source_case_id": "pending",
                "tlp": "AMBER",
                "tags": [],
            }
        ],
        mitre_tactics=["TA0006"],
        mitre_techniques=["T1110"],
    )


def test_playbook_library_loads_yaml_playbook():
    library = PlaybookLibrary(playbooks_dir="configs/cyber/playbooks/")
    loaded = library.load_all()
    assert len(loaded) >= 1
    ids = {pb.playbook_id for pb in loaded}
    assert "PB-001" in ids


def test_playbook_library_match_playbook_for_t1110_case():
    library = PlaybookLibrary(playbooks_dir="configs/cyber/playbooks/")
    library.load_all()
    case = _build_case()
    playbook = library.match_playbook(case)
    assert playbook is not None
    assert playbook.playbook_id == "PB-001"


def test_playbook_executor_executes_steps_and_records_results():
    executor = PlaybookExecutor()
    case = _build_case()
    playbook = Playbook(
        playbook_id="PB-T",
        name="Test PB",
        description="test",
        trigger_conditions=[],
        steps=[
            PlaybookStep(step_id=1, name="notify", action=PlaybookAction.NOTIFY_ANALYST),
            PlaybookStep(step_id=2, name="llm", action=PlaybookAction.QUERY_LLM),
        ],
    )
    result = executor.execute(playbook, case)
    assert result["steps_executed"] == 2
    assert result["steps_succeeded"] == 2
    assert len(result["results"]) == 2


def test_playbook_executor_respects_step_conditions():
    executor = PlaybookExecutor()
    case = _build_case()
    playbook = Playbook(
        playbook_id="PB-COND",
        name="Conditional",
        description="cond",
        trigger_conditions=[],
        steps=[
            PlaybookStep(
                step_id=1,
                name="only_malicious",
                action=PlaybookAction.BLOCK_IP,
                condition="enrichment_verdict == malicious",
            )
        ],
    )
    result = executor.execute(playbook, case)
    assert result["steps_skipped"] == 1
    assert result["results"][0]["status"] == "skipped"


def test_playbook_executor_handles_failure_with_continue_policy():
    executor = PlaybookExecutor()
    case = _build_case()
    executor.ir_bridge.dfir_iris.add_evidence = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("forced failure"))
    playbook = Playbook(
        playbook_id="PB-F",
        name="FailThenContinue",
        description="failure handling",
        trigger_conditions=[],
        steps=[
            PlaybookStep(
                step_id=1,
                name="collect_forensics_missing_id",
                action=PlaybookAction.COLLECT_FORENSICS,
                parameters={},
                on_failure="continue",
            ),
            PlaybookStep(step_id=2, name="notify", action=PlaybookAction.NOTIFY_ANALYST),
        ],
    )
    result = executor.execute(playbook, case)
    assert result["steps_executed"] == 2
    assert result["steps_failed"] >= 1


def test_soar_engine_auto_respond_returns_result_without_match():
    engine = SOAREngine()
    case = IncidentCase(
        title="Unknown incident",
        description="No known pattern",
        severity=CaseSeverity.LOW,
        source_events=["evt-x"],
        mitre_techniques=["T9999"],
    )
    result = engine.auto_respond(case)
    assert "mode" in result
