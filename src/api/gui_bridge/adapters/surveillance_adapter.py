"""Surveillance/ISR workspace adapter.

Aggregates ISR assets from COP provider agents, sensor analytics,
and drone operations into GUISurveillanceData.
"""

from datetime import datetime, timezone

from src.api.gui_bridge.models.gui_schemas import (
    AssetStatus,
    GUIISRAsset,
    GUISurveillanceData,
    GUITargetBoardItem,
    GUITaskingItem,
    TaskingStatus,
)
from src.api.gui_bridge.training_emitter import emit_training_record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SurveillanceAdapter:
    def __init__(self):
        from src.dashboard.providers.cop_provider import COPDataProvider

        self._cop = COPDataProvider()

    def get_assets(self) -> dict:
        assets = self._build_assets()
        tasking = self._build_tasking()
        targets = self._build_targets()
        result = GUISurveillanceData(
            assets=assets,
            taskingQueue=tasking,
            targetBoard=targets,
            updatedAt=_now_iso(),
        ).model_dump()
        emit_training_record("surveillance", {"query": "assets"}, result)
        return result

    def get_collection_status(self) -> dict:
        """Expose collection-manager status for tactical retasking decisions."""
        try:
            from src.apps.intel.intel_manager import IntelManager

            mgr = IntelManager()
            result = mgr.collect_and_analyze()
            return {"collection": result, "updatedAt": _now_iso()}
        except Exception:
            return {"collection": {}, "updatedAt": _now_iso()}

    def get_source_reliability(self) -> dict:
        """Return source reliability grades to support confidence weighting."""
        try:
            from src.apps.intel.osint.source_manager import SourceManager

            sm = SourceManager()
            sources = sm.get_sources() if hasattr(sm, "get_sources") else []
            return {
                "sources": [s.model_dump() if hasattr(s, "model_dump") else s for s in sources],
                "updatedAt": _now_iso(),
            }
        except Exception:
            return {"sources": [], "updatedAt": _now_iso()}

    def get_fusion_brief(self, region: str = "all") -> dict:
        """Provide OSINT/ISR fused SITREP for commander surveillance context."""
        try:
            from src.apps.intel.intel_manager import IntelManager

            mgr = IntelManager()
            sitrep = mgr.generate_sitrep(region)
            return {
                "brief": sitrep.model_dump() if hasattr(sitrep, "model_dump") else {},
                "updatedAt": _now_iso(),
            }
        except Exception:
            return {"brief": {}, "updatedAt": _now_iso()}

    def get_watchlists(self) -> dict:
        """Entity watchlists for tactical surveillance triage and persistence."""
        try:
            from src.apps.intel.intel_manager import IntelManager

            mgr = IntelManager()
            items = mgr.search_intel("") if hasattr(mgr, "search_intel") else []
            return {
                "watchlists": {
                    "persons": [],
                    "organizations": [],
                    "vessels": [],
                    "vehicles": [],
                    "sites": [],
                },
                "updatedAt": _now_iso(),
            }
        except Exception:
            return {
                "watchlists": {
                    "persons": [],
                    "organizations": [],
                    "vessels": [],
                    "vehicles": [],
                    "sites": [],
                },
                "updatedAt": _now_iso(),
            }

    def _build_assets(self):
        agents = self._cop.get_agents()
        results = []
        for a in agents:
            role = str(a.get("role", "")).upper()
            asset_type = {
                "SCOUT": "MQ-9",
                "LEADER": "RQ-4",
                "INTERCEPTOR": "MQ-1C",
            }.get(role, "SIGINT Node")
            state = str(a.get("state", "")).upper()
            status = (
                AssetStatus.ACTIVE
                if state in ("ACTIVE", "EXECUTING")
                else (
                    AssetStatus.MAINTENANCE
                    if state == "MAINTENANCE"
                    else AssetStatus.STANDBY
                )
            )
            pos = a.get("position", {})
            loc = (
                f"Grid {pos.get('x', 0):.0f}-{pos.get('y', 0):.0f}"
                if isinstance(pos, dict)
                else "Unknown"
            )
            results.append(
                GUIISRAsset(
                    id=a.get("id", ""),
                    type=asset_type,
                    status=status,
                    location=loc,
                )
            )
        if not results:
            results = [
                GUIISRAsset(
                    id="UAV-02",
                    type="MQ-9",
                    status=AssetStatus.ACTIVE,
                    location="Sector 8",
                ),
                GUIISRAsset(
                    id="UAV-07",
                    type="RQ-4",
                    status=AssetStatus.STANDBY,
                    location="FOB East",
                ),
                GUIISRAsset(
                    id="SIG-11",
                    type="SIGINT Node",
                    status=AssetStatus.ACTIVE,
                    location="Sector 6",
                ),
            ]
        return results

    def _build_tasking(self):
        return [
            GUITaskingItem(
                id="TSK-101",
                priority="high",
                description="Re-task UAV-02 for corridor sweep",
                assignedAssetId="UAV-02",
                status=TaskingStatus.IN_PROGRESS,
            ),
            GUITaskingItem(
                id="TSK-104",
                priority="medium",
                description="Thermal sweep near grid 7-F",
                assignedAssetId=None,
                status=TaskingStatus.QUEUED,
            ),
        ]

    def _build_targets(self):
        threats = self._cop.get_threats()
        results = []
        for t in threats[:5]:
            results.append(
                GUITargetBoardItem(
                    id=t.get("id", "TGT-X"),
                    designation=t.get("title", "Unknown contact"),
                    confidence=(
                        int(float(t.get("confidence", 0.5)) * 100)
                        if float(t.get("confidence", 1)) <= 1.0
                        else int(t.get("confidence", 50))
                    ),
                    lastSeen=t.get("timestamp", _now_iso()),
                )
            )
        if not results:
            results = [
                GUITargetBoardItem(
                    id="TGT-44",
                    designation="Unknown fast mover",
                    confidence=84,
                    lastSeen=_now_iso(),
                )
            ]
        return results
