from datetime import datetime, timezone

from packages.schemas.common.base import GeoPoint, Provenance
from packages.schemas.event_intel.models import NormalizedGlobalEvent
from packages.schemas.flight.models import NormalizedFlightTrack
from packages.schemas.geospatial.models import NormalizedGeoObservation
from packages.schemas.maritime.models import NormalizedVesselTrack
from packages.schemas.terrain.models import NormalizedMapLayer
from packages.schemas.threat_intel.models import NormalizedThreatIndicator
from packages.schemas.weather.models import NormalizedWeatherObservation


def test_all_schema_models_instantiate_without_error():
    provenance = Provenance(
        provider_id="mock",
        provider_name="Mock",
        fetched_at=datetime.now(timezone.utc),
        raw_id="1",
        confidence=0.9,
        classification="UNCLASSIFIED",
    )

    NormalizedGeoObservation(provenance=provenance)
    NormalizedThreatIndicator(provenance=provenance)
    NormalizedGlobalEvent(provenance=provenance)
    NormalizedVesselTrack(provenance=provenance)
    NormalizedFlightTrack(provenance=provenance)
    NormalizedWeatherObservation(provenance=provenance)
    NormalizedMapLayer(provenance=provenance)

    assert GeoPoint(lat=1.0, lon=2.0).crs == "EPSG:4326"
