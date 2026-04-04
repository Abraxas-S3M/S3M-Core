"""Tests for S3M Phase 21 austere edge runtime.
UNCLASSIFIED - FOUO
"""

import pytest

from src.edge_runtime.bearer_broker import BearerBroker, LinkMetrics, LinkState, LinkType, MessageClass
from src.edge_runtime.degradation_controller import MODE_POLICIES, DegradationController, OperatingMode
from src.edge_runtime.durable_queue import DurableQueue, SyncReconciler
from src.edge_runtime.hardware_profiler import HardwareProfiler, HardwareTier, NodeProfile
from src.edge_runtime.health_surface import OperatorHealthSurface
from src.edge_runtime.model_planner import DEFAULT_VARIANTS, ExecutionDecision, ModelExecutionPlanner


@pytest.fixture
def cpu_austere_profile() -> NodeProfile:
    return NodeProfile(
        tier=HardwareTier.CPU_AUSTERE,
        cpu_cores=4,
        cpu_arch="aarch64",
        ram_total_gb=8.0,
        ram_available_gb=5.0,
        disk_total_gb=64.0,
        disk_free_gb=30.0,
        gpu_detected=False,
        gpu_name=None,
        gpu_memory_mb=0,
        cuda_available=False,
        thermal_zone_c=55.0,
        power_source="battery",
        active_links=["eth0"],
    )


@pytest.fixture
def edge_gpu_profile() -> NodeProfile:
    return NodeProfile(
        tier=HardwareTier.EDGE_GPU,
        cpu_cores=8,
        cpu_arch="aarch64",
        ram_total_gb=32.0,
        ram_available_gb=20.0,
        disk_total_gb=256.0,
        disk_free_gb=100.0,
        gpu_detected=True,
        gpu_name="Orin",
        gpu_memory_mb=32768,
        cuda_available=True,
        thermal_zone_c=60.0,
        power_source="mains",
        active_links=["eth0", "wlan0"],
    )


@pytest.fixture
def queue_db(tmp_path):
    db_path = str(tmp_path / "test_queue.db")
    queue = DurableQueue(db_path=db_path)
    yield queue
    queue.close()


class TestHardwareProfiler:
    def test_run_returns_node_profile(self) -> None:
        profiler = HardwareProfiler()
        profile = profiler.run()
        assert isinstance(profile, NodeProfile)
        assert profile.cpu_cores >= 1
        assert profile.tier in HardwareTier

    def test_to_dict(self) -> None:
        profiler = HardwareProfiler()
        profile = profiler.run()
        payload = profile.to_dict()
        assert "tier" in payload
        assert "cpu_cores" in payload
        assert "gpu_detected" in payload

    def test_classify_cpu_austere(self) -> None:
        tier = HardwareProfiler._classify(cores=2, ram_gb=4.0, gpu=False, thermal=None, power="battery")
        assert tier == HardwareTier.CPU_AUSTERE

    def test_classify_edge_gpu(self) -> None:
        tier = HardwareProfiler._classify(cores=8, ram_gb=32.0, gpu=True, thermal=60.0, power="mains")
        assert tier == HardwareTier.EDGE_GPU

    def test_classify_vehicle(self) -> None:
        tier = HardwareProfiler._classify(cores=8, ram_gb=32.0, gpu=True, thermal=70.0, power="vehicle")
        assert tier == HardwareTier.VEHICLE_NODE


class TestDegradationController:
    def test_initial_mode_cpu_austere(self, cpu_austere_profile: NodeProfile) -> None:
        controller = DegradationController(cpu_austere_profile)
        assert controller.current_mode == OperatingMode.MODE_B_CPU_CONSTRAINED

    def test_initial_mode_full_edge(self, edge_gpu_profile: NodeProfile) -> None:
        controller = DegradationController(edge_gpu_profile)
        assert controller.current_mode == OperatingMode.MODE_A_FULL_EDGE

    def test_initial_mode_offline_no_links(self, edge_gpu_profile: NodeProfile) -> None:
        edge_gpu_profile.active_links = []
        controller = DegradationController(edge_gpu_profile)
        assert controller.current_mode == OperatingMode.MODE_D_OFFLINE_SURVIVAL

    def test_force_mode(self, edge_gpu_profile: NodeProfile) -> None:
        controller = DegradationController(edge_gpu_profile)
        controller.force_mode(OperatingMode.MODE_D_OFFLINE_SURVIVAL, "test")
        assert controller.current_mode == OperatingMode.MODE_D_OFFLINE_SURVIVAL
        assert len(controller.get_transition_log()) >= 1

    def test_policy_constraints(self) -> None:
        policy_a = MODE_POLICIES[OperatingMode.MODE_A_FULL_EDGE]
        policy_d = MODE_POLICIES[OperatingMode.MODE_D_OFFLINE_SURVIVAL]
        assert policy_a.max_concurrent_models > policy_d.max_concurrent_models
        assert policy_a.allow_gpu is True
        assert policy_d.allow_gpu is False
        assert policy_d.queue_outbound is True

    def test_subscriber_notified(self, edge_gpu_profile: NodeProfile) -> None:
        controller = DegradationController(edge_gpu_profile)
        notifications = []
        controller.subscribe(lambda mode, policy: notifications.append(mode))
        controller.force_mode(OperatingMode.MODE_C_INTERMITTENT_LINK, "test")
        assert len(notifications) == 1
        assert notifications[0] == OperatingMode.MODE_C_INTERMITTENT_LINK

    def test_service_tiers(self) -> None:
        tiers = DegradationController.service_tiers()
        assert tiers["llm_inference_q4"]["tier"] == 0
        assert tiers["llm_inference_q4"]["cpu_safe"] is True
        assert tiers["simulation_engine"]["tier"] == 2
        assert tiers["adapter_finetune_small"]["cpu_safe"] is True
        assert tiers["classifier_retrain"]["max_memory_mb"] == 1024
        assert tiers["knowledge_distillation"]["tier"] == 1
        assert tiers["federated_adapter_merge"]["offline_safe"] is False
        assert tiers["full_model_finetune_large"]["tier"] == 2
        assert tiers["model_fine_tune"]["deprecated_alias_for"] == "full_model_finetune_large"
        assert tiers["model_fine_tune"]["max_memory_mb"] == tiers["full_model_finetune_large"]["max_memory_mb"]


