"""Readiness workspace adapter.

Internal dependencies:
- src.api.readiness_routes (readiness_router data)
- src.dashboard.providers.runtime_store (fallback state)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.api.gui_bridge.models.gui_schemas import (
    GUICertStatus,
    GUIEquipmentSummary,
    GUIPersonnelSummary,
    GUIReadinessData,
    GUIReadinessEnriched,
    GUIUnitStatus,
    UnitReadinessStatus,
)
from src.api.gui_bridge.training_emitter import emit_training_record
from src.readiness.fatigue_model import DawsonReidFatigueModel


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReadinessAdapter:
    def __init__(self):
        self._overview_func = None
        self._fatigue_model = DawsonReidFatigueModel()
        try:
            from src.api.readiness_routes import _readiness_store

            self._overview_func = _readiness_store
        except Exception:
            pass

    def get_summary(self) -> GUIReadinessData:
        # Try to get real data from readiness module
        personnel_data = self._get_personnel()
        equipment_data = self._get_equipment()
        units = self._get_units()

        result = GUIReadinessData(
            personnel=GUIPersonnelSummary(**personnel_data),
            equipment=GUIEquipmentSummary(**equipment_data),
            unitStatus=units,
            updatedAt=_now_iso(),
        )
        emit_training_record("readiness", {"query": "summary"}, result)
        return result

    def get_enriched_summary(self) -> dict:
        base = self.get_summary()
        certs = self._get_certifications()
        quals = self._get_qualification_matrix()
        forecast = self._get_readiness_forecast()
        return GUIReadinessEnriched(
            personnel=base.personnel,
            equipment=base.equipment,
            unitStatus=base.unitStatus,
            certifications=certs,
            qualificationMatrix=quals,
            readinessForecast=forecast,
            updatedAt=_now_iso(),
        ).model_dump()

    def _get_personnel(self) -> Dict[str, int]:
        try:
            from src.api.readiness_routes import _members

            total = len(_members)
            deployed = sum(
                1
                for m in _members.values()
                if getattr(m, "status", None) in ("deployed", "active")
            )
            on_leave = sum(
                1 for m in _members.values() if getattr(m, "status", None) == "leave"
            )
            return {
                "available": max(0, total - deployed - on_leave),
                "deployed": deployed,
                "onLeave": on_leave,
            }
        except Exception:
            return {"available": 1240, "deployed": 880, "onLeave": 47}

    def _get_equipment(self) -> Dict[str, int]:
        try:
            from src.api.maintenance_routes import _assets

            ready = sum(
                1
                for a in _assets.values()
                if getattr(a, "status", "") in ("operational", "ready")
            )
            maint = sum(
                1
                for a in _assets.values()
                if getattr(a, "status", "") in ("maintenance", "scheduled")
            )
            unavail = len(_assets) - ready - maint
            return {"ready": ready, "maintenance": maint, "unavailable": max(0, unavail)}
        except Exception:
            return {"ready": 312, "maintenance": 49, "unavailable": 15}

    def _get_units(self):
        try:
            from src.api.readiness_routes import _units

            result = []
            for uid, unit in _units.items():
                score = getattr(unit, "readiness_score", 0)
                if isinstance(score, float) and score <= 1.0:
                    score = int(score * 100)
                status = (
                    UnitReadinessStatus.READY
                    if score >= 80
                    else (
                        UnitReadinessStatus.DEGRADED
                        if score >= 50
                        else UnitReadinessStatus.UNAVAILABLE
                    )
                )
                result.append(
                    GUIUnitStatus(unitId=uid, readiness=int(score), status=status)
                )
            return result if result else self._default_units()
        except Exception:
            return self._default_units()

    @staticmethod
    def _default_units():
        return [
            GUIUnitStatus(
                unitId="ALPHA-1", readiness=92, status=UnitReadinessStatus.READY
            ),
            GUIUnitStatus(
                unitId="BRAVO-3", readiness=76, status=UnitReadinessStatus.DEGRADED
            ),
            GUIUnitStatus(
                unitId="CHARLIE-2",
                readiness=61,
                status=UnitReadinessStatus.DEGRADED,
            ),
        ]

    def _get_certifications(self) -> List[GUICertStatus]:
        """Pull from readiness config + personnel store."""
        import yaml

        try:
            with open("configs/readiness.yaml", encoding="utf-8") as handle:
                cfg = yaml.safe_load(handle) or {}
            cert_types = cfg.get("certifications", {}).get("standard_types", [])

            cert_records = []
            expiring_ids = set()
            expired_ids = set()
            try:
                from src.api.readiness_routes import _readiness

                cert_mgr = _readiness.certification_manager
                cert_records = list(getattr(cert_mgr, "certifications", {}).values())
                expiring_ids = {cert.cert_id for cert in cert_mgr.get_expiring_soon(30)}
                expired_ids = {cert.cert_id for cert in cert_mgr.get_expired()}
            except Exception:
                pass

            results: List[GUICertStatus] = []
            for cert_type in cert_types:
                cert_code = str(cert_type.get("type", "UNKNOWN"))
                matching = [
                    cert
                    for cert in cert_records
                    if str(getattr(cert, "certification_type", "")) == cert_code
                ]
                total = len(matching)
                current = sum(
                    1
                    for cert in matching
                    if callable(getattr(cert, "is_valid", None)) and cert.is_valid()
                )
                expiring = sum(1 for cert in matching if getattr(cert, "cert_id", "") in expiring_ids)
                expired = sum(1 for cert in matching if getattr(cert, "cert_id", "") in expired_ids)
                if expired == 0 and total > current:
                    expired = total - current

                results.append(
                    GUICertStatus(
                        certType=cert_code,
                        nameEn=str(cert_type.get("name_en", cert_code)),
                        nameAr=str(cert_type.get("name_ar", cert_code)),
                        total=total,
                        current=current,
                        expiringSoon=expiring,
                        expired=expired,
                    )
                )
            fatigue_status = self._build_shift_rotation_fatigue_status()
            if fatigue_status is not None:
                results.append(fatigue_status)
            return results
        except Exception:
            return []

    def _build_shift_rotation_fatigue_status(self) -> Optional[GUICertStatus]:
        try:
            from src.api.readiness_routes import _readiness

            members = list(_readiness.personnel_registry.get_members())
            now = datetime.now(timezone.utc)
            scores: List[float] = []
            for member in members:
                history = self._get_member_sleep_history(member, now)
                scores.append(self._fatigue_model.compute_fatigue_score(history, now))

            return GUICertStatus(
                certType="SHIFT_ROTATION_FATIGUE",
                nameEn="Shift/Rotation Fatigue",
                nameAr="إجهاد المناوبات والتناوب",
                total=len(scores),
                current=sum(1 for score in scores if score >= 75.0),
                expiringSoon=sum(1 for score in scores if 50.0 <= score < 75.0),
                expired=sum(1 for score in scores if score < 50.0),
            )
        except Exception:
            return GUICertStatus(
                certType="SHIFT_ROTATION_FATIGUE",
                nameEn="Shift/Rotation Fatigue",
                nameAr="إجهاد المناوبات والتناوب",
                total=0,
                current=0,
                expiringSoon=0,
                expired=0,
            )

    def _get_member_sleep_history(
        self,
        member: Any,
        current_time: datetime,
    ) -> List[Tuple[datetime, datetime]]:
        explicit = self._normalize_sleep_history(getattr(member, "sleep_history", None))
        if explicit:
            return explicit
        return self._build_status_sleep_history(member, current_time)

    @staticmethod
    def _coerce_datetime(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            if raw.endswith("Z"):
                raw = f"{raw[:-1]}+00:00"
            parsed = datetime.fromisoformat(raw)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        return None

    def _normalize_sleep_history(self, raw_history: Any) -> List[Tuple[datetime, datetime]]:
        if not isinstance(raw_history, list):
            return []
        windows: List[Tuple[datetime, datetime]] = []
        for item in raw_history:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            sleep_start = self._coerce_datetime(item[0])
            sleep_end = self._coerce_datetime(item[1])
            if sleep_start is None or sleep_end is None or sleep_end <= sleep_start:
                continue
            windows.append((sleep_start, sleep_end))
        windows.sort(key=lambda row: row[0])
        return windows

    def _build_status_sleep_history(
        self,
        member: Any,
        current_time: datetime,
    ) -> List[Tuple[datetime, datetime]]:
        status_value = getattr(getattr(member, "status", None), "value", None) or str(
            getattr(member, "status", "ACTIVE_DUTY")
        )
        status_key = status_value.upper()
        plan = {
            "ACTIVE_DUTY": (22.0, 7.0),
            "TRAINING": (23.0, 6.0),
            "DEPLOYED": (0.0, 5.0),
            "MEDICAL_LEAVE": (21.0, 8.5),
            "ADMINISTRATIVE_LEAVE": (21.5, 8.0),
            "RESERVE": (22.0, 8.0),
        }
        start_hour, sleep_hours = plan.get(status_key, (22.0, 7.0))

        training_score = getattr(member, "training_score", None)
        if isinstance(training_score, (int, float)):
            if training_score < 70:
                sleep_hours = max(4.0, sleep_hours - 0.5)
            elif training_score > 90:
                sleep_hours = min(9.5, sleep_hours + 0.5)

        anchor = current_time.astimezone(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        windows: List[Tuple[datetime, datetime]] = []
        for days_back in (3, 2, 1):
            sleep_start = anchor - timedelta(days=days_back) + timedelta(hours=start_hour)
            sleep_end = sleep_start + timedelta(hours=sleep_hours)
            if sleep_end <= current_time:
                windows.append((sleep_start, sleep_end))

        if windows:
            return windows

        fallback_end = current_time - timedelta(hours=1)
        fallback_start = fallback_end - timedelta(hours=max(4.0, sleep_hours))
        return [(fallback_start, fallback_end)]

    def _get_qualification_matrix(self) -> Dict[str, Any]:
        try:
            from src.api.readiness_routes import _readiness

            members = _readiness.personnel_registry.get_members()
            units = _readiness.unit_manning_manager.get_units()
            by_branch = _readiness.personnel_registry.get_statistics().get("by_branch", {})
            coalition_ready = len(
                [m for m in members if len(set(getattr(m, "languages", []) or [])) >= 3]
            )
            bilingual_ready = len(
                [m for m in members if {"ar", "en"}.issubset(set(getattr(m, "languages", []) or []))]
            )
            total_slots = sum(len(getattr(unit, "slots", [])) for unit in units)
            filled_slots = sum(
                len([slot for slot in getattr(unit, "slots", []) if getattr(slot, "filled_by", None)])
                for unit in units
            )
            return {
                "byMission": {
                    "jointOps": {"qualified": bilingual_ready, "required": max(1, len(members))},
                    "coalitionSupport": {"qualified": coalition_ready, "required": max(1, len(units) * 4)},
                    "cyberDefense": {
                        "qualified": int(by_branch.get("CYBER", 0)),
                        "required": max(1, int(len(members) * 0.1)),
                    },
                },
                "byPlatform": {
                    "ground": {"qualified": int(by_branch.get("ARMY", 0)), "required": max(1, len(units) * 8)},
                    "air": {"qualified": int(by_branch.get("AIR_FORCE", 0)), "required": max(1, len(units) * 3)},
                    "maritime": {"qualified": int(by_branch.get("NAVY", 0)), "required": max(1, len(units) * 2)},
                },
                "byClassification": {
                    "confidentialPlus": {"qualified": len(members), "required": max(1, len(members))},
                    "secretPlus": {
                        "qualified": len(
                            [m for m in members if str(getattr(getattr(m, "clearance", ""), "value", "")) in {"SECRET", "TOP_SECRET", "SCI"}]
                        ),
                        "required": max(1, int(len(members) * 0.35)),
                    },
                },
                "byCoalition": {
                    "arEnBilingual": {"qualified": bilingual_ready, "required": max(1, int(len(members) * 0.8))},
                    "multilingual": {"qualified": coalition_ready, "required": max(1, int(len(members) * 0.2))},
                },
                "specialistShortageHeatmap": [
                    {
                        "unitId": getattr(unit, "unit_id", "UNKNOWN"),
                        "shortagePercent": int(
                            round(
                                (1.0 - (len([s for s in getattr(unit, "slots", []) if getattr(s, "filled_by", None)]) / max(1, len(getattr(unit, "slots", [])))))
                                * 100
                            )
                        ),
                    }
                    for unit in units
                ],
                "manningFillPercent": int(round((filled_slots / max(1, total_slots)) * 100)),
            }
        except Exception:
            return {
                "byMission": {},
                "byPlatform": {},
                "byClassification": {},
                "byCoalition": {},
                "specialistShortageHeatmap": [],
                "manningFillPercent": 0,
            }

    def _get_readiness_forecast(self) -> List[Dict[str, Any]]:
        baseline = 76
        vacancy_pressure = 0
        try:
            from src.api.readiness_routes import _readiness

            force = _readiness.calculate_force_readiness()
            baseline = int(round(float(force.get("overall_readiness", baseline))))
            units = _readiness.unit_manning_manager.get_units()
            total_slots = sum(len(getattr(unit, "slots", [])) for unit in units)
            vacant_slots = sum(getattr(unit, "vacant_count", lambda: 0)() for unit in units)
            vacancy_pressure = int(round((vacant_slots / max(1, total_slots)) * 100))
        except Exception:
            try:
                units = self._get_units()
                baseline = int(sum(unit.readiness for unit in units) / max(1, len(units)))
            except Exception:
                pass

        horizons = [1, 7, 14, 30]
        now = datetime.now(timezone.utc)
        output: List[Dict[str, Any]] = []
        for idx, day in enumerate(horizons):
            tactical_drag = min(12, int(vacancy_pressure * 0.2) + idx)
            projected = max(0, min(100, baseline - tactical_drag + (1 if day == 30 else 0)))
            output.append(
                {
                    "horizonDays": day,
                    "timestamp": now.replace(microsecond=0).isoformat(),
                    "projectedReadiness": projected,
                    "confidence": max(55, 88 - (idx * 8)),
                }
            )
        return output
