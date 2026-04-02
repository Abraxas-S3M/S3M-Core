"""Unit tests for tactical force-awareness tracking and prediction."""

import unittest
from datetime import datetime, timedelta, timezone

from src.force_awareness.force_tracker import (
    AssetState,
    Domain,
    ForceAwarenessManager,
    ForceStateStore,
    ForceStatus,
    GeoPoint,
    PredictiveReadinessEngine,
)


def _ts(hours_from_base: int) -> str:
    base = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(hours=hours_from_base)).isoformat()


def _state(
    asset_id: str,
    readiness: float,
    ts_hour: int,
    lat: float = 24.7136,
    lon: float = 46.6753,
    status: ForceStatus = ForceStatus.FULLY_MISSION_CAPABLE,
) -> AssetState:
    return AssetState(
        asset_id=asset_id,
        callsign=f"CS-{asset_id}",
        domain=Domain.AIR,
        status=status,
        position=GeoPoint(lat=lat, lon=lon, alt_m=1000.0),
        readiness_score=readiness,
        fuel_pct=0.8,
        munitions_pct=0.7,
        maintenance_hours_due=4.0,
        crew_fatigue_score=0.2,
        timestamp=_ts(ts_hour),
        metadata={"mission": "CAP"},
    )


class TestForceTracker(unittest.TestCase):
    def test_geopoint_haversine_reasonable_distance(self) -> None:
        riyadh = GeoPoint(24.7136, 46.6753)
        jeddah = GeoPoint(21.4858, 39.1925)
        km = riyadh.haversine_km(jeddah)
        self.assertGreaterEqual(km, 800.0)
        self.assertLessEqual(km, 1000.0)

    def test_asset_state_validation_rejects_invalid_range(self) -> None:
        with self.assertRaises(ValueError):
            AssetState(
                asset_id="a1",
                callsign="c1",
                domain=Domain.LAND,
                status=ForceStatus.UNKNOWN,
                position=GeoPoint(10.0, 10.0),
                readiness_score=1.2,
            )

    def test_store_ring_buffer_and_latest(self) -> None:
        store = ForceStateStore(history_depth=2)
        store.upsert(_state("A-1", 0.9, 0))
        store.upsert(_state("A-1", 0.8, 1))
        store.upsert(_state("A-1", 0.7, 2))
        hist = store.history("A-1", n=10)
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0].readiness_score, 0.8)
        self.assertEqual(store.latest("A-1").readiness_score, 0.7)

    def test_predictive_engine_returns_expected_hours(self) -> None:
        engine = PredictiveReadinessEngine()
        history = [
            _state("JET-1", 0.8, 0),
            _state("JET-1", 0.6, 1),
            _state("JET-1", 0.4, 2),
        ]
        # Linear drop of 0.2 per hour reaches threshold (0.3) in 0.5h from last point.
        self.assertEqual(engine.predict_nmc_hours(history), 0.5)

    def test_predictive_engine_returns_none_when_improving(self) -> None:
        engine = PredictiveReadinessEngine()
        history = [
            _state("JET-2", 0.3, 0),
            _state("JET-2", 0.4, 1),
            _state("JET-2", 0.5, 2),
        ]
        self.assertIsNone(engine.predict_nmc_hours(history))

    def test_manager_full_picture_and_nearby_assets(self) -> None:
        fam = ForceAwarenessManager()
        fam.update(_state("AIR-1", 0.85, 0, lat=24.7, lon=46.6, status=ForceStatus.FULLY_MISSION_CAPABLE))
        fam.update(_state("AIR-1", 0.65, 1, lat=24.7, lon=46.6, status=ForceStatus.PARTIALLY_MISSION_CAPABLE))
        fam.update(_state("AIR-1", 0.45, 2, lat=24.7, lon=46.6, status=ForceStatus.PARTIALLY_MISSION_CAPABLE))
        fam.update(_state("SEA-1", 0.9, 0, lat=30.0, lon=35.0, status=ForceStatus.FULLY_MISSION_CAPABLE))

        asset = fam.get_asset("AIR-1")
        self.assertIsNotNone(asset)
        assert asset is not None
        self.assertEqual(asset["status"], "PMC")
        self.assertIsNotNone(asset["predicted_nmc_hours"])
        self.assertTrue(asset["alert"])

        picture = fam.get_full_picture()
        self.assertEqual(picture["total_assets"], 2)
        self.assertEqual(picture["by_status"]["PMC"], 1)
        self.assertEqual(picture["by_status"]["FMC"], 1)

        nearby = fam.assets_near(lat=24.7136, lon=46.6753, radius_km=100.0)
        ids = {item["asset_id"] for item in nearby}
        self.assertIn("AIR-1", ids)
        self.assertNotIn("SEA-1", ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
