"""Coordinator for incident-response platform adapters in Layer 07."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from services.cyber.ir_platforms.cortex_adapter import CortexAdapter
from services.cyber.ir_platforms.dfir_iris_adapter import DFIRIRISAdapter
from services.cyber.ir_platforms.misp_adapter import MISPAdapter
from services.cyber.ir_platforms.thehive_adapter import TheHiveAdapter
from services.cyber.models import CaseSeverity, EnrichmentResult, IncidentCase, Observable


class IRPlatformBridge:
    """Runs case synchronization and observable enrichment across SOC platforms."""

    def __init__(self) -> None:
        self.thehive = TheHiveAdapter()
        self.cortex = CortexAdapter()
        self.misp = MISPAdapter()
        self.dfir_iris = DFIRIRISAdapter()

    def enrich_observables(self, observables: List[Observable]) -> List[EnrichmentResult]:
        return [self.cortex.analyze_observable(observable) for observable in observables]

    def enrich_observables_from_dicts(self, observables: List[dict]) -> List[EnrichmentResult]:
        typed: List[Observable] = []
        for item in observables:
            if isinstance(item, Observable):
                typed.append(item)
                continue
            if not isinstance(item, dict):
                continue
            try:
                typed.append(
                    Observable(
                        observable_id=str(item.get("observable_id", "")),
                        observable_type=item.get("observable_type", "IP_ADDRESS"),
                        value=str(item.get("value", "")),
                        source_case_id=str(item.get("source_case_id", "UNKNOWN_CASE")),
                        first_seen=item.get("first_seen", datetime.now(timezone.utc)),
                        last_seen=item.get("last_seen", datetime.now(timezone.utc)),
                        tags=list(item.get("tags", [])),
                        tlp=str(item.get("tlp", "AMBER")),
                        enrichments=list(item.get("enrichments", [])),
                    )
                )
            except Exception:
                continue
        return self.enrich_observables(typed)

    def process_case(self, case: IncidentCase) -> dict:
        thehive_result = self.thehive.create_alert(case)

        typed_observables: List[Observable] = []
        for observable in case.observables:
            if isinstance(observable, Observable):
                typed_observables.append(observable)
            elif isinstance(observable, dict):
                try:
                    typed_observables.append(
                        Observable(
                            observable_id=str(observable.get("observable_id", "")),
                            observable_type=observable.get("observable_type", "IP_ADDRESS"),
                            value=str(observable.get("value", "")),
                            source_case_id=case.case_id,
                            tags=list(observable.get("tags", [])),
                            tlp=str(observable.get("tlp", "AMBER")),
                            enrichments=list(observable.get("enrichments", [])),
                        )
                    )
                except Exception:
                    continue

        enrichments = self.enrich_observables(typed_observables)
        for enrichment in enrichments:
            case.enrichments.append(enrichment.to_dict())

        misp_result = self.misp.create_event(case)

        dfir_result = None
        if case.severity in {CaseSeverity.HIGH, CaseSeverity.CRITICAL}:
            dfir_result = self.dfir_iris.create_case(case)

        return {
            "thehive": thehive_result,
            "enrichments": [item.to_dict() for item in enrichments],
            "misp": misp_result,
            "dfir_iris": dfir_result,
        }

    def get_platform_status(self) -> dict:
        return {
            "thehive": self.thehive.connect(),
            "cortex": self.cortex.connect(),
            "misp": self.misp.connect(),
            "dfir_iris": self.dfir_iris.connect(),
        }

    def health_check(self) -> dict:
        status = self.get_platform_status()
        online = [name for name, ok in status.items() if ok]
        return {
            "status": "operational" if online else "degraded",
            "platforms_online": online,
            "platform_status": status,
        }
