from src.apps.drone_ops import ATRIntegrator, AutopilotBridge, DroneOpsModule, MissionPlanner


def test_mission_planner_plan_mission_returns_id_and_waypoints():
    planner = MissionPlanner()
    result = planner.plan_mission(
        {
            "mission_type": "PATROL",
            "waypoints": [(0, 0, 50), (200, 100, 50)],
            "num_agents": 1,
            "rules_of_engagement": "weapons_tight",
        }
    )
    assert "mission_id" in result
    assert isinstance(result["waypoints"], list)
    assert len(result["waypoints"]) >= 1


def test_autopilot_bridge_simulated_connects():
    bridge = AutopilotBridge(backend="simulated")
    assert bridge.connect()


def test_send_command_simulated_true():
    bridge = AutopilotBridge(backend="simulated")
    bridge.connect()
    assert bridge.send_command({"type": "MOVE_TO", "position": (100, 100, 40)})


def test_get_telemetry_shape():
    bridge = AutopilotBridge(backend="simulated")
    bridge.connect()
    telemetry = bridge.get_telemetry()
    assert "position" in telemetry
    assert "battery_pct" in telemetry


def test_atr_should_replan_for_high_detection():
    atr = ATRIntegrator()
    detections = [{"class": "tank", "confidence": 0.92, "threat_level": "HIGH"}]
    assert atr.should_replan(detections) is True


def test_drone_ops_health_check_keys():
    module = DroneOpsModule()
    health = module.health_check()
    assert "planner" in health
    assert "autopilot" in health
    assert "atr" in health
