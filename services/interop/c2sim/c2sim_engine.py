"""C2SIM engine combining XML factory and transport adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from services.interop.c2sim.message_factory import C2SIMMessageFactory
from services.interop.c2sim.server_adapter import C2SIMServerAdapter
from src.security.interop.c2sim_adapter import C2SIMAdapter


class C2SIMEngine:
    """High-level C2SIM orchestration for orders, reports, and initialization."""

    def __init__(self, config: dict = None):
        cfg = config or {}
        self.config = cfg
        self.factory = C2SIMMessageFactory(
            namespace=str(cfg.get("namespace", "http://www.sisostds.org/schemas/C2SIM/1.1"))
        )
        self.server = C2SIMServerAdapter(server_url=cfg.get("server_url"))
        # Keep Phase 10 adapter logic available for mission conversion compatibility.
        self.phase10_adapter = C2SIMAdapter(
            server_url=cfg.get("server_url"),
            namespace=str(cfg.get("namespace", "http://www.sisostds.org/schemas/C2SIM/1.1")),
        )
        self._metrics = {"orders_sent": 0, "reports_sent": 0, "inits_sent": 0, "messages_received": 0}

    def send_order(self, order: dict) -> dict:
        xml = self.factory.create_order(
            order_id=str(order.get("order_id", f"order-{datetime.now(timezone.utc).timestamp()}")),
            issuer=str(order.get("issuer", "S3M-HQ")),
            task_type=str(order.get("task_type", "Move")),
            assigned_units=list(order.get("assigned_units", [])),
            waypoints=list(order.get("waypoints", [])),
            roe=str(order.get("roe", "self-defense")),
            start_time=order.get("start_time"),
        )
        result = self.server.push_message(xml, "Order")
        self._metrics["orders_sent"] += 1
        return result

    def send_report(self, report: dict) -> dict:
        xml = self.factory.create_report(
            report_id=str(report.get("report_id", f"report-{datetime.now(timezone.utc).timestamp()}")),
            reporter=str(report.get("reporter", "S3M-Unit")),
            report_type=str(report.get("report_type", "StatusReport")),
            content=dict(report.get("content", {})),
        )
        result = self.server.push_message(xml, "Report")
        self._metrics["reports_sent"] += 1
        return result

    def send_initialization(self, scenario: dict) -> dict:
        xml = self.factory.create_initialization(dict(scenario))
        result = self.server.push_message(xml, "Initialization")
        self._metrics["inits_sent"] += 1
        return result

    def receive_messages(self) -> List[dict]:
        rows = self.server.pull_messages()
        parsed: List[dict] = []
        for xml in rows:
            parsed.append(self.factory.parse_any(xml))
        self._metrics["messages_received"] += len(parsed)
        return parsed

    def order_to_mission(self, c2sim_order: dict) -> dict:
        payload = c2sim_order.get("data", c2sim_order)
        task = payload.get("task", payload)
        return {
            "mission_id": payload.get("order_id", payload.get("OrderID", "unknown-order")),
            "mission_type": str(task.get("task_type", "PATROL")).upper(),
            "agent_ids": list(task.get("assigned_units", [])),
            "waypoints": list(task.get("waypoints", [])),
            "rules_of_engagement": payload.get("roe", payload.get("rules_of_engagement", "SELF_DEFENSE_ONLY")),
            "start_time": payload.get("start_time"),
        }

    def mission_to_order(self, mission) -> str:
        return self.phase10_adapter.mission_to_order(mission)

    def aar_to_report(self, aar) -> str:
        return self.phase10_adapter.aar_to_report(aar)

    def scenario_to_initialization(self, scenario) -> str:
        if hasattr(scenario, "to_dict"):
            payload = scenario.to_dict()
        elif isinstance(scenario, dict):
            payload = scenario
        else:
            payload = dict(getattr(scenario, "__dict__", {}))
        return self.factory.create_initialization(payload)

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "metrics": dict(self._metrics),
            "server": self.server.get_server_status(),
            "namespace": self.factory.namespace,
        }
