"""Unit tests for durable queue and sync reconciler components."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.edge_runtime.durable_queue import DurableQueue, QueueItemState, SyncReconciler


def _queue_path(tmp_path) -> str:
    return str(tmp_path / "outbound_queue.db")


def test_enqueue_claim_order_and_attempt_tracking(tmp_path):
    queue = DurableQueue(db_path=_queue_path(tmp_path))
    try:
        low_id = queue.enqueue("status_low", {"seq": 1}, priority=5)
        high_id = queue.enqueue("status_high", {"seq": 2}, priority=0)

        batch = queue.claim_batch(limit=2)

        assert [item.item_id for item in batch] == [high_id, low_id]
        assert all(item.state == QueueItemState.IN_FLIGHT.value for item in batch)
        assert all(item.attempts == 1 for item in batch)
        assert all(item.last_attempt_at is not None for item in batch)
    finally:
        queue.close()


def test_ack_and_purge_delivered(tmp_path):
    queue = DurableQueue(db_path=_queue_path(tmp_path))
    try:
        item_id = queue.enqueue("health", {"ok": True})
        item = queue.claim_batch(limit=1)[0]
        assert item.item_id == item_id

        queue.ack(item_id)
        stats = queue.stats()
        assert stats[QueueItemState.DELIVERED.value] == 1

        purged = queue.purge_delivered()
        assert purged == 1
        assert queue.stats()[QueueItemState.DELIVERED.value] == 0
    finally:
        queue.close()


def test_nack_requeues_then_fails_when_retries_exhausted(tmp_path):
    queue = DurableQueue(db_path=_queue_path(tmp_path))
    try:
        item_id = queue.enqueue("retriable", {"payload": "x"}, max_retries=2)

        queue.claim_batch(limit=1)
        queue.nack(item_id)
        assert queue.stats()[QueueItemState.PENDING.value] == 1

        queue.claim_batch(limit=1)
        queue.nack(item_id)
        assert queue.stats()[QueueItemState.FAILED.value] == 1
        assert queue.stats()[QueueItemState.PENDING.value] == 0
    finally:
        queue.close()


def test_ttl_expiry_marks_stale_items_expired(tmp_path):
    queue = DurableQueue(db_path=_queue_path(tmp_path))
    try:
        item_id = queue.enqueue("sensor_frame", {"frame": 123}, ttl_seconds=5)
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        queue._conn.execute("UPDATE queue SET created_at=? WHERE item_id=?", (stale_time, item_id))
        queue._conn.commit()

        assert queue.pending_count() == 0
        assert queue.stats()[QueueItemState.EXPIRED.value] == 1
    finally:
        queue.close()


def test_persistence_across_restarts(tmp_path):
    db_path = _queue_path(tmp_path)
    q1 = DurableQueue(db_path=db_path)
    item_id = q1.enqueue("mission_log", {"entry": "hold"})
    q1.close()

    q2 = DurableQueue(db_path=db_path)
    try:
        assert q2.pending_count() == 1
        batch = q2.claim_batch(limit=1)
        assert len(batch) == 1
        assert batch[0].item_id == item_id
    finally:
        q2.close()


def test_sync_reconciler_mixed_delivery_outcomes(tmp_path):
    queue = DurableQueue(db_path=_queue_path(tmp_path))
    try:
        queue.enqueue("ok", {"id": 1})
        queue.enqueue("raise", {"id": 2})
        queue.enqueue("nope", {"id": 3})

        reconciler = SyncReconciler(queue=queue)

        def send_fn(item):
            if item.message_class == "ok":
                return True
            if item.message_class == "raise":
                raise RuntimeError("radio path down")
            return False

        result = reconciler.run_sync(send_fn=send_fn)

        assert result["attempted"] == 3
        assert result["delivered"] == 1
        assert result["failed"] == 2
        assert result["remaining_pending"] == 2
        assert len(reconciler.get_sync_log()) == 1
    finally:
        queue.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"message_class": "", "payload": {"x": 1}},
        {"message_class": "m", "payload": {"x": 1}, "priority": -1},
        {"message_class": "m", "payload": {"x": 1}, "max_retries": -1},
        {"message_class": "m", "payload": {"x": 1}, "ttl_seconds": -1},
        {"message_class": "m", "payload": "not json"},
    ],
)
def test_enqueue_input_validation(tmp_path, kwargs):
    queue = DurableQueue(db_path=_queue_path(tmp_path))
    try:
        with pytest.raises(ValueError):
            queue.enqueue(**kwargs)
    finally:
        queue.close()
