"""Unit tests for radar scan-to-scan plot correlation.

Military context:
These checks protect tactical track custody quality before plots are promoted
into downstream multi-sensor fusion and fire-control workflows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.radar.models import RadarPlot
from services.radar.plot_correlator import PlotCorrelator


def _ts(seconds: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds)


def test_new_track_stays_active_on_creation_scan():
    correlator = PlotCorrelator(distance_gate_m=500.0, velocity_gate_mps=20.0, max_coast_scans=0)
    first_scan = [RadarPlot(snr_db=18.0, position_cartesian=(100.0, 50.0, 20.0), radial_velocity_mps=25.0)]

    correlated = correlator.correlate(first_scan, scan_time=_ts(0))

    track_id = correlated[0].correlated_track_id
    assert isinstance(track_id, str) and track_id.startswith("rtrk-")
    assert correlator.get_active_track_count() == 1
    assert correlator.get_stats()["coasting"] == 0


def test_associates_consecutive_scan_plot_to_existing_track():
    correlator = PlotCorrelator(distance_gate_m=250.0, velocity_gate_mps=15.0, max_coast_scans=2)
    first_scan = [RadarPlot(snr_db=20.0, position_cartesian=(1_000.0, 0.0, 0.0), radial_velocity_mps=30.0)]
    first_result = correlator.correlate(first_scan, scan_time=_ts(0))
    first_track = first_result[0].correlated_track_id

    second_scan = [RadarPlot(snr_db=16.0, position_cartesian=(1_030.0, 0.0, 0.0), radial_velocity_mps=31.0)]
    second_result = correlator.correlate(second_scan, scan_time=_ts(1))

    assert second_result[0].correlated_track_id == first_track
    assert correlator.get_stats()["total_tracks"] == 1


def test_velocity_gate_rejects_incompatible_plot():
    correlator = PlotCorrelator(distance_gate_m=500.0, velocity_gate_mps=5.0, max_coast_scans=2)
    first_scan = [RadarPlot(snr_db=14.0, position_cartesian=(0.0, 0.0, 0.0), radial_velocity_mps=20.0)]
    first_track = correlator.correlate(first_scan, scan_time=_ts(0))[0].correlated_track_id

    second_scan = [RadarPlot(snr_db=13.0, position_cartesian=(10.0, 0.0, 0.0), radial_velocity_mps=35.0)]
    second_track = correlator.correlate(second_scan, scan_time=_ts(1))[0].correlated_track_id

    assert second_track != first_track
    assert correlator.get_stats()["total_tracks"] == 2


def test_coasting_and_pruning_lifecycle():
    correlator = PlotCorrelator(distance_gate_m=500.0, velocity_gate_mps=20.0, max_coast_scans=1)
    correlator.correlate(
        [RadarPlot(snr_db=17.0, position_cartesian=(0.0, 0.0, 0.0), radial_velocity_mps=0.0)],
        scan_time=_ts(0),
    )

    correlator.correlate([], scan_time=_ts(1))
    assert correlator.get_stats() == {"active_tracks": 1, "total_tracks": 1, "coasting": 1}

    correlator.correlate([], scan_time=_ts(2))
    assert correlator.get_active_track_count() == 0

    correlator.correlate([], scan_time=_ts(3))
    assert correlator.get_stats()["total_tracks"] == 1

    correlator.correlate([], scan_time=_ts(4))
    assert correlator.get_stats()["total_tracks"] == 0


def test_models_and_correlator_validate_inputs():
    with pytest.raises(ValueError):
        RadarPlot(snr_db=10.0, position_cartesian=(1.0, 2.0), radial_velocity_mps=2.0)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        PlotCorrelator(distance_gate_m=0.0)
