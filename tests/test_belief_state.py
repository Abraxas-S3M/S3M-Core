"""Unit tests for the belief-state runtime models and store."""

from __future__ import annotations

import json
import math
import threading
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.belief_state import (
    AuditEntry,
    BeliefHypothesis,
    BeliefState,
    BeliefStore,
    BeliefUpdate,
    DoctrineContext,
    EntityRef,
    EvidenceLink,
    MergeConflict,
    UncertaintyMetrics,
)
from src.belief_state.models import (
    DoctrineType,
    EvidenceLayer,
    HypothesisStatus,
    UpdateSource,
)


def _make_evidence(confidence: float = 0.8) -> EvidenceLink:
    return EvidenceLink(
        layer=EvidenceLayer.OPERATOR,
        description="Operator observation",
        confidence=confidence,
    )


def _make_hypothesis(
    description: str = "Hostile intent detected",
    probability: float = 0.5,
    status: HypothesisStatus = HypothesisStatus.ACTIVE,
) -> BeliefHypothesis:
    return BeliefHypothesis(description=description, probability=probability, status=status)


def _make_state_with_two_hypotheses() -> tuple[BeliefState, str, str]:
    hyp_a = _make_hypothesis(description="A", probability=0.7)
    hyp_b = _make_hypothesis(description="B", probability=0.3)
    a_id = str(hyp_a.hypothesis_id)
    b_id = str(hyp_b.hypothesis_id)
    state = BeliefState(
        hypotheses={a_id: hyp_a, b_id: hyp_b},
        confidence_distribution={a_id: 0.7, b_id: 0.3},
        uncertainty_metrics=UncertaintyMetrics(epistemic_uncertainty=0.3, entropy=0.61),
    )
    return state, a_id, b_id


class TestBeliefHypothesis:
    def test_auto_uuid(self):
        h1 = _make_hypothesis()
        h2 = _make_hypothesis()
        assert h1.hypothesis_id != h2.hypothesis_id

    def test_blank_description_rejected(self):
        with pytest.raises(ValidationError):
            BeliefHypothesis(description="   ", probability=0.5)

    def test_probability_bounds(self):
        with pytest.raises(ValidationError):
            BeliefHypothesis(description="too high", probability=1.1)
        with pytest.raises(ValidationError):
            BeliefHypothesis(description="too low", probability=-0.1)

    def test_net_evidence_weight_positive(self):
        hyp = BeliefHypothesis(
            description="weighted",
            probability=0.6,
            supporting_evidence=[_make_evidence(0.9), _make_evidence(0.3)],
            conflicting_evidence=[_make_evidence(0.4)],
        )
        assert hyp.net_evidence_weight == pytest.approx(0.8)

    def test_evidence_count(self):
        hyp = BeliefHypothesis(
            description="count",
            probability=0.5,
            supporting_evidence=[_make_evidence(0.4)],
            conflicting_evidence=[_make_evidence(0.2), _make_evidence(0.1)],
        )
        assert hyp.evidence_count == 3

    def test_arabic_description_optional(self):
        hyp = BeliefHypothesis(
            description="English",
            description_ar="وصف",
            probability=0.5,
        )
        assert hyp.description_ar == "وصف"


class TestBeliefUpdate:
    def test_is_frozen(self):
        update = BeliefUpdate(source=UpdateSource.OPERATOR_INPUT)
        with pytest.raises(ValidationError):
            update.source = UpdateSource.LLM_ASSESSMENT

    def test_delta_out_of_bounds_rejected(self):
        with pytest.raises(ValidationError):
            BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={"a": 1.5})
        with pytest.raises(ValidationError):
            BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={"a": -1.5})

    def test_valid_delta_accepted(self):
        update = BeliefUpdate(
            source=UpdateSource.SECURITY_RUNTIME,
            delta={"x": 1.0, "y": -1.0, "z": 0.0},
        )
        assert update.delta["x"] == 1.0
        assert update.delta["y"] == -1.0

    def test_auto_uuid(self):
        u1 = BeliefUpdate(source=UpdateSource.OPERATOR_INPUT)
        u2 = BeliefUpdate(source=UpdateSource.OPERATOR_INPUT)
        assert u1.update_id != u2.update_id

    def test_arabic_justification(self):
        update = BeliefUpdate(
            source=UpdateSource.OPERATOR_INPUT,
            justification_ar="مبرر تشغيلي",
        )
        assert update.justification_ar == "مبرر تشغيلي"


