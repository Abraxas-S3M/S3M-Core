from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import pytest


_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "command" / "action_board.py"
_SPEC = spec_from_file_location("action_board_under_test", _MODULE_PATH)
_MODULE = module_from_spec(_SPEC)
assert _SPEC is not None and _SPEC.loader is not None
_SPEC.loader.exec_module(_MODULE)
ActionBoard = _MODULE.ActionBoard


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
