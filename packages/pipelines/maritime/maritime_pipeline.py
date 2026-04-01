"""Maritime fusion pipeline bridging external maritime APIs into Phase 15."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from connectors.local_storage import LocalStorage
from integration_sdk.base.provider_adapter import OperatingMode, ProviderCategory
from integration_sdk.registry.provider_registry import ProviderRegistry
from packages.pipelines.batch.batch_ingestion import BatchIngestionRunner
from packages.pipelines.deduplication.dedup_engine import HashBasedDeduplicator
from packages.pipelines.entity_resolution.entity_resolver import CrossProviderEntityResolver
from packages.providers.maritime_marinetraffic.adapter import MarineTrafficAdapter
from packages.providers.maritime_spire.adapter import SpireMaritimeAdapter
from packages.providers.maritime_vesselfinder.adapter import VesselFinderAdapter
from packages.providers.maritime_windward.adapter import WindwardAdapter
from packages.schemas.maritime.models import NormalizedVesselTrack
from services.sensor_analytics.border.surveillance_engine import BorderSurveillanceEngine
from services.sensor_analytics.models import BorderAlert


class MaritimeFusionPipeline:
    def __init__(self, mode: OperatingMode = OperatingMode.AIRGAPPED) -> None:
        self.registry = ProviderRegistry()
        self.registry.register(MarineTrafficAdapter)
        self.registry.register(VesselFinderAdapter)
        self.registry.register(SpireMaritimeAdapter)
        self.registry.register(WindwardAdapter)
        for pid in [
            "maritime-marinetraffic",
            "maritime-vesselfinder",
            "maritime-spire",
            "maritime-windward",
        ]:
            self.registry.set_mode(pid, mode)

        self.storage = LocalStorage(root_dir="data/integrations")
        self.batch_runner = BatchIngestionRunner(self.registry, self.storage)
        self.deduplicator = HashBasedDeduplicator()
        self.entity_resolver = CrossProviderEntityResolver(key_fields=["mmsi"])

        self.mt = self.registry.get("maritime-marinetraffic")
        self.vf = self.registry.get("maritime-vesselfinder")
        self.sp = self.registry.get("maritime-spire")
        self.ww = self.registry.get("maritime-windward")
        self.border_engine = BorderSurveillanceEngine()

        self._last_vessels: list[NormalizedVesselTrack] = []
        self._last_dark: list[dict[str, Any]] = []
        self._last_by_zone: dict[str, Any] = {}
        self._last_by_provider: dict[str, int] = {}

    def _merge_tracks(self, tracks: list[NormalizedVesselTrack]) -> list[NormalizedVesselTrack]:
        by_mmsi: dict[str, NormalizedVesselTrack] = {}
        for item in tracks:
            if not item.mmsi:
                continue
            prev = by_mmsi.get(item.mmsi)
            if prev is None:
                by_mmsi[item.mmsi] = item
                continue

            # Tactical context: freshest position is mission-critical for intercept decisions.
            if item.timestamp >= prev.timestamp:
                prev.geo_point = item.geo_point
                prev.timestamp = item.timestamp
                prev.speed_knots = item.speed_knots
                prev.course_deg = item.course_deg
                prev.heading_deg = item.heading_deg

            if prev.vessel_type in {"", "Unknown"} and item.vessel_type not in {"", "Unknown"}:
                prev.vessel_type = item.vessel_type
            if not prev.vessel_name and item.vessel_name:
                prev.vessel_name = item.vessel_name
            if not prev.destination and item.destination:
                prev.destination = item.destination
            if prev.length_m is None and item.length_m is not None:
                prev.length_m = item.length_m
            if prev.draught_m is None and item.draught_m is not None:
                prev.draught_m = item.draught_m

            tags = set(prev.tags)
            tags.update(item.tags)
            prev.tags = sorted(tags)
            prev.is_dark = prev.is_dark or item.is_dark

        deduped = self.deduplicator.deduplicate(list(by_mmsi.values()))
        return deduped

    def ingest_all_zones(self, timespan_minutes: int = 60) -> dict[str, Any]:
        mt_data = self.mt.fetch_all_saudi_zones(timespan_minutes=timespan_minutes)
        vf_data = self.vf.fetch_all_saudi_zones()
        sp_data = self.sp.fetch_all_saudi_zones()

        mt_tracks = self.mt.normalizer.normalize_batch(mt_data.get("vessels", []))
        vf_tracks = self.vf.normalizer.normalize_batch(vf_data.get("vessels", []))
        sp_tracks = self.sp.normalizer.normalize_batch(sp_data.get("vessels", []))

        all_tracks = mt_tracks + vf_tracks + sp_tracks
        merged = self._merge_tracks(all_tracks)

        sp_satellite_mmsi = {
            t.mmsi
            for t in sp_tracks
            if any(tag in {"collection:satellite", "collection:mixed"} for tag in t.tags)
        }
        satellite_confirmed = 0
        for vessel in merged:
            if vessel.mmsi in sp_satellite_mmsi:
                if "satellite_confirmed" not in vessel.tags:
                    vessel.tags.append("satellite_confirmed")
                satellite_confirmed += 1

        out_dir = Path("data/integrations/maritime-merged")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"maritime_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        out_path.write_text(
            json.dumps({"vessels": [asdict(v) for v in merged]}, default=str, indent=2),
            encoding="utf-8",
        )

        dedup_count = len(all_tracks) - len(merged)
        self._last_vessels = merged
        self._last_by_zone = mt_data.get("by_zone", {})
        self._last_by_provider = {
            "maritime-marinetraffic": len(mt_tracks),
            "maritime-vesselfinder": len(vf_tracks),
            "maritime-spire": len(sp_tracks),
        }

        return {
            "total_vessels": len(merged),
            "by_zone": self._last_by_zone,
            "by_provider": self._last_by_provider,
            "satellite_confirmed": satellite_confirmed,
            "dedup_count": dedup_count,
        }

    def enrich_with_risk(self, vessels: list[NormalizedVesselTrack]) -> list[NormalizedVesselTrack]:
        high_risk_zones = {"bab_el_mandeb", "strait_of_hormuz", "gulf_of_aden"}
        targets: list[NormalizedVesselTrack] = []
        for vessel in vessels:
            zones = {tag.split(":", 1)[1] for tag in vessel.tags if tag.startswith("zone:")}
            if zones.intersection(high_risk_zones):
                targets.append(vessel)

        if not targets:
            # Fallback to top-activity vessels when zone tags are unavailable.
            targets = [v for v in vessels if v.mmsi][: min(20, len(vessels))]

        screen = self.ww.screen_fleet([v.mmsi for v in targets if v.mmsi])
        risk_map = {str(item.get("mmsi")): item for item in screen.get("results", [])}
        for vessel in vessels:
            profile = risk_map.get(vessel.mmsi)
            if not profile:
                continue
            vessel.tags.append(f"risk_level:{profile.get('risk_level', 'unknown')}")
            vessel.tags.append(f"risk_score:{profile.get('risk_score', 0)}")
            for ind in profile.get("risk_indicators", []):
                if ind.get("type"):
                    vessel.tags.append(f"indicator:{ind['type']}")
            if any(ind.get("type") == "dark_activity" and int(ind.get("score", 0) or 0) > 50 for ind in profile.get("risk_indicators", [])):
                vessel.is_dark = True
            setattr(vessel, "risk_score", int(profile.get("risk_score", 0) or 0))

        return vessels

    def detect_dark_vessels(self) -> list[dict[str, Any]]:
        mt_all = self.mt.fetch_all_saudi_zones(60)
        vf_all = self.vf.fetch_all_saudi_zones()
        gaps = self.mt.fetch_ais_gap_events(days_back=7)
        gap_pairs = self.mt.normalizer.detect_ais_gaps(gaps.get("gaps", []))
        gap_map = {g["mmsi"]: g for g in gap_pairs}

        mt_set = {str(v.get("MMSI")) for v in mt_all.get("vessels", [])}
        vf_set = {str(v.get("AIS", {}).get("MMSI")) for v in vf_all.get("vessels", [])}
        terrestrial = mt_set.union(vf_set)

        satellite_only = self.sp.detect_satellite_only_vessels("persian_gulf")
        risk = self.ww.screen_saudi_zones()
        dark_risk_mmsi = {str(item.get("mmsi")) for item in risk.get("dark_activity", [])}

        dark: list[dict[str, Any]] = []
        for vessel in satellite_only:
            mmsi = str(vessel.get("mmsi", ""))
            if not mmsi:
                continue
            source = "satellite_only"
            if mmsi in gap_map:
                source = "ais_gap+satellite"
            if mmsi in dark_risk_mmsi:
                source = "windward_dark_activity"
            pos = vessel.get("position", {})
            dark.append(
                {
                    "mmsi": mmsi,
                    "vessel_name": vessel.get("name"),
                    "dark_source": source,
                    "last_known_position": {"lat": pos.get("latitude", 0.0), "lon": pos.get("longitude", 0.0)},
                    "gap_duration_hours": gap_map.get(mmsi, {}).get("duration_hours", 0.0),
                    "risk_level": "high" if mmsi in dark_risk_mmsi else "medium",
                }
            )

        for mmsi, gap in gap_map.items():
            if mmsi in {d["mmsi"] for d in dark}:
                continue
            if mmsi in terrestrial:
                dark.append(
                    {
                        "mmsi": mmsi,
                        "vessel_name": "unknown",
                        "dark_source": "ais_gap_event",
                        "last_known_position": gap.get("last_known_position", {"lat": 0.0, "lon": 0.0}),
                        "gap_duration_hours": gap.get("duration_hours", 0.0),
                        "risk_level": "high" if mmsi in dark_risk_mmsi else "medium",
                    }
                )

        self._last_dark = dark
        return dark

    def feed_to_phase15(self, vessels: list[NormalizedVesselTrack]) -> str:
        out_dir = Path("data/ais")
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / f"api_ingest_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
        with file_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "MMSI",
                    "timestamp",
                    "message_type",
                    "lat",
                    "lon",
                    "speed",
                    "course",
                    "heading",
                    "vessel_name",
                    "vessel_type",
                    "destination",
                    "nav_status",
                ],
            )
            writer.writeheader()
            for vessel in vessels:
                writer.writerow(
                    {
                        "MMSI": vessel.mmsi,
                        "timestamp": vessel.timestamp.isoformat(),
                        "message_type": 1,
                        "lat": vessel.geo_point.lat if vessel.geo_point else 0.0,
                        "lon": vessel.geo_point.lon if vessel.geo_point else 0.0,
                        "speed": vessel.speed_knots,
                        "course": vessel.course_deg,
                        "heading": vessel.heading_deg,
                        "vessel_name": vessel.vessel_name,
                        "vessel_type": 80 if "tanker" in vessel.vessel_type.lower() else 70,
                        "destination": vessel.destination or "",
                        "nav_status": 0,
                    }
                )
        return str(file_path)

    def feed_dark_vessels_to_border_surveillance(self, dark_vessels: list[dict[str, Any]]) -> list[Any]:
        alerts: list[BorderAlert] = []
        for idx, item in enumerate(dark_vessels, start=1):
            pos = item.get("last_known_position", {})
            alerts.append(
                BorderAlert(
                    alert_id=f"maritime-dark-{idx}",
                    zone_id="ZONE-ADEN",
                    timestamp=datetime.now(timezone.utc),
                    alert_type="dark_vessel",
                    severity="high",
                    position=(float(pos.get("lat", 0.0)), float(pos.get("lon", 0.0))),
                    description=f"Dark vessel indicator from {item.get('dark_source', 'fusion')}",
                    vessel_id=item.get("mmsi"),
                    confidence=0.9,
                    evidence=[item],
                )
            )
        return self.border_engine.feed_to_threat_detection(alerts)

    def get_chokepoint_status(self) -> dict[str, Any]:
        if not self._last_vessels:
            self.ingest_all_zones(60)
        if not self._last_dark:
            self.detect_dark_vessels()

        def summarize(zone_key: str) -> dict[str, Any]:
            zone_vessels = [v for v in self._last_vessels if any(zone_key in tag for tag in v.tags)]
            tankers = [v for v in zone_vessels if "tanker" in v.vessel_type.lower()]
            dark = [d for d in self._last_dark if d.get("last_known_position")]
            high_risk = [v for v in zone_vessels if any(tag.startswith("risk_level:high") or tag.startswith("risk_level:critical") for tag in v.tags)]
            flow = {"eastbound": 0, "westbound": 0}
            for v in zone_vessels:
                if 0 <= v.course_deg < 180:
                    flow["eastbound"] += 1
                else:
                    flow["westbound"] += 1
            payload = {
                "vessels": len(zone_vessels),
                "tankers": len(tankers),
                "dark": len(dark),
                "high_risk": len(high_risk),
                "flow_direction": flow,
            }
            if zone_key == "gulf_of_aden":
                payload["recent_alerts"] = self.ww.fetch_alerts(zone="bab_el_mandeb", severity="high", days_back=7).get("alerts", [])
            return payload

        return {
            "strait_of_hormuz": summarize("strait_of_hormuz"),
            "bab_el_mandeb": summarize("bab_el_mandeb"),
            "gulf_of_aden": summarize("gulf_of_aden"),
        }

    def health_check(self) -> dict[str, Any]:
        providers = {
            "maritime-marinetraffic": self.mt.health_check(),
            "maritime-vesselfinder": self.vf.health_check(),
            "maritime-spire": self.sp.health_check(),
            "maritime-windward": self.ww.health_check(),
        }
        return {
            "status": "ok",
            "providers": providers,
            "total_registered": len(self.registry.get_all(category=ProviderCategory.MARITIME)),
        }
