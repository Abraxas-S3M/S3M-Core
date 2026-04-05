"""Tests for offline survival cognition helper."""

from src.edge_runtime.offline_brain import OfflineBrain


def test_offline_brain_activation_and_snapshot() -> None:
    brain = OfflineBrain()
    brain.activate("link_loss")
    snap = brain.snapshot()
    assert snap["active"] is True
    assert snap["last_reason"] == "link_loss"
    assert isinstance(snap["activated_at"], str)


def test_offline_brain_intent_queue_bounds() -> None:
    brain = OfflineBrain()
    for idx in range(300):
        brain.enqueue_intent(f"intent-{idx}")
    snap = brain.snapshot()
    assert len(snap["queued_intents"]) == 256
    assert snap["queued_intents"][0] == "intent-44"
    assert snap["queued_intents"][-1] == "intent-299"