class TestBeliefState:
    def test_is_frozen(self):
        state = BeliefState()
        with pytest.raises(ValidationError):
            state.version = 99

    def test_distribution_must_sum_to_one(self):
        hyp = _make_hypothesis(probability=0.4)
        hyp_id = str(hyp.hypothesis_id)
        with pytest.raises(ValidationError):
            BeliefState(
                hypotheses={hyp_id: hyp},
                confidence_distribution={hyp_id: 0.4},
            )

    def test_empty_distribution_is_valid(self):
        state = BeliefState()
        assert state.confidence_distribution == {}

    def test_distribution_keys_must_exist_in_hypotheses(self):
        with pytest.raises(ValidationError):
            BeliefState(
                hypotheses={},
                confidence_distribution={str(uuid4()): 1.0},
            )

    def test_leading_hypothesis_returns_highest_prob(self):
        state, a_id, _ = _make_state_with_two_hypotheses()
        leading = state.leading_hypothesis()
        assert leading is not None
        assert str(leading.hypothesis_id) == a_id

    def test_leading_hypothesis_none_when_empty(self):
        state = BeliefState()
        assert state.leading_hypothesis() is None

    def test_active_hypotheses_sorted_desc(self):
        hyp_1 = _make_hypothesis(description="low", probability=0.2)
        hyp_2 = _make_hypothesis(description="high", probability=0.9)
        hyp_3 = _make_hypothesis(
            description="retired",
            probability=0.8,
            status=HypothesisStatus.REFUTED,
        )
        state = BeliefState(
            hypotheses={
                str(hyp_1.hypothesis_id): hyp_1,
                str(hyp_2.hypothesis_id): hyp_2,
                str(hyp_3.hypothesis_id): hyp_3,
            },
            confidence_distribution={
                str(hyp_1.hypothesis_id): 0.2,
                str(hyp_2.hypothesis_id): 0.8,
            },
        )
        active = state.active_hypotheses()
        assert [item.description for item in active] == ["high", "low"]

    def test_entropy_uniform(self):
        hypotheses = {}
        distribution = {}
        for idx in range(4):
            hyp = _make_hypothesis(description=f"h{idx}", probability=0.25)
            hyp_id = str(hyp.hypothesis_id)
            hypotheses[hyp_id] = hyp
            distribution[hyp_id] = 0.25
        state = BeliefState(
            hypotheses=hypotheses,
            confidence_distribution=distribution,
        )
        assert state.entropy() == pytest.approx(math.log(4.0))

    def test_entropy_certain(self):
        hyp = _make_hypothesis(probability=1.0)
        hyp_id = str(hyp.hypothesis_id)
        state = BeliefState(
            hypotheses={hyp_id: hyp},
            confidence_distribution={hyp_id: 1.0},
        )
        assert state.entropy() == pytest.approx(0.0)

    def test_diff_detects_added_hypothesis(self):
        base = BeliefState()
        added = _make_hypothesis(description="new", probability=1.0)
        added_id = str(added.hypothesis_id)
        newer = BeliefState(
            hypotheses={added_id: added},
            confidence_distribution={added_id: 1.0},
        )
        diff = base.diff(newer)
        assert diff["hypotheses_added"] == [added_id]

    def test_diff_detects_entity_change(self):
        entity = EntityRef(label="Tracked target")
        entity_id = str(entity.entity_id)
        base = BeliefState(entities={entity_id: entity})
        changed = entity.model_copy(update={"label": "Tracked target updated"})
        newer = BeliefState(entities={entity_id: changed})
        diff = base.diff(newer)
        assert diff["entities_changed"] == [entity_id]


