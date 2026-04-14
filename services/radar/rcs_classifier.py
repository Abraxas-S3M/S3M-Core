"""RCS-based tactical target classification helpers."""

from __future__ import annotations

from typing import Iterable

from services.radar.models import RCSClassification, RadarPlot


class RCSClassifier:
    """Classify radar plots by RCS to support rapid threat triage."""

    def classify_plots(self, plots: Iterable[RadarPlot]) -> None:
        for plot in plots:
            if not isinstance(plot, RadarPlot):
                continue
            plot.rcs_classification = self.classify_rcs(plot.rcs_dbsm)

    def classify_rcs(self, rcs_dbsm: float) -> RCSClassification:
        if not isinstance(rcs_dbsm, (int, float)):
            return RCSClassification.UNKNOWN
        value = float(rcs_dbsm)
        if value < -20.0:
            return RCSClassification.MICRO
        if value < -5.0:
            return RCSClassification.SMALL
        if value < 10.0:
            return RCSClassification.MEDIUM
        return RCSClassification.LARGE

    @staticmethod
    def rcs_class_to_threat_class(rcs_class: RCSClassification) -> str:
        mapping = {
            RCSClassification.MICRO: "small_uav",
            RCSClassification.SMALL: "uav_or_munition",
            RCSClassification.MEDIUM: "aircraft",
            RCSClassification.LARGE: "large_aircraft_or_transport",
            RCSClassification.UNKNOWN: "unknown",
        }
        return mapping.get(rcs_class, "unknown")

