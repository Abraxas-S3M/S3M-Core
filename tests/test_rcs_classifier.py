"""Unit tests for radar RCS classifier behavior.

Military context:
These checks ensure tactical target typing remains deterministic so downstream
air-defense allocation can prioritize the correct effector class.
"""

from __future__ import annotations

import pytest

from services.radar.models import RCSClassification, RadarPlot
from services.radar.rcs_classifier import RCSClassifier


def test_classify_non_positive_rcs_returns_clutter_with_floor_confidence():
    cls, confidence = RCSClassifier().classify(0.0)
    assert cls == RCSClassification.CLUTTER
    assert confidence == 0.3


def test_classify_overlap_band_prefers_cruise_missile_for_high_speed():
    cls, confidence = RCSClassifier().classify(rcs_m2=0.2, speed_mps=250.0, altitude_m=500.0)
    assert cls == RCSClassification.CRUISE_MISSILE
    assert confidence == pytest.approx(0.65)


def test_classify_out_of_table_returns_unknown():
    cls, confidence = RCSClassifier().classify(rcs_m2=200.0, speed_mps=120.0, altitude_m=2_000.0)
    assert cls == RCSClassification.UNKNOWN
    assert confidence == 0.3


def test_classify_high_altitude_penalizes_helicopter_tracks():
    cls, confidence = RCSClassifier().classify(rcs_m2=2.0, speed_mps=220.0, altitude_m=12_500.0)
    assert cls == RCSClassification.FIGHTER
    assert confidence == pytest.approx(0.75)


def test_classify_plot_updates_plot_in_place():
    plot = RadarPlot(
        rcs_linear_m2=2.0,
        radial_velocity_mps=-190.0,
        position_cartesian=(1_000.0, 500.0, 1_200.0),
    )
    result = RCSClassifier().classify_plot(plot)
    assert result is plot
    assert plot.rcs_classification == RCSClassification.FIGHTER
    assert plot.classification_confidence == pytest.approx(0.75)


def test_classify_plots_batch_classification_returns_updated_plots():
    plots = [
        RadarPlot(rcs_linear_m2=0.005, radial_velocity_mps=40.0, position_cartesian=(0.0, 0.0, 100.0)),
        RadarPlot(rcs_linear_m2=20.0, radial_velocity_mps=130.0, position_cartesian=(0.0, 0.0, 800.0)),
    ]
    result = RCSClassifier().classify_plots(plots)
    assert len(result) == 2
    assert result[0].rcs_classification == RCSClassification.SMALL_UAV
    assert result[1].rcs_classification == RCSClassification.LARGE_AIRCRAFT


def test_rcs_class_to_threat_class_maps_known_and_unknown_classes():
    assert (
        RCSClassifier.rcs_class_to_threat_class(RCSClassification.CRUISE_MISSILE)
        == "ENEMY_CRUISE_MISSILE"
    )
    assert RCSClassifier.rcs_class_to_threat_class(RCSClassification.UNKNOWN) == "UNKNOWN"


def test_radar_plot_rejects_negative_rcs():
    with pytest.raises(ValueError):
        RadarPlot(rcs_linear_m2=-0.1, radial_velocity_mps=0.0)


def test_radar_plot_rejects_invalid_cartesian_shape():
    with pytest.raises(ValueError):
        RadarPlot(
            rcs_linear_m2=0.1,
            radial_velocity_mps=10.0,
            position_cartesian=(0.0, 0.0),  # type: ignore[arg-type]
        )