class TestBeliefStoreCreate:
    def test_create_increments_version(self):
        store = BeliefStore()
        assert store.current().version == 0
        state = store.create(hypotheses=[_make_hypothesis(description="h1", probability=0.3)])
        assert state.version == 1

    def test_create_distribution_normalised(self):
        store = BeliefStore()
        h1 = _make_hypothesis(description="h1", probability=0.2)
        h2 = _make_hypothesis(description="h2", probability=0.2)
        state = store.create(hypotheses=[h1, h2])
        assert sum(state.confidence_distribution.values()) == pytest.approx(1.0)

    def test_create_requires_hypotheses(self):
        store = BeliefStore()
        with pytest.raises(ValueError):
            store.create(hypotheses=[])

    def test_create_with_entities_and_doctrine(self):
        store = BeliefStore()
        entity = EntityRef(label="Asset Alpha")
        doctrine = DoctrineContext(
            doctrine_type=DoctrineType.CONVENTIONAL,
            mission_label="Mission X",
        )
        state = store.create(
            hypotheses=[_make_hypothesis(description="h", probability=1.0)],
            entities=[entity],
            doctrine=doctrine,
        )
        assert str(entity.entity_id) in state.entities
        assert state.doctrine_context.mission_label == "Mission X"

    def test_create_audit_entry_written(self):
        store = BeliefStore()
        store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        audit = store.audit_log()
        assert len(audit) == 1
        assert isinstance(audit[0], AuditEntry)

    def test_create_with_arabic_mission_label(self):
        store = BeliefStore()
        doctrine = DoctrineContext(mission_label="Mission", mission_label_ar="مهمة")
        state = store.create(
            hypotheses=[_make_hypothesis(description="h", probability=1.0)],
            doctrine=doctrine,
        )
        assert state.doctrine_context.mission_label_ar == "مهمة"


class TestBeliefStoreApply:
    def test_apply_increases_version(self):
        store = BeliefStore()
        base = store.create(hypotheses=[_make_hypothesis(description="h1", probability=1.0)])
        hyp_id = next(iter(base.hypotheses))
        update = BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: -0.1})
        state = store.apply(update)
        assert state.version == base.version + 1

    def test_apply_shifts_probability(self):
        store = BeliefStore()
        h1 = _make_hypothesis(description="h1", probability=0.8)
        h2 = _make_hypothesis(description="h2", probability=0.2)
        state = store.create(hypotheses=[h1, h2])
        h1_id = str(h1.hypothesis_id)
        update = BeliefUpdate(source=UpdateSource.REPLAN_ENGINE, delta={h1_id: -0.5})
        next_state = store.apply(update)
        assert next_state.confidence_distribution[h1_id] < state.confidence_distribution[h1_id]

    def test_apply_distribution_stays_normalised(self):
        store = BeliefStore()
        h1 = _make_hypothesis(description="h1", probability=0.6)
        h2 = _make_hypothesis(description="h2", probability=0.4)
        state = store.create(hypotheses=[h1, h2])
        h1_id = str(h1.hypothesis_id)
        for _ in range(10):
            state = store.apply(
                BeliefUpdate(source=UpdateSource.SECURITY_RUNTIME, delta={h1_id: 0.1})
            )
            assert sum(state.confidence_distribution.values()) == pytest.approx(1.0)

    def test_apply_adds_new_hypothesis(self):
        store = BeliefStore()
        store.create(hypotheses=[_make_hypothesis(description="base", probability=1.0)])
        new_h = _make_hypothesis(description="new", probability=0.4)
        state = store.apply(
            BeliefUpdate(
                source=UpdateSource.DECISION_ENGINE,
                new_hypotheses=[new_h],
            )
        )
        assert str(new_h.hypothesis_id) in state.hypotheses

    def test_apply_retires_hypothesis(self):
        store = BeliefStore()
        h1 = _make_hypothesis(description="to retire", probability=1.0)
        store.create(hypotheses=[h1])
        h1_id = str(h1.hypothesis_id)
        state = store.apply(
            BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, retired_ids=[h1_id])
        )
        assert state.hypotheses[h1_id].status == HypothesisStatus.REFUTED
        assert h1_id not in state.confidence_distribution

    def test_apply_adds_entity(self):
        store = BeliefStore()
        store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        entity = EntityRef(label="Unit Bravo")
        state = store.apply(
            BeliefUpdate(source=UpdateSource.SENSOR_FUSION, entity_updates=[entity])
        )
        assert str(entity.entity_id) in state.entities

    def test_apply_updates_doctrine(self):
        store = BeliefStore()
        store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        doctrine = DoctrineContext(mission_label="Updated", escalation_level=2)
        state = store.apply(
            BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, doctrine_update=doctrine)
        )
        assert state.doctrine_context.mission_label == "Updated"
        assert state.doctrine_context.escalation_level == 2

    def test_apply_audit_entry_contains_update_id(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        hyp_id = next(iter(created.hypotheses))
        update = BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: 0.0})
        store.apply(update)
        assert str(update.update_id) in store.audit_log()[-1].update_ids

    def test_apply_unknown_delta_key_ignored(self):
        store = BeliefStore()
        state = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        before = dict(state.confidence_distribution)
        after = store.apply(
            BeliefUpdate(source=UpdateSource.SECURITY_RUNTIME, delta={"missing": 0.5})
        )
        assert after.confidence_distribution == before

    def test_apply_preserves_history(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        hyp_id = next(iter(created.hypotheses))
        store.apply(BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: 0.0}))
        store.apply(BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: 0.0}))
        versions = [snapshot.version for snapshot in store.history(n=10)]
        assert versions == [0, 1, 2, 3]


