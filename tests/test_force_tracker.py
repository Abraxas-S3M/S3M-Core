"""Unit tests for tactical force-awareness tracking and prediction."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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


def test_geopoint_haversine_reasonable_distance() -> None:
    riyadh = GeoPoint(24.7136, 46.6753)
    jeddah = GeoPoint(21.4858, 39.1925)
    km = riyadh.haversine_km(jeddah)
    assert 800.0 <= km <= 1000.0


def test_asset_state_validation_rejects_invalid_range() -> None:
    with pytest.raises(ValueError):
        AssetState(
            asset_id="a1",
            callsign="c1",
            domain=Domain.LAND,
            status=ForceStatus.UNKNOWN,
            position=GeoPoint(10.0, 10.0),
            readiness_score=1.2,
        )


def test_store_ring_buffer_and_latest() -> None:
    store = ForceStateStore(history_depth=2)
    store.upsert(_state("A-1", 0.9, 0))
    store.upsert(_state("A-1", 0.8, 1))
    store.upsert(_state("A-1", 0.7, 2))
    hist = store.history("A-1", n=10)
    assert len(hist) == 2
    assert hist[0].readiness_score == 0.8
    assert store.latest("A-1").readiness_score == 0.7


def test_predictive_engine_returns_expected_hours() -> None:
    engine = PredictiveReadinessEngine()
    history = [
        _state("JET-1", 0.8, 0),
        _state("JET-1", 0.6, 1),
        _state("JET-1", 0.4, 2),
    ]
    # Linear drop of 0.2 per hour reaches threshold (0.3) in 0.5h from last point.
    assert engine.predict_nmc_hours(history) == 0.5


def test_predictive_engine_returns_none_when_improving() -> None:
    engine = PredictiveReadinessEngine()
    history = [
        _state("JET-2", 0.3, 0),
        _state("JET-2", 0.4, 1),
        _state("JET-2", 0.5, 2),
    ]
    assert engine.predict_nmc_hours(history) is None


def test_manager_full_picture_and_nearby_assets() -> None:
    fam = ForceAwarenessManager()
    fam.update(_state("AIR-1", 0.85, 0, lat=24.7, lon=46.6, status=ForceStatus.FULLY_MISSION_CAPABLE))
    fam.update(_state("AIR-1", 0.65, 1, lat=24.7, lon=46.6, status=ForceStatus.PARTIALLY_MISSION_CAPABLE))
    fam.update(_state("AIR-1", 0.45, 2, lat=24.7, lon=46.6, status=ForceStatus.PARTIALLY_MISSION_CAPABLE))
    fam.update(_state("SEA-1", 0.9, 0, lat=30.0, lon=35.0, status=ForceStatus.FULLY_MISSION_CAPABLE))

    asset = fam.get_asset("AIR-1")
    assert asset is not None
    assert asset["status"] == "PMC"
    assert asset["predicted_nmc_hours"] is not None
    assert asset["alert"] is True

    picture = fam.get_full_picture()
    assert picture["total_assets"] == 2
    assert picture["by_status"]["PMC"] == 1
    assert picture["by_status"]["FMC"] == 1

    nearby = fam.assets_near(lat=24.7136, lon=46.6753, radius_km=100.0)
    ids = {item["asset_id"] for item in nearby}
    assert "AIR-1" in ids
    assert "SEA-1" not in ids
