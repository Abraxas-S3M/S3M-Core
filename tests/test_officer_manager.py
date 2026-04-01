from apps.simulation.training.officer_manager import OfficerManager


def test_register_and_get_officer():
    mgr = OfficerManager()
    officer = mgr.register_officer("A", "Captain", "Unit", "infantry")
    assert mgr.get_officer(officer.officer_id) is not None


def test_record_exercise_updates_average():
    mgr = OfficerManager()
    officer = mgr.register_officer("A", "Captain", "Unit", "infantry")
    mgr.record_exercise(officer.officer_id, "ex1", 80)
    assert mgr.get_officer(officer.officer_id).average_score == 80


def test_performance_trend_computed():
    mgr = OfficerManager()
    officer = mgr.register_officer("A", "Captain", "Unit", "infantry")
    mgr.record_wargame(officer.officer_id, "w1", 60)
    mgr.record_wargame(officer.officer_id, "w2", 70)
    mgr.record_wargame(officer.officer_id, "w3", 80)
    assert mgr.get_officer(officer.officer_id).performance_trend in {"improving", "stable", "declining"}


def test_get_leaderboard_sorted():
    mgr = OfficerManager()
    a = mgr.register_officer("A", "Captain", "Unit", "infantry")
    b = mgr.register_officer("B", "Captain", "Unit", "infantry")
    mgr.record_course(a.officer_id, "c1", 90)
    mgr.record_course(b.officer_id, "c1", 70)
    board = mgr.get_leaderboard()
    assert board[0]["average_score"] >= board[-1]["average_score"]


def test_readiness_score_computation():
    mgr = OfficerManager()
    officer = mgr.register_officer("A", "Captain", "Unit", "infantry")
    mgr.record_course(officer.officer_id, "c1", 85, certification="Cert")
    assert mgr.get_officer(officer.officer_id).readiness_score() >= 85
