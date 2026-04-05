"""Tests for S3M Persistent Memory Architecture (Batch 1)."""

from src.memory.episodic_memory import EpisodicMemory, Episode
from src.memory.semantic_memory import SemanticMemory, Concept, ConceptLink
from src.memory.decision_journal import DecisionJournal, JournalEntry


def test_episodic_store_and_retrieve():
    memory = EpisodicMemory(capacity=100)
    episode = Episode(
        context="patrol mission sector alpha",
        tags=["patrol", "sector_alpha", "threat"],
        action_taken="hold",
        reward=0.8,
        importance=0.9,
    )
    memory.store(episode)
    assert memory.size() == 1
    results = memory.query(context="patrol sector", tags=["threat"], limit=5)
    assert len(results) >= 1
    assert results[0]["episode"]["action_taken"] == "hold"


def test_episodic_lru_eviction():
    memory = EpisodicMemory(capacity=100)
    for index in range(150):
        memory.store(Episode(context=f"event_{index}", importance=0.5))
    assert memory.size() == 100


def test_semantic_add_and_query():
    semantic = SemanticMemory()
    semantic.add_concept(
        Concept(
            concept_id="c1",
            name="T-72 Tank",
            category="vehicle",
            keywords=["tank", "armor", "t72", "tracked"],
            confidence=0.9,
        )
    )
    semantic.add_concept(
        Concept(
            concept_id="c2",
            name="BMP-2 IFV",
            category="vehicle",
            keywords=["ifv", "armor", "bmp", "tracked"],
            confidence=0.85,
        )
    )
    results = semantic.query(keywords=["tank", "armor"], limit=5)
    assert len(results) >= 1
    assert results[0]["concept"]["name"] == "T-72 Tank"


def test_semantic_graph_traversal():
    semantic = SemanticMemory()
    semantic.add_concept(Concept(concept_id="a", name="Radar", keywords=["radar", "sensor"]))
    semantic.add_concept(Concept(concept_id="b", name="SAM Site", keywords=["sam", "missile"]))
    semantic.add_concept(Concept(concept_id="c", name="Air Defense Network", keywords=["iads"]))
    semantic.add_link(ConceptLink(source_id="a", target_id="b", relation="feeds", strength=0.9))
    semantic.add_link(ConceptLink(source_id="b", target_id="c", relation="part_of", strength=0.8))

    related = semantic.get_related("a", depth=2)
    related_ids = [item["concept_id"] for item in related]
    assert "b" in related_ids
    assert "c" in related_ids


def test_decision_journal_record_and_query():
    journal = DecisionJournal(capacity=1000)
    entry = JournalEntry(
        decision_id="d-001",
        mission_id="m-alpha",
        selected_action="advance",
        confidence=0.75,
        utility_score=0.6,
        rationale_en="Best utility under current belief state.",
        rationale_ar="أفضل منفعة وفق حالة المعتقد الحالية.",
    )
    journal.record(entry)
    assert journal.size() == 1

    results = journal.query(mission_id="m-alpha")
    assert len(results) == 1
    assert results[0].selected_action == "advance"


def test_decision_journal_outcome_attachment():
    journal = DecisionJournal(capacity=1000)
    journal.record(JournalEntry(decision_id="d-100", selected_action="hold"))
    success = journal.attach_outcome("d-100", {"result": "mission_complete"}, reward=1.0)
    assert success is True
    entries = journal.query()
    assert entries[0].outcome_reward == 1.0


def test_decision_journal_pattern_analysis():
    journal = DecisionJournal()
    for index in range(20):
        journal.record(
            JournalEntry(
                decision_id=f"d-{index}",
                selected_action="hold" if index % 3 == 0 else "advance",
                confidence=0.5 + index * 0.02,
            )
        )
    patterns = journal.analyze_patterns(last_n=20)
    assert patterns["total"] == 20
    assert "advance" in patterns["action_distribution"]
    assert patterns["avg_confidence"] > 0.5
