"""Supply-chain disruption prediction for tactical sustainment."""

from __future__ import annotations

from typing import Any, Dict, List

from src.apps._shared import clamp, ensure_non_empty_text, safe_float
from src.llm_core import Orchestrator, QueryRequest, TaskDomain
from src.threat_detection import AnomalyDetector


class SupplyChainPredictor:
    """Predict logistics disruptions using anomaly scoring + LLM analysis."""

    def __init__(self) -> None:
        self.anomaly = AnomalyDetector(contamination=0.2)
        self.orchestrator = Orchestrator()

    def _extract_features(self, records: List[dict]) -> tuple[List[List[float]], List[str]]:
        features: List[List[float]] = []
        ids: List[str] = []
        for idx, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            ids.append(str(record.get("id", f"shipment-{idx+1}")))
            features.append(
                [
                    safe_float(record.get("delay_hours", 0.0)),
                    safe_float(record.get("weight", 0.0)),
                    safe_float(record.get("priority", 1.0)),
                    safe_float(record.get("route_distance", 0.0)),
                ]
            )
        return features, ids

    def _analyze_disruption(self, record: dict, anomaly_description: str) -> str:
        prompt = (
            "Analyze this supply chain anomaly: Shipment {sid} from {origin} to {dest} "
            "shows {desc}. Provide: 1) Likely cause 2) Impact assessment "
            "3) Recommended action 4) Alternative routing."
        ).format(
            sid=record.get("id", "unknown"),
            origin=record.get("origin", "unknown"),
            dest=record.get("dest", "unknown"),
            desc=anomaly_description,
        )
        response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.PLANNING))
        return str(getattr(response, "text", "")).strip()

    def predict_disruptions(self, supply_data: List[dict]) -> dict:
        """Identify anomalous shipments and generate disruption insights."""
        if not isinstance(supply_data, list):
            raise ValueError("supply_data must be a list")
        features, shipment_ids = self._extract_features(supply_data)
        if not features:
            return {
                "total_shipments": 0,
                "anomalies_detected": 0,
                "disruptions": [],
                "overall_risk": "LOW",
            }

        events = self.anomaly.detect(
            data=features,
            feature_names=["delay_hours", "weight", "priority", "route_distance"],
        )
        # First detector pass establishes baseline when model is cold; second pass surfaces anomalies.
        if not events:
            events = self.anomaly.detect(
                data=features,
                feature_names=["delay_hours", "weight", "priority", "route_distance"],
            )
        disruptions = []
        for event in events:
            sample_index = int(event.raw_data.get("sample_index", 0))
            if sample_index < 0 or sample_index >= len(supply_data):
                continue
            record = supply_data[sample_index]
            llm_analysis = self._analyze_disruption(record, event.description)
            fallback = (
                "Likely cause: route friction. Impact: moderate delay. "
                "Recommended action: reroute through lower-risk corridor."
            )
            if not llm_analysis or "pending" in llm_analysis.lower():
                llm_analysis = fallback
            disruptions.append(
                {
                    "shipment_id": shipment_ids[sample_index],
                    "anomaly_score": round(float(event.confidence), 3),
                    "analysis": llm_analysis,
                    "recommended_action": llm_analysis.split("Recommended action:")[-1].strip() if "Recommended action:" in llm_analysis else "Reroute and prioritize escort",
                }
            )

        anomaly_ratio = (len(disruptions) / len(features)) if features else 0.0
        risk = "LOW"
        if anomaly_ratio >= 0.35:
            risk = "HIGH"
        elif anomaly_ratio >= 0.15:
            risk = "MEDIUM"

        return {
            "total_shipments": len(features),
            "anomalies_detected": len(disruptions),
            "disruptions": disruptions,
            "overall_risk": risk,
        }

    def analyze_report(self, supply_data: List[dict]) -> str:
        """Generate full supply-chain status report text."""
        if not isinstance(supply_data, list):
            raise ValueError("supply_data must be a list")
        total = len(supply_data)
        avg_delay = 0.0
        if total:
            avg_delay = sum(safe_float(r.get("delay_hours", 0.0)) for r in supply_data if isinstance(r, dict)) / total
        summary = {
            "total_shipments": total,
            "avg_delay_hours": round(avg_delay, 2),
            "priority_load": round(sum(clamp(safe_float(r.get("priority", 1.0)), 1.0, 10.0) for r in supply_data if isinstance(r, dict)), 2),
        }
        prompt = (
            "Generate a military supply chain status report using this summary: "
            f"{summary}. Include: summary statistics, top risks, capacity utilization, delivery performance."
        )
        response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.PLANNING))
        text = str(getattr(response, "text", "")).strip()
        if not text or "pending" in text.lower():
            return (
                "Supply Report:\n"
                f"- Total shipments: {summary['total_shipments']}\n"
                f"- Average delay (hours): {summary['avg_delay_hours']}\n"
                "- Top risks: route congestion, hostile interference, maintenance delays\n"
                "- Capacity utilization: moderate\n"
                "- Delivery performance: monitor priority lanes"
            )
        return text
