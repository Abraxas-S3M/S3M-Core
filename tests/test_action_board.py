from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from src.api.server import app
from src.command.action_board import ActionBoard


@pytest.fixture(autouse=True)
def clear_action_board_store():
    ActionBoard._tasks.clear()
    yield
    ActionBoard._tasks.clear()


def test_action_board_prioritization_formula():
    board = ActionBoard()
    item = board.add_task(
        title="Re-task ISR orbit",
        urgency=5,
        impact=4,
        assignee="OPS-ALPHA",
    )
    ActionBoard._tasks[item.id].created_at = datetime.now(timezone.utc) - timedelta(hours=10)

    prioritized = board.get_prioritized()
    assert len(prioritized) == 1
    score = prioritized[0].urgencyScore
    assert score == pytest.approx((5 * 2.0) + (4 * 1.5) + (10 * 0.1), rel=1e-3)


def test_action_board_update_and_filter():
    board = ActionBoard()
    first = board.add_task(title="Harden relay node", urgency=4, impact=4)
    board.add_task(title="Archive patrol logs", urgency=1, impact=1, status="complete")

    updated = board.update_task(first.id, status="active", linked_decision_id="R003")
    assert updated is not None
    assert updated.status == "active"
    assert updated.linkedDecisionId == "R003"

    active = board.get_tasks(status_filter="active")
    assert len(active) == 1
    assert active[0].id == first.id


def test_action_board_routes_create_get_patch():
    client = TestClient(app)
    base = "/api/v1/workspaces/command/action-board"

    create = client.post(
        base,
        json={
            "title": "Shift QRF to corridor Echo",
            "urgency": 5,
            "impact": 5,
            "assignee": "QRF-1",
            "status": "pending",
            "linkedDecisionId": "R001",
        },
    )
    assert create.status_code == 200
    created = create.json()
    assert created["title"] == "Shift QRF to corridor Echo"
    assert "urgencyScore" in created

    listing = client.get(base)
    assert listing.status_code == 200
    payload = listing.json()
    assert isinstance(payload, list)
    assert payload[0]["id"] == created["id"]

    patch = client.patch(
        f"{base}/{created['id']}",
        json={"status": "active", "assignee": "QRF-2"},
    )
    assert patch.status_code == 200
    patched = patch.json()
    assert patched["status"] == "active"
    assert patched["assignee"] == "QRF-2"
