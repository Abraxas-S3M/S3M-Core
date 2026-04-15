"""Capability and partner registry for interoperability components."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List


class InteropRegistry:
    """Stores capability declarations and coalition partner code tables."""

    def __init__(self):
        self.capabilities: Dict[str, Dict[str, object]] = {}
        self.exercise_sessions: Dict[int, dict] = {}
        self._register_default_capabilities()

    def _register_default_capabilities(self) -> None:
        capabilities = {
            "dis": ("IEEE-1278.1", ["entity_state_pdu", "dead_reckoning", "exercise_control_pdus"]),
            "c2sim": ("1.1", ["order_exchange", "report_exchange", "offline_outbox"]),
            "bml": ("SISO-BML", ["sitrep_generation", "aar_reporting", "order_parsing"]),
            "msdl": ("1.0", ["scenario_import", "scenario_export"]),
            "cot": ("2.0", ["tak_multicast", "track_publish", "track_ingest"]),
            "nffi": ("STANAG-5527-1.4", ["blue_force_publish", "coalition_track_ingest", "offline_outbox"]),
            "symbology": ("MIL-STD-2525D", ["sidc_generation", "cot_sidc_mapping", "dis_sidc_mapping"]),
            "mtf": ("APP-11(D)", ["xml_message_formatting", "dtg_generation", "offline_message_queue"]),
            "taxii": ("2.1", ["stix_bundle_publish", "stix_bundle_poll", "offline_outbox", "offline_inbox_cache"]),
            "nsili": (
                "STANAG-4559-Ed3",
                [
                    "local_catalog_query",
                    "local_product_retrieval",
                    "offline_xml_export",
                    "partner_catalog_sync_phase1",
                ],
            ),
            "jreap": ("JREAP-C", ["j_series_ingest", "cot_crossfeed", "dis_crossfeed"]),
            "oth_gold": ("3.0", ["maritime_track_publish", "maritime_track_ingest"]),
            "hla": ("IEEE-1516-2010", ["rpr_fom_2.0", "stub_rti", "dis_bridge", "time_management"]),
            "mip": ("MIP-4.3", ["dem_handshake", "cop_oig_publish", "offline_oig_outbox"]),
            "nvg": ("NVG-2.0", ["cop_overlay_publish", "overlay_import", "geojson_bridge"]),
            "uas4586": ("STANAG-4586", ["vehicle_status", "payload_status", "isr_product", "cot_crossfeed"]),
            "fmv": ("STANAG-4609", ["misb_0601_klv", "metadata_parse", "nsili_registration"]),
            "fmn_security": ("FMN-Profile", ["nato_security_label", "release_policy", "interop_message_labeling"]),
            "ogc": ("OGC-WMS-WFS", ["geojson_transform", "nvg_bridge", "wfs_feature_exchange"]),
            "link22": ("STANAG-5522", ["f_series_contract", "track_stub_publish", "future_transport_stub"]),
        }
        for protocol, declaration in capabilities.items():
            version, features = declaration
            self.register_capability(protocol, version, features)

    def register_capability(self, protocol, version, features: List[str]):
        self.capabilities[str(protocol).lower()] = {
            "protocol": str(protocol),
            "version": str(version),
            "features": list(features),
        }

    def get_capabilities(self) -> dict:
        return dict(self.capabilities)

    def get_gcc_partner_codes(self) -> dict:
        return {
            "Saudi Arabia": 178,
            "UAE": 223,
            "Kuwait": 117,
            "Bahrain": 16,
            "Qatar": 164,
            "Oman": 154,
        }

    def get_nato_partner_codes(self) -> dict:
        return {
            "United States": 225,
            "United Kingdom": 224,
            "France": 71,
            "Germany": 78,
            "Italy": 105,
            "Spain": 198,
            "Turkey": 222,
            "Canada": 39,
            "Netherlands": 145,
            "Norway": 146,
        }

    def get_iso3_codes(self) -> dict:
        """Return numeric country-code to ISO3 mapping for GCC and NATO partners."""
        return {
            178: "SAU",
            223: "ARE",
            117: "KWT",
            16: "BHR",
            164: "QAT",
            154: "OMN",
            225: "USA",
            224: "GBR",
            71: "FRA",
            78: "DEU",
            105: "ITA",
            198: "ESP",
            222: "TUR",
            39: "CAN",
            145: "NLD",
            146: "NOR",
        }

    def get_all_partner_codes(self) -> dict:
        merged = dict(self.get_gcc_partner_codes())
        merged.update(self.get_nato_partner_codes())
        return merged

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "capability_count": len(self.capabilities),
            "exercise_sessions": len(self.exercise_sessions),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