class TestBeliefStoreMerge:
    def test_merge_single_update(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        hyp_id = next(iter(created.hypotheses))
        update = BeliefUpdate(source=UpdateSource.MERGE_RESOLUTION, delta={hyp_id: -0.2})
        merged = store.merge([update])
        assert merged.version == created.version + 1

    def test_merge_two_consistent_updates(self):
        store = BeliefStore()
        h1 = _make_hypothesis(description="h1", probability=0.7)
        h2 = _make_hypothesis(description="h2", probability=0.3)
        created = store.create(hypotheses=[h1, h2])
        h1_id = str(h1.hypothesis_id)
        u1 = BeliefUpdate(source=UpdateSource.MERGE_RESOLUTION, delta={h1_id: 0.1})
        u2 = BeliefUpdate(source=UpdateSource.MERGE_RESOLUTION, delta={h1_id: 0.05})
        merged = store.merge([u1, u2])
        assert merged.version == created.version + 1

    def test_merge_conflict_detected_average(self):
        store = BeliefStore(conflict_threshold=0.15)
        h1 = _make_hypothesis(description="h1", probability=1.0)
        store.create(hypotheses=[h1])
        h1_id = str(h1.hypothesis_id)
        u1 = BeliefUpdate(source=UpdateSource.MERGE_RESOLUTION, delta={h1_id: 0.5})
        u2 = BeliefUpdate(source=UpdateSource.MERGE_RESOLUTION, delta={h1_id: -0.5})
        store.merge([u1, u2], strategy=BeliefStore.RESOLVE_AVERAGE)
        conflicts = store.conflicts()
        assert conflicts
        assert isinstance(conflicts[-1], MergeConflict)
        assert conflicts[-1].resolved_delta == pytest.approx(0.0)

    def test_merge_conflict_resolved_max(self):
        store = BeliefStore(conflict_threshold=0.15)
        h1 = _make_hypothesis(description="h1", probability=1.0)
        store.create(hypotheses=[h1])
        h1_id = str(h1.hypothesis_id)
        u1 = BeliefUpdate(source=UpdateSource.MERGE_RESOLUTION, delta={h1_id: 0.7})
        u2 = BeliefUpdate(source=UpdateSource.MERGE_RESOLUTION, delta={h1_id: -0.4})
        store.merge([u1, u2], strategy=BeliefStore.RESOLVE_MAX)
        assert store.conflicts()[-1].resolved_delta == pytest.approx(0.7)

    def test_merge_distribution_normalised_after(self):
        store = BeliefStore()
        h1 = _make_hypothesis(description="h1", probability=0.5)
        h2 = _make_hypothesis(description="h2", probability=0.5)
        store.create(hypotheses=[h1, h2])
        h1_id = str(h1.hypothesis_id)
        u1 = BeliefUpdate(source=UpdateSource.MERGE_RESOLUTION, delta={h1_id: 0.8})
        u2 = BeliefUpdate(source=UpdateSource.MERGE_RESOLUTION, delta={h1_id: -0.2})
        merged = store.merge([u1, u2])
        assert sum(merged.confidence_distribution.values()) == pytest.approx(1.0)

    def test_merge_empty_raises(self):
        store = BeliefStore()
        with pytest.raises(ValueError):
            store.merge([])


class TestBeliefStoreHistory:
    def test_history_preserved_across_applies(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        hyp_id = next(iter(created.hypotheses))
        for _ in range(3):
            store.apply(BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: 0.0}))
        versions = [snapshot.version for snapshot in store.history(n=10)]
        assert versions == [0, 1, 2, 3, 4]

    def test_get_version_returns_correct_snapshot(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        fetched = store.get_version(created.version)
        assert fetched is not None
        assert fetched.version == created.version

    def test_get_version_none_for_unknown(self):
        store = BeliefStore()
        assert store.get_version(9999) is None

    def test_rolling_window_respected(self):
        store = BeliefStore(max_history=5)
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        hyp_id = next(iter(created.hypotheses))
        for _ in range(10):
            store.apply(BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: 0.0}))
        history = store.history(n=20)
        assert len(history) == 5
        assert [s.version for s in history] == [7, 8, 9, 10, 11]

    def test_past_snapshots_immutable(self):
        store = BeliefStore()
        snap = store.current()
        with pytest.raises(ValidationError):
            snap.version = 42


