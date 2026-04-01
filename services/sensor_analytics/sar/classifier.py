"""Rule-driven SAR ship classifier for tactical maritime analytics."""

from __future__ import annotations

from typing import Dict, List, Optional

from services.sensor_analytics.models import SARDetection, VesselClassification


class SARShipClassifier:
    """Classify SAR vessel detections using dimensions and shape heuristics."""

    def __init__(self) -> None:
        self._llm_available = self._detect_llm()

    def _detect_llm(self) -> bool:
        # Tactical fallback: if LLM adapter is unavailable, deterministic rules remain active.
        try:
            from src.llm_core.inference import S3MInference  # noqa: F401

            return True
        except Exception:
            return False

    def classify(self, detection: SARDetection) -> VesselClassification:
        length_m = max(0.0, float(detection.estimated_length_meters))
        width_m = max(0.1, float(detection.estimated_width_meters))
        ratio = length_m / width_m

        if length_m > 200:
            if ratio > 6:
                return VesselClassification.TANKER
            return VesselClassification.CARGO

        if 50 <= length_m <= 200:
            if ratio > 6:
                return VesselClassification.CARGO
            if 3 <= ratio <= 6:
                return VesselClassification.MILITARY_SURFACE
            return VesselClassification.PASSENGER

        if 20 <= length_m < 50:
            if ratio < 3:
                return VesselClassification.FISHING
            if 3 <= ratio <= 6:
                return VesselClassification.PATROL
            return VesselClassification.TUG

        if length_m < 20:
            if ratio < 2.2:
                return VesselClassification.YACHT
            if ratio < 3:
                return VesselClassification.FISHING
            return VesselClassification.UNKNOWN

        return VesselClassification.UNKNOWN

    def classify_batch(self, detections: List[SARDetection]) -> List[VesselClassification]:
        return [self.classify(det) for det in detections]

    def enrich_from_ais(self, detection: SARDetection, ais_vessel: Optional[Dict] = None) -> Dict:
        classification = self.classify(detection)
        enriched = detection.to_dict()
        enriched["classification"] = classification.value
        if ais_vessel:
            ais_class = str(ais_vessel.get("classification", "")).upper()
            if ais_class in VesselClassification.__members__:
                classification = VesselClassification[ais_class]
                enriched["classification"] = classification.value
            enriched["ais_match"] = ais_vessel
        else:
            enriched["ais_match"] = None
        enriched["llm_refined"] = self._llm_available
        return enriched