class TestModelPlanner:
    def test_plan_phi3_on_cpu_austere(self, cpu_austere_profile: NodeProfile) -> None:
        controller = DegradationController(cpu_austere_profile)
        planner = ModelExecutionPlanner(cpu_austere_profile, controller)
        plan = planner.plan("phi3-mini")
        assert plan.decision == ExecutionDecision.RUN_LOCAL
        assert plan.variant is not None
        assert plan.variant.requires_gpu is False
        assert plan.max_tokens <= 512

    def test_plan_unknown_model_rejected(self, cpu_austere_profile: NodeProfile) -> None:
        controller = DegradationController(cpu_austere_profile)
        planner = ModelExecutionPlanner(cpu_austere_profile, controller)
        plan = planner.plan("nonexistent-model")
        assert plan.decision == ExecutionDecision.REJECT

    def test_plan_offline_survival_limits(self, cpu_austere_profile: NodeProfile) -> None:
        controller = DegradationController(cpu_austere_profile)
        controller.force_mode(OperatingMode.MODE_D_OFFLINE_SURVIVAL, "test")
        planner = ModelExecutionPlanner(cpu_austere_profile, controller)
        plan = planner.plan("phi3-mini", requested_tokens=2048)
        assert plan.max_tokens <= 256
        assert plan.max_context <= 2048

    def test_plan_to_dict(self, cpu_austere_profile: NodeProfile) -> None:
        controller = DegradationController(cpu_austere_profile)
        planner = ModelExecutionPlanner(cpu_austere_profile, controller)
        payload = planner.plan("phi3-mini").to_dict()
        assert "decision" in payload
        assert "precision" in payload
        assert "model_id" in payload
        assert "runtime_format" in payload
        assert "backend" in payload

    def test_default_variants_declared(self) -> None:
        assert len(DEFAULT_VARIANTS) >= 8


class TestBearerBroker:
    def test_no_bearers_returns_persist(self) -> None:
        broker = BearerBroker()
        decision = broker.route(MessageClass.TELEMETRY)
        assert decision.selected_bearer is None
        assert decision.persist_if_fail is True

    def test_register_and_route(self) -> None:
        broker = BearerBroker()
        broker.register_bearer(
            LinkType.WIFI,
            LinkMetrics(
                link_type=LinkType.WIFI,
                state=LinkState.UP,
                latency_ms=20,
                bandwidth_kbps=50000,
                packet_loss_pct=0.1,
                confidence=0.9,
            ),
        )
        decision = broker.route(MessageClass.TELEMETRY)
        assert decision.selected_bearer == LinkType.WIFI

    def test_urgent_tries_all_bearers(self) -> None:
        broker = BearerBroker()
        broker.register_bearer(
            LinkType.WIFI,
            LinkMetrics(link_type=LinkType.WIFI, state=LinkState.UP, latency_ms=20, confidence=0.9),
        )
        broker.register_bearer(
            LinkType.MESH,
            LinkMetrics(link_type=LinkType.MESH, state=LinkState.UP, latency_ms=500, confidence=0.5),
        )
        decision = broker.route(MessageClass.URGENT_CONTROL)
        assert decision.selected_bearer is not None
        assert len(decision.fallback_bearers) >= 1

    def test_bulk_needs_bandwidth(self) -> None:
        broker = BearerBroker()
        broker.register_bearer(
            LinkType.MESH,
            LinkMetrics(
                link_type=LinkType.MESH,
                state=LinkState.UP,
                latency_ms=500,
                bandwidth_kbps=10,
                confidence=0.5,
            ),
        )
        decision = broker.route(MessageClass.BULK_SYNC)
        assert decision.selected_bearer is None
        assert decision.persist_if_fail is True

    def test_down_bearer_excluded(self) -> None:
        broker = BearerBroker()
        broker.register_bearer(LinkType.WIFI, LinkMetrics(link_type=LinkType.WIFI, state=LinkState.DOWN))
        broker.register_bearer(
            LinkType.CELLULAR,
            LinkMetrics(link_type=LinkType.CELLULAR, state=LinkState.UP, latency_ms=80, confidence=0.8),
        )
        decision = broker.route(MessageClass.SUMMARIES)
        assert decision.selected_bearer == LinkType.CELLULAR

    def test_bearer_status(self) -> None:
        broker = BearerBroker()
        broker.register_bearer(
            LinkType.SATELLITE,
            LinkMetrics(link_type=LinkType.SATELLITE, state=LinkState.DEGRADED, latency_ms=800),
        )
        status = broker.bearer_status()
        assert len(status) == 1
        assert status[0]["type"] == "satellite"

    def test_link_change_callback(self) -> None:
        changes = []
        broker = BearerBroker(on_link_change=lambda up: changes.append(up))
        broker.register_bearer(LinkType.WIFI, LinkMetrics(link_type=LinkType.WIFI, state=LinkState.UP))
        assert len(changes) == 1
        assert changes[0] is True
        broker.mark_down(LinkType.WIFI)
        assert changes[-1] is False