class TestBeliefStoreAudit:
    def test_every_apply_produces_audit_entry(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        hyp_id = next(iter(created.hypotheses))
        store.apply(BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: 0.0}))
        store.apply(BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: 0.0}))
        assert len(store.audit_log()) == 3

    def test_audit_entry_hypothesis_delta_populated(self):
        store = BeliefStore()
        store.create(hypotheses=[_make_hypothesis(description="base", probability=1.0)])
        new_h = _make_hypothesis(description="added", probability=0.2)
        store.apply(
            BeliefUpdate(source=UpdateSource.DECISION_ENGINE, new_hypotheses=[new_h])
        )
        latest = store.audit_log()[-1]
        assert latest.hypothesis_delta[str(new_h.hypothesis_id)] == "ADDED"

    def test_audit_entry_retired_delta(self):
        store = BeliefStore()
        h1 = _make_hypothesis(description="retire", probability=1.0)
        store.create(hypotheses=[h1])
        h1_id = str(h1.hypothesis_id)
        store.apply(BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, retired_ids=[h1_id]))
        latest = store.audit_log()[-1]
        assert latest.hypothesis_delta[h1_id] == "CHANGED"

    def test_audit_chain_parent_version_links(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        hyp_id = next(iter(created.hypotheses))
        applied = store.apply(BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: 0.0}))
        assert applied.parent_version == created.version

    def test_export_audit_json_parseable(self):
        store = BeliefStore()
        store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        payload = store.export_audit_json(n=10)
        parsed = json.loads(payload)
        assert isinstance(parsed, list)
        assert parsed[0]["to_version"] == 1


