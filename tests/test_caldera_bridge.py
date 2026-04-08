from services.cyber.offensive.caldera_bridge import CalderaBridge


def test_create_operation_requires_approval_token():
    bridge = CalderaBridge()
    try:
        bridge.create_operation("sim-red-team-phishing", ["edge-1"], approval_token="")
        assert False, "Expected ValueError when approval token is missing"
    except ValueError as exc:
        assert "approval_token" in str(exc)


def test_create_operation_simulated_when_caldera_unavailable(monkeypatch):
    bridge = CalderaBridge()
    monkeypatch.setattr(bridge, "_is_caldera_available", lambda: False)

    operation_id = bridge.create_operation(
        adversary_id="sim-red-team-phishing",
        targets=["edge-node-1"],
        approval_token="ops-approved",
    )
    assert operation_id.startswith("sim-op-")

    status = bridge.get_operation_status(operation_id)
    assert "steps_completed" in status
    assert "techniques_used" in status
    assert isinstance(status["techniques_used"], list)


def test_list_adversary_profiles_fallback_when_caldera_unavailable(monkeypatch):
    bridge = CalderaBridge()
    monkeypatch.setattr(bridge, "_is_caldera_available", lambda: False)
    profiles = bridge.list_adversary_profiles()
    assert isinstance(profiles, list)
    assert profiles
    assert "adversary_id" in profiles[0]