class TestDurableQueue:
    def test_enqueue_and_stats(self, queue_db: DurableQueue) -> None:
        queue_db.enqueue("telemetry", {"temp": 42})
        queue_db.enqueue("logs", {"msg": "boot"})
        stats = queue_db.stats()
        assert stats["pending"] == 2

    def test_claim_and_ack(self, queue_db: DurableQueue) -> None:
        queue_db.enqueue("alert", {"level": "critical"}, priority=0)
        batch = queue_db.claim_batch(limit=5)
        assert len(batch) == 1
        assert batch[0].state == "in_flight"
        queue_db.ack(batch[0].item_id)
        assert queue_db.stats()["delivered"] == 1

    def test_nack_retries(self, queue_db: DurableQueue) -> None:
        queue_db.enqueue("log", {"x": 1}, max_retries=3)
        batch = queue_db.claim_batch()
        queue_db.nack(batch[0].item_id)
        assert queue_db.stats()["pending"] == 1

    def test_nack_exhausted(self, queue_db: DurableQueue) -> None:
        queue_db.enqueue("log", {"x": 1}, max_retries=1)
        batch = queue_db.claim_batch()
        queue_db.nack(batch[0].item_id)
        assert queue_db.stats()["failed"] == 1

    def test_priority_ordering(self, queue_db: DurableQueue) -> None:
        queue_db.enqueue("low", {"p": "low"}, priority=9)
        queue_db.enqueue("high", {"p": "high"}, priority=1)
        batch = queue_db.claim_batch(limit=2)
        assert batch[0].priority == 1

    def test_purge_delivered(self, queue_db: DurableQueue) -> None:
        queue_db.enqueue("x", {"a": 1})
        batch = queue_db.claim_batch()
        queue_db.ack(batch[0].item_id)
        removed = queue_db.purge_delivered()
        assert removed == 1


class TestSyncReconciler:
    def test_sync_with_send_fn(self, queue_db: DurableQueue) -> None:
        queue_db.enqueue("telemetry", {"val": 1})
        queue_db.enqueue("telemetry", {"val": 2})
        reconciler = SyncReconciler(queue_db)
        result = reconciler.run_sync(send_fn=lambda item: True)
        assert result["delivered"] == 2
        assert result["remaining_pending"] == 0

    def test_sync_with_failures(self, queue_db: DurableQueue) -> None:
        queue_db.enqueue("telemetry", {"val": 1})
        reconciler = SyncReconciler(queue_db)
        result = reconciler.run_sync(send_fn=lambda item: False)
        assert result["failed"] == 1
        assert result["remaining_pending"] == 1

    def test_sync_log(self, queue_db: DurableQueue) -> None:
        reconciler = SyncReconciler(queue_db)
        reconciler.run_sync()
        assert len(reconciler.get_sync_log()) == 1


class TestHealthSurface:
    def test_full_status(self, cpu_austere_profile: NodeProfile, queue_db: DurableQueue) -> None:
        profiler = HardwareProfiler()
        profiler.profile = cpu_austere_profile
        controller = DegradationController(cpu_austere_profile)
        broker = BearerBroker()
        surface = OperatorHealthSurface(profiler, controller, broker, queue_db)
        status = surface.full_status()
        assert "node" in status
        assert "operating_mode" in status
        assert "communications" in status
        assert "queue" in status
        assert "transitions" in status

    def test_summary_line(self, cpu_austere_profile: NodeProfile, queue_db: DurableQueue) -> None:
        profiler = HardwareProfiler()
        profiler.profile = cpu_austere_profile
        controller = DegradationController(cpu_austere_profile)
        broker = BearerBroker()
        surface = OperatorHealthSurface(profiler, controller, broker, queue_db)
        line = surface.summary_line()
        assert "bearers=" in line
        assert "queued=" in line