class TestNormalisation:
    def test_collapsed_distribution_restored_uniform(self):
        store = BeliefStore()
        h1 = _make_hypothesis(description="h1", probability=0.5)
        h2 = _make_hypothesis(description="h2", probability=0.5)
        store.create(hypotheses=[h1, h2])
        h1_id = str(h1.hypothesis_id)
        h2_id = str(h2.hypothesis_id)
        state = store.apply(
            BeliefUpdate(
                source=UpdateSource.OPERATOR_INPUT,
                delta={h1_id: -1.0, h2_id: -1.0},
            )
        )
        assert state.confidence_distribution[h1_id] == pytest.approx(0.5)
        assert state.confidence_distribution[h2_id] == pytest.approx(0.5)

    def test_retiring_all_hypotheses_empties_distribution(self):
        store = BeliefStore()
        h1 = _make_hypothesis(description="h1", probability=0.5)
        h2 = _make_hypothesis(description="h2", probability=0.5)
        store.create(hypotheses=[h1, h2])
        state = store.apply(
            BeliefUpdate(
                source=UpdateSource.OPERATOR_INPUT,
                retired_ids=[str(h1.hypothesis_id), str(h2.hypothesis_id)],
            )
        )
        assert state.confidence_distribution == {}


class TestConcurrency:
    def test_50_concurrent_applies_version_increments_correctly(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        hyp_id = next(iter(created.hypotheses))
        start_version = store.current().version
        errors: list[Exception] = []

        def worker() -> None:
            try:
                store.apply(BeliefUpdate(source=UpdateSource.SENSOR_FUSION, delta={hyp_id: 0.0}))
            except Exception as exc:  # pragma: no cover - defensive in threaded test
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert store.current().version == start_version + 50

    def test_concurrent_creates_and_applies(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="base", probability=1.0)])
        base_hyp_id = next(iter(created.hypotheses))
        start_version = store.current().version
        errors: list[Exception] = []

        def create_worker(index: int) -> None:
            try:
                store.create(
                    hypotheses=[_make_hypothesis(description=f"c{index}", probability=0.3)],
                    author="creator",
                )
            except Exception as exc:  # pragma: no cover - defensive in threaded test
                errors.append(exc)

        def apply_worker() -> None:
            try:
                store.apply(
                    BeliefUpdate(
                        source=UpdateSource.SENSOR_FUSION,
                        delta={base_hyp_id: 0.0},
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive in threaded test
                errors.append(exc)

        threads = [threading.Thread(target=create_worker, args=(idx,)) for idx in range(10)]
        threads.extend(threading.Thread(target=apply_worker) for _ in range(10))

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert store.current().version == start_version + 20


class TestSubscriber:
    def test_subscriber_called_after_apply(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        hyp_id = next(iter(created.hypotheses))
        calls: list[BeliefState] = []
        store.subscribe(lambda state: calls.append(state))
        store.apply(BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: 0.0}))
        assert len(calls) == 1

    def test_subscriber_receives_correct_version(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        hyp_id = next(iter(created.hypotheses))
        versions: list[int] = []
        store.subscribe(lambda state: versions.append(state.version))
        state = store.apply(BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: 0.0}))
        assert versions[-1] == state.version

    def test_faulty_subscriber_does_not_crash_store(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        hyp_id = next(iter(created.hypotheses))

        def faulty(_: BeliefState) -> None:
            raise RuntimeError("fault")

        store.subscribe(faulty)
        state = store.apply(BeliefUpdate(source=UpdateSource.OPERATOR_INPUT, delta={hyp_id: 0.0}))
        assert state.version == 2


class TestJsonExport:
    def test_export_current_json_valid(self):
        store = BeliefStore()
        store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        payload = store.export_json()
        parsed = json.loads(payload)
        assert parsed["version"] == 1

    def test_export_specific_version(self):
        store = BeliefStore()
        created = store.create(hypotheses=[_make_hypothesis(description="h", probability=1.0)])
        payload = store.export_json(version=created.version)
        parsed = json.loads(payload)
        assert parsed["version"] == created.version

    def test_export_unknown_version_raises(self):
        store = BeliefStore()
        with pytest.raises(KeyError):
            store.export_json(version=777)

    def test_distribution_in_export_sums_to_one(self):
        store = BeliefStore()
        h1 = _make_hypothesis(description="h1", probability=0.2)
        h2 = _make_hypothesis(description="h2", probability=0.8)
        store.create(hypotheses=[h1, h2])
        parsed = json.loads(store.export_json())
        total = sum(parsed["confidence_distribution"].values())
        assert total == pytest.approx(1.0)
