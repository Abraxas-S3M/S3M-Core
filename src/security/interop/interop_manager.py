"""Multi-protocol security interoperability manager for S3M."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from services.interop.cot import CotBridge, CotEventFactory, CotTransport
from services.interop.fmn_security import FMNSecurityManager
from services.interop.fmv import FMVMetadataBuilder
from services.interop.hla import DISHLABridge, HLAFederateAdapter
from services.interop.jreap import JREAPBridge
from services.interop.link22 import Link22Adapter
from services.interop.mip import MIPGateway
from services.interop.mtf import MTFFormatter, MTFTransport
from services.interop.nffi import NFFIGateway, NFFIMessageBuilder
from services.interop.nsili import NSILICatalog
from services.interop.nvg import NVGOverlayExchange, NVGParser
from services.interop.ogc import GeoJSONAdapter
from services.interop.oth import OTHGoldAdapter
from services.interop.stix import TAXIIClient
from services.interop.uas4586 import UAS4586Interface
from src.security.interop.bml_adapter import BMLAdapter
from src.security.interop.c2sim_adapter import C2SIMAdapter
from src.security.interop.dis_adapter import DISAdapter


class InteropManager:
    """Coordinates coalition interoperability adapters under a single control surface."""

    SUPPORTED_PROTOCOLS = (
        "dis",
        "c2sim",
        "bml",
        "cot",
        "nffi",
        "mtf",
        "taxii",
        "jreap",
        "oth_gold",
        "hla",
        "mip",
        "nvg",
        "nsili",
        "uas4586",
        "fmv",
        "fmn_security",
        "ogc",
        "link22",
    )

    def __init__(self) -> None:
        self.dis_adapter = DISAdapter()
        self.c2sim_adapter = C2SIMAdapter()
        self.bml_adapter = BMLAdapter()

        self._cot_transport = CotTransport({})
        self._cot_event_factory = CotEventFactory({})
        self.cot_bridge = CotBridge(self._cot_transport, self._cot_event_factory)

        self.nffi_builder = NFFIMessageBuilder()
        self.nffi_gateway = NFFIGateway(config={}, message_builder=self.nffi_builder)

        self.mtf_formatter = MTFFormatter()
        self.mtf_transport = MTFTransport()

        self.taxii_client = TAXIIClient(server_url="http://localhost", collection_id="default")
        self.jreap_bridge = JREAPBridge({"jreap": {}})
        self.oth_adapter = OTHGoldAdapter()
        self.hla_adapter = HLAFederateAdapter({"rti_type": "stub", "time_step_seconds": 0.1})
        self.hla_dis_bridge = DISHLABridge(self.hla_adapter)
        self.mip_gateway = MIPGateway(config={})
        self.nvg_exchange = NVGOverlayExchange(config={})
        self.nvg_parser = NVGParser({})
        self.nsili_catalog = NSILICatalog({"catalog_dir": "data/interop/nsili_catalog/"})
        self.uas4586 = UAS4586Interface(config={"max_loi": 3, "registered_uavs": []})
        self.fmv_builder = FMVMetadataBuilder(config={"register_in_nsili": True})
        self.fmn_security = FMNSecurityManager({"enforce_labels": False})
        self.geojson_adapter = GeoJSONAdapter()
        self.link22_adapter = Link22Adapter({"mode": "stub"})

        self._status: Dict[str, Dict[str, Any]] = {
            protocol: self._new_status(connected=(protocol == "bml")) for protocol in self.SUPPORTED_PROTOCOLS
        }
        self._history: List[Dict[str, Any]] = []

    @staticmethod
    def _new_status(*, connected: bool = False) -> Dict[str, Any]:
        return {
            "enabled": False,
            "connected": bool(connected),
            "messages_sent": 0,
            "messages_received": 0,
        }

    @staticmethod
    def _protocol_cfg(config: dict[str, Any], protocol: str) -> dict[str, Any]:
        nested = config.get(protocol)
        if isinstance(nested, dict):
            return dict(nested)
        return dict(config)

    def _label_outgoing_data(self, data: Any) -> Any:
        """Apply FMN coalition label to outbound payload history records."""
        if not self._status.get("fmn_security", {}).get("enabled", False):
            return data
        try:
            serialized = data if isinstance(data, str) else json.dumps(data, ensure_ascii=True, default=str)
            classification = str(self.fmn_security.default_label.classification)
            releasable_to = list(self.fmn_security.default_label.releasable_to) or ["SAU"]
            return self.fmn_security.label_message(serialized, classification, releasable_to)
        except Exception:
            return data

    def _record(self, protocol: str, direction: str, message_type: str, data: Any, raw: str = "") -> None:
        payload = self._label_outgoing_data(data) if direction == "outbound" else data
        self._history.append(
            {
                "protocol": protocol,
                "direction": direction,
                "message_type": message_type,
                "data": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "raw": raw,
            }
        )
        if len(self._history) > 5000:
            self._history = self._history[-5000:]

    def enable_protocol(self, protocol: str, config: dict | None = None) -> bool:
        protocol = protocol.lower().strip()
        raw_config = dict(config or {})
        cfg = self._protocol_cfg(raw_config, protocol)

        if protocol == "dis":
            self.dis_adapter = DISAdapter(
                exercise_id=int(cfg.get("exercise_id", 1)),
                site_id=int(cfg.get("site_id", 1)),
                app_id=int(cfg.get("app_id", 1)),
                broadcast_address=str(cfg.get("broadcast_address", "255.255.255.255")),
                port=int(cfg.get("port", 3000)),
            )
            ok = self.dis_adapter.connect()
            self._status["dis"]["enabled"] = True
            self._status["dis"]["connected"] = ok
            return ok

        if protocol == "c2sim":
            self.c2sim_adapter = C2SIMAdapter(
                server_url=cfg.get("server_url"),
                namespace=str(cfg.get("namespace", "http://www.sisostds.org/schemas/C2SIM/1.1")),
            )
            ok = self.c2sim_adapter.connect(cfg.get("server_url"))
            self._status["c2sim"]["enabled"] = True
            self._status["c2sim"]["connected"] = ok
            return ok

        if protocol == "bml":
            self._status["bml"]["enabled"] = True
            self._status["bml"]["connected"] = True
            return True

        if protocol == "cot":
            self._cot_transport = CotTransport(cfg)
            self._cot_event_factory = CotEventFactory(cfg)
            self.cot_bridge = CotBridge(self._cot_transport, self._cot_event_factory)
            mode = str(cfg.get("transport", "multicast")).strip().lower()
            if mode in {"tak", "tak_server"}:
                ok = self._cot_transport.connect_tak_server(str(cfg.get("tak_server_url", "")).strip())
            elif mode in {"offline", "none"}:
                ok = True
            else:
                ok = self._cot_transport.connect_multicast()
            self._status["cot"]["enabled"] = True
            self._status["cot"]["connected"] = bool(ok and self._cot_transport.connected)
            return bool(ok)

        if protocol == "nffi":
            nffi_cfg = {
                "transport_profile": str(cfg.get("transport_profile", "IP-1")),
                "gateway_url": cfg.get("gateway_url"),
                "publish_interval_seconds": int(cfg.get("publish_interval_seconds", 10)),
                "track_source_country": str(cfg.get("track_source_country", "SAU")),
                "system_id": str(cfg.get("system_id", "S3M-FALCON")),
                "outbox_dir": str(cfg.get("outbox_dir", "data/interop/nffi_outbox/")),
                "inbox_dir": str(cfg.get("inbox_dir", "data/interop/nffi_inbox/")),
                "stale_threshold_seconds": int(cfg.get("stale_threshold_seconds", 300)),
                "multicast_group": str(cfg.get("multicast_group", "239.2.3.1")),
                "multicast_port": int(cfg.get("multicast_port", 4571)),
            }
            self.nffi_builder = NFFIMessageBuilder()
            self.nffi_gateway = NFFIGateway(config=nffi_cfg, message_builder=self.nffi_builder)
            ok = self.nffi_gateway.connect(nffi_cfg.get("gateway_url"))
            self._status["nffi"]["enabled"] = True
            self._status["nffi"]["connected"] = ok
            # Offline outbox mode remains a valid enabled state in disconnected operations.
            return True

        if protocol == "mtf":
            self.mtf_formatter = MTFFormatter(config=cfg)
            self.mtf_transport = MTFTransport(gateway_url=cfg.get("gateway_url"))
            ok = self.mtf_transport.connect(cfg.get("gateway_url")) if cfg.get("gateway_url") else False
            self._status["mtf"]["enabled"] = True
            self._status["mtf"]["connected"] = bool(ok)
            # Tactical message generation works offline through queueing even when disconnected.
            return True

        if protocol == "taxii":
            server_url = str(cfg.get("server_url", "http://localhost")).strip() or "http://localhost"
            collection_id = str(cfg.get("collection_id", "default")).strip() or "default"
            self.taxii_client = TAXIIClient(
                server_url=server_url,
                collection_id=collection_id,
                auth=cfg.get("auth") if isinstance(cfg.get("auth"), dict) else {},
                outbox_dir=str(cfg.get("outbox_dir", "data/interop/taxii_outbox/")),
                inbox_dir=str(cfg.get("inbox_dir", "data/interop/taxii_inbox/")),
            )
            ok = False
            try:
                self.taxii_client.discover()
                ok = True
            except Exception:
                ok = False
            self._status["taxii"]["enabled"] = True
            # Offline TAXII queueing is a valid enabled state in air-gapped operations.
            self._status["taxii"]["connected"] = bool(self.taxii_client.connected)
            return True

        if protocol == "jreap":
            jreap_cfg = {
                "listen_port": int(cfg.get("listen_port", 5555)),
                "supported_j_series": cfg.get("supported_j_series", ["J2.2", "J3.2", "J3.5", "J13.2"]),
            }
            self.jreap_bridge = JREAPBridge({"jreap": jreap_cfg})
            auto_start = bool(cfg.get("auto_start", True))
            ok = True
            if auto_start:
                ok = self.jreap_bridge.start_listener(int(jreap_cfg["listen_port"]))
            self._status["jreap"]["enabled"] = True
            self._status["jreap"]["connected"] = bool(self.jreap_bridge.running)
            return True

        if protocol == "oth_gold":
            self.oth_adapter = OTHGoldAdapter()
            gateway_url = str(cfg.get("gateway_url", "")).strip()
            ok = self.oth_adapter.connect(gateway_url) if gateway_url else False
            self._status["oth_gold"]["enabled"] = True
            self._status["oth_gold"]["connected"] = bool(ok and self.oth_adapter.connected)
            return True

        if protocol == "hla":
            hla_cfg = {
                "rti_type": str(cfg.get("rti_type", "stub")),
                "rti_host": str(cfg.get("rti_host", "localhost")),
                "rti_port": int(cfg.get("rti_port", 11000)),
                "federation_name": str(cfg.get("federation_name", "S3M_Coalition")),
                "fom_path": str(cfg.get("fom_path", "configs/interop/s3m_fom.xml")),
                "time_step_seconds": float(cfg.get("time_step_seconds", 0.1)),
            }
            self.hla_adapter = HLAFederateAdapter(hla_cfg)
            self.hla_dis_bridge = DISHLABridge(self.hla_adapter)
            created = self.hla_adapter.create_federation(
                hla_cfg["federation_name"],
                hla_cfg["fom_path"],
            )
            joined = self.hla_adapter.join_federation(hla_cfg["federation_name"]) if created else False
            if joined:
                self.hla_adapter.publish_object_class("Aircraft", ["Position", "Velocity", "Marking"])
                self.hla_adapter.subscribe_object_class("Aircraft", ["Position", "Velocity", "Marking"])
            self._status["hla"]["enabled"] = True
            self._status["hla"]["connected"] = bool(created and joined)
            return True

        if protocol == "mip":
            mip_cfg = {
                "baseline": str(cfg.get("baseline", "4.3")),
                "data_model": str(cfg.get("data_model", "MIM")),
                "gateway_url": cfg.get("gateway_url"),
                "oig_categories": cfg.get("oig_categories", ["operations", "intelligence", "logistics", "plans", "cop"]),
                "publish_interval_seconds": int(cfg.get("publish_interval_seconds", 10)),
                "outbox_dir": str(cfg.get("outbox_dir", "data/interop/mip_outbox/")),
                "inbox_dir": str(cfg.get("inbox_dir", "data/interop/mip_inbox/")),
            }
            self.mip_gateway = MIPGateway(config=mip_cfg)
            partner_gateway_url = str(cfg.get("partner_gateway_url", "")).strip()
            connected = self.mip_gateway.connect(partner_gateway_url) if partner_gateway_url else False
            self._status["mip"]["enabled"] = True
            self._status["mip"]["connected"] = bool(connected)
            return True

        if protocol == "nvg":
            nvg_cfg = {
                "version": str(cfg.get("version", "2.0")),
                "namespace": str(cfg.get("namespace", "http://tide.act.nato.int/schemas/2012/10/nvg")),
                "publish_interval_seconds": int(cfg.get("publish_interval_seconds", 10)),
                "outbox_dir": str(cfg.get("outbox_dir", "data/interop/nvg_outbox/")),
            }
            self.nvg_exchange = NVGOverlayExchange(config=nvg_cfg)
            self.nvg_parser = NVGParser(nvg_cfg)
            self._status["nvg"]["enabled"] = True
            self._status["nvg"]["connected"] = True
            return True

        if protocol == "nsili":
            nsili_cfg = {
                "catalog_dir": str(cfg.get("catalog_dir", "data/interop/nsili_catalog/")),
                "max_products": int(cfg.get("max_products", 10000)),
                "default_classification": str(cfg.get("default_classification", "UNCLASSIFIED")),
                "partner_catalogs": cfg.get("partner_catalogs", []),
            }
            self.nsili_catalog = NSILICatalog(nsili_cfg)
            self._status["nsili"]["enabled"] = True
            self._status["nsili"]["connected"] = True
            return True

        if protocol == "uas4586":
            uas_cfg = {
                "max_loi": int(cfg.get("max_loi", 3)),
                "publish_interval_seconds": int(cfg.get("publish_interval_seconds", 1)),
                "registered_uavs": cfg.get("registered_uavs", []),
            }
            self.uas4586 = UAS4586Interface(config=uas_cfg)
            self._status["uas4586"]["enabled"] = True
            self._status["uas4586"]["connected"] = True
            return True

        if protocol == "fmv":
            self.fmv_builder = FMVMetadataBuilder(
                config={
                    "klv_standard": str(cfg.get("klv_standard", "MISB_0601")),
                    "embed_in_stream": bool(cfg.get("embed_in_stream", False)),
                    "register_in_nsili": bool(cfg.get("register_in_nsili", True)),
                }
            )
            self._status["fmv"]["enabled"] = True
            self._status["fmv"]["connected"] = True
            return True

        if protocol == "fmn_security":
            self.fmn_security = FMNSecurityManager(dict(cfg))
            self._status["fmn_security"]["enabled"] = True
            self._status["fmn_security"]["connected"] = True
            return True

        if protocol == "ogc":
            self.geojson_adapter = GeoJSONAdapter()
            self._status["ogc"]["enabled"] = True
            self._status["ogc"]["connected"] = True
            return True

        if protocol == "link22":
            link22_cfg = {
                "mode": str(cfg.get("mode", "stub")),
            }
            self.link22_adapter = Link22Adapter(link22_cfg)
            endpoint = str(cfg.get("network_address", "")).strip()
            connected = self.link22_adapter.connect(endpoint) if endpoint else False
            self._status["link22"]["enabled"] = True
            self._status["link22"]["connected"] = bool(connected)
            return True

        return False

    def disable_protocol(self, protocol: str) -> None:
        protocol = protocol.lower().strip()
        if protocol == "dis":
            self.dis_adapter.disconnect()
        elif protocol == "c2sim":
            self.c2sim_adapter.disconnect()
        elif protocol == "cot":
            self._cot_transport.disconnect()
        elif protocol == "nffi":
            self.nffi_gateway.disconnect()
        elif protocol == "mtf":
            self.mtf_transport.disconnect()
        elif protocol == "taxii":
            self.taxii_client.connected = False
        elif protocol == "jreap":
            self.jreap_bridge.stop_listener()
        elif protocol == "oth_gold":
            self.oth_adapter.disconnect()
        elif protocol == "hla":
            self.hla_adapter.resign_federation()
        elif protocol == "mip":
            self.mip_gateway.disconnect()
        elif protocol == "nvg":
            self.nvg_exchange.stop_streaming()
        elif protocol == "link22":
            self.link22_adapter = Link22Adapter({"mode": "stub"})

        if protocol in self._status:
            self._status[protocol]["enabled"] = False
            self._status[protocol]["connected"] = False

    def get_protocol_status(self) -> dict:
        return {protocol: dict(state) for protocol, state in self._status.items()}

    def send_entity_update(self, entity: Any) -> dict:
        result = {
            "dis": False,
            "c2sim": False,
            "cot": False,
            "nffi": False,
            "hla": False,
            "mip": False,
            "nvg": False,
            "ogc": False,
        }
        entity_dict = entity if isinstance(entity, dict) else self.dis_adapter.sim_entity_to_dis(entity)

        if self._status["dis"]["enabled"] and self._status["dis"]["connected"]:
            ok = self.dis_adapter.send_entity_update(entity_dict)
            result["dis"] = ok
            if ok:
                self._status["dis"]["messages_sent"] += 1
                self._record("dis", "outbound", "entity_state", entity_dict)

        if self._status["c2sim"]["enabled"]:
            xml = self.c2sim_adapter.entity_to_position_report(entity_dict)
            ok = self.c2sim_adapter.send_message(xml)
            result["c2sim"] = ok
            if ok:
                self._status["c2sim"]["messages_sent"] += 1
                self._record("c2sim", "outbound", "position_report", entity_dict, raw=xml)

        # Tactical crossfeed: once DIS sends a track, emit coalition-friendly CoT/NFFI mirrors.
        interop_track = self._entity_to_interop_track(entity_dict)
        if self._status["cot"]["enabled"]:
            result["cot"] = self.send_cot_tracks([interop_track]) > 0
        if self._status["nffi"]["enabled"]:
            result["nffi"] = self.send_nffi_tracks([interop_track]) > 0
        if self._status["hla"]["enabled"]:
            try:
                self.hla_dis_bridge.sync_from_dis(entity_dict)
                result["hla"] = True
                self._status["hla"]["messages_sent"] += 1
                self._record("hla", "outbound", "dis_entity_sync", {"entity_id": str(entity_dict.get("entity_id", ""))})
            except Exception:
                result["hla"] = False
        geo_crossfeed = self._crossfeed_geo_formats([interop_track])
        result["mip"] = bool(geo_crossfeed.get("mip"))
        result["nvg"] = bool(geo_crossfeed.get("nvg"))
        result["ogc"] = bool(geo_crossfeed.get("ogc"))

        return result

    def send_mission(self, mission: Any) -> dict:
        accepted = {"c2sim": False}
        if self._status["c2sim"]["enabled"]:
            xml = self.c2sim_adapter.mission_to_order(mission)
            ok = self.c2sim_adapter.send_message(xml)
            accepted["c2sim"] = ok
            if ok:
                self._status["c2sim"]["messages_sent"] += 1
                self._record(
                    "c2sim",
                    "outbound",
                    "order",
                    {"mission": str(getattr(mission, "mission_id", "unknown"))},
                    raw=xml,
                )
        return accepted

    def send_aar(self, aar: Any) -> dict:
        accepted = {"c2sim": False, "bml": False}
        if self._status["c2sim"]["enabled"]:
            xml = self.c2sim_adapter.aar_to_report(aar)
            ok = self.c2sim_adapter.send_message(xml)
            accepted["c2sim"] = ok
            if ok:
                self._status["c2sim"]["messages_sent"] += 1
                self._record("c2sim", "outbound", "report", {"aar": str(getattr(aar, "aar_id", "unknown"))}, raw=xml)
        if self._status["bml"]["enabled"]:
            xml = self.bml_adapter.generate_aar_report(aar)
            accepted["bml"] = True
            self._status["bml"]["messages_sent"] += 1
            self._record("bml", "outbound", "aar_report", {"aar": str(getattr(aar, "aar_id", "unknown"))}, raw=xml)
        return accepted

    def send_cot_tracks(self, tracks: List[dict]) -> int:
        if not self._status["cot"]["enabled"]:
            return 0
        published = self.cot_bridge.publish_tracks(list(tracks or []))
        if published > 0:
            self._status["cot"]["messages_sent"] += published
            self._record("cot", "outbound", "track_batch", {"published": published, "requested": len(tracks)})
        return published

    def send_nffi_tracks(self, tracks: List[dict]) -> int:
        if not self._status["nffi"]["enabled"]:
            return 0
        published = self.nffi_gateway.publish_friendly_tracks(list(tracks or []))
        if published > 0:
            self._status["nffi"]["messages_sent"] += published
            self._record("nffi", "outbound", "track_batch", {"published": published, "requested": len(tracks)})
        return published

    def send_mtf_message(
        self,
        report_type: str,
        content: dict[str, Any],
        originator: str = "S3M INTEL CENTER",
        classification: str = "UNCLASSIFIED",
    ) -> dict[str, Any]:
        if not self._status["mtf"]["enabled"]:
            return {"accepted": False, "reason": "mtf_disabled"}

        xml = self.mtf_formatter.format_message(
            report_type=report_type,
            content=dict(content or {}),
            originator=originator,
            classification=classification,
        )
        parsed = self.mtf_formatter.parse_message(xml)
        delivery = self.mtf_transport.push_message(
            xml_str=xml,
            message_type=parsed["message_type"],
            metadata={
                "originator": parsed["originator"],
                "classification": parsed["classification"],
                "serial_number": parsed["serial_number"],
                "datetime_group": parsed["datetime_group"],
            },
        )
        accepted = str(delivery.get("status", "")).strip() in {"sent", "queued_offline"}
        if accepted:
            self._status["mtf"]["messages_sent"] += 1
            self._record("mtf", "outbound", parsed["message_type"], parsed["content"], raw=xml)
        return {
            "accepted": accepted,
            "message_type": parsed["message_type"],
            "serial_number": parsed["serial_number"],
            "datetime_group": parsed["datetime_group"],
            "transport": delivery,
        }

    def send_taxii_bundle(self, bundle: dict[str, Any], collection_id: str | None = None) -> bool:
        if not self._status["taxii"]["enabled"]:
            return False
        ok = self.taxii_client.publish(bundle=bundle, collection_id=collection_id)
        if ok:
            object_count = len(bundle.get("objects", [])) if isinstance(bundle, dict) else 0
            self._status["taxii"]["messages_sent"] += max(1, object_count)
            self._record("taxii", "outbound", "stix_bundle", {"objects": object_count})
        return ok

    def send_jreap_tracks(self) -> List[dict]:
        if not self._status["jreap"]["enabled"]:
            return []
        tracks = self.jreap_bridge.process_received()
        if tracks:
            self._status["jreap"]["messages_received"] += len(tracks)
            self._record("jreap", "inbound", "track_batch", {"count": len(tracks)})
        return tracks

    def send_oth_gold_tracks(self, tracks: List[dict]) -> int:
        if not self._status["oth_gold"]["enabled"]:
            return 0
        published = self.oth_adapter.publish(list(tracks or []))
        if published > 0:
            self._status["oth_gold"]["messages_sent"] += published
            self._record("oth_gold", "outbound", "track_batch", {"published": published, "requested": len(tracks)})
        return published

    def _crossfeed_geo_formats(self, tracks: List[dict]) -> dict[str, bool]:
        """Bridge COP tracks across MIP/NVG/GeoJSON so NATO feeds stay aligned."""
        result = {"mip": False, "nvg": False, "ogc": False}
        rows = [track for track in list(tracks or []) if isinstance(track, dict)]
        if not rows:
            return result

        if self._status["mip"]["enabled"]:
            published = self.mip_gateway.exchange_cop(rows)
            result["mip"] = published > 0
            if published > 0:
                self._status["mip"]["messages_sent"] += published
                self._record("mip", "outbound", "cop_oig", {"published": published})

        if self._status["ogc"]["enabled"] or self._status["nvg"]["enabled"]:
            geojson = self.geojson_adapter.tracks_to_geojson(rows)
            ogc_tracks = self.geojson_adapter.geojson_to_tracks(geojson)
            result["ogc"] = bool(ogc_tracks)
            if ogc_tracks and self._status["ogc"]["enabled"]:
                self._status["ogc"]["messages_sent"] += len(ogc_tracks)
                self._record("ogc", "outbound", "geojson_feature_collection", {"features": len(geojson.get("features", []))})

            if self._status["nvg"]["enabled"]:
                nvg_xml = self.geojson_adapter.geojson_to_nvg(geojson)
                parsed = self.nvg_parser.parse(nvg_xml)
                nvg_tracks = self.nvg_parser.to_tracks(parsed)
                self.nvg_exchange.publish_cop_overlay(nvg_tracks, mission_layers=[])
                result["nvg"] = bool(nvg_tracks)
                if nvg_tracks:
                    self._status["nvg"]["messages_sent"] += len(nvg_tracks)
                    self._record("nvg", "outbound", "overlay_publish", {"tracks": len(nvg_tracks)}, raw=nvg_xml)

        return result

    def register_uas_platform(self, uav_id: str, uav_type: str, capabilities: list[str]) -> dict:
        if not self._status["uas4586"]["enabled"]:
            return {}
        registration = self.uas4586.register_uav(uav_id, uav_type, capabilities)
        self._record("uas4586", "outbound", "register_uav", {"uav_id": registration.get("uav_id", "")})
        return registration

    def publish_uas_vehicle_status(self, uav_id: str, status: dict[str, Any]) -> dict[str, Any]:
        """Cross-connect STANAG 4586 vehicle status into CoT track exchange."""
        if not self._status["uas4586"]["enabled"]:
            return {"published": False, "reason": "uas4586_disabled", "cot": False}

        published = self.uas4586.publish_vehicle_status(uav_id, status)
        if not published:
            return {"published": False, "reason": self.uas4586.health_check().get("last_error"), "cot": False}

        self._status["uas4586"]["messages_sent"] += 1
        self._record("uas4586", "outbound", "vehicle_status", {"uav_id": uav_id})

        cot_ok = False
        if self._status["cot"]["enabled"]:
            position = status.get("position", {})
            if isinstance(position, dict):
                lat = float(position.get("lat", position.get("latitude", 0.0)))
                lon = float(position.get("lon", position.get("longitude", 0.0)))
                alt = float(position.get("alt", position.get("altitude", 0.0)))
            else:
                lat = 0.0
                lon = 0.0
                alt = 0.0
            cot_ok = self.send_cot_tracks(
                [
                    {
                        "unit_id": str(uav_id),
                        "entity_type": "FRIENDLY_UAV",
                        "affiliation": "friendly",
                        "domain": "air",
                        "position": [lat, lon, alt],
                        "speed": float(status.get("speed", 0.0)),
                        "heading": float(status.get("heading", 0.0)),
                        "callsign": str(status.get("callsign", uav_id)),
                    }
                ]
            ) > 0
        return {"published": True, "cot": cot_ok}

    def register_fmv_with_nsili(
        self,
        uav_status: dict[str, Any],
        payload_status: dict[str, Any],
        timestamp: float,
        video_reference: str,
    ) -> dict[str, Any]:
        """Cross-connect FMV metadata packets into STANAG 4559 NSILI catalog."""
        if not self._status["fmv"]["enabled"] or not self._status["nsili"]["enabled"]:
            return {"registered": False, "reason": "fmv_or_nsili_disabled"}

        packet = self.fmv_builder.build_metadata_packet(uav_status, payload_status, timestamp)
        parsed = self.fmv_builder.parse_metadata_packet(packet)
        product_id = self.fmv_builder.register_with_nsili(parsed, video_reference)
        self.nsili_catalog.register_product(
            {
                "productId": product_id,
                "productType": "VIDEO",
                "classification": "UNCLASSIFIED",
                "title": f"FMV {video_reference}",
                "format": "video/mp4",
                "contentRef": video_reference,
            }
        )
        self._status["fmv"]["messages_sent"] += 1
        self._status["nsili"]["messages_sent"] += 1
        self._record("fmv", "outbound", "metadata_packet", {"product_id": product_id})
        self._record("nsili", "outbound", "catalog_register", {"product_id": product_id})
        return {"registered": True, "product_id": product_id, "metadata": parsed}

    def publish_link22_track(self, track: dict[str, Any]) -> bool:
        if not self._status["link22"]["enabled"]:
            return False
        ok = self.link22_adapter.publish_track(track)
        self._record("link22", "outbound", "track_publish", {"published": bool(ok)})
        if ok:
            self._status["link22"]["messages_sent"] += 1
        return ok

    def receive_link22_tracks(self) -> List[dict]:
        if not self._status["link22"]["enabled"]:
            return []
        tracks = self.link22_adapter.receive_tracks()
        if tracks:
            self._status["link22"]["messages_received"] += len(tracks)
            self._record("link22", "inbound", "track_batch", {"count": len(tracks)})
        return tracks

    def receive_all(self) -> List[dict]:
        messages: List[dict] = []

        if self._status["dis"]["enabled"] and self._status["dis"]["connected"]:
            dis_data = self.dis_adapter.receive()
            if dis_data:
                msg = {
                    "protocol": "dis",
                    "message_type": "entity_state",
                    "data": dis_data,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "raw": "",
                }
                messages.append(msg)
                self._status["dis"]["messages_received"] += 1
                self._record("dis", "inbound", "entity_state", dis_data)

        if self._status["c2sim"]["enabled"]:
            xml_msgs = self.c2sim_adapter.receive_messages()
            for raw in xml_msgs:
                parsed = {"raw_message": raw}
                if "<Order" in raw:
                    try:
                        parsed = self.c2sim_adapter.order_to_mission(raw)
                    except Exception:
                        parsed = {"raw_message": raw}
                msg = {
                    "protocol": "c2sim",
                    "message_type": "xml",
                    "data": parsed,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "raw": raw,
                }
                messages.append(msg)
                self._status["c2sim"]["messages_received"] += 1
                self._record("c2sim", "inbound", "xml", parsed, raw=raw)

        if self._status["cot"]["enabled"]:
            for track in self.cot_bridge.ingest_received():
                messages.append(
                    {
                        "protocol": "cot",
                        "message_type": "track",
                        "data": track,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "raw": "",
                    }
                )
                self._status["cot"]["messages_received"] += 1
                self._record("cot", "inbound", "track", track)

        if self._status["nffi"]["enabled"]:
            for track in self.nffi_gateway.receive_coalition_tracks():
                messages.append(
                    {
                        "protocol": "nffi",
                        "message_type": "track",
                        "data": track,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "raw": "",
                    }
                )
                self._status["nffi"]["messages_received"] += 1
                self._record("nffi", "inbound", "track", track)

        if self._status["mtf"]["enabled"]:
            for raw in self.mtf_transport.pull_messages():
                parsed = {"raw_message": raw}
                try:
                    parsed = self.mtf_formatter.parse_message(raw)
                except Exception:
                    parsed = {"raw_message": raw}
                messages.append(
                    {
                        "protocol": "mtf",
                        "message_type": "xml",
                        "data": parsed,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "raw": raw,
                    }
                )
                self._status["mtf"]["messages_received"] += 1
                self._record("mtf", "inbound", "xml", parsed, raw=raw)

        if self._status["jreap"]["enabled"]:
            for track in self.jreap_bridge.process_received():
                messages.append(
                    {
                        "protocol": "jreap",
                        "message_type": "track",
                        "data": track,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "raw": "",
                    }
                )
                self._status["jreap"]["messages_received"] += 1
                self._record("jreap", "inbound", "track", track)

        if self._status["oth_gold"]["enabled"]:
            for track in self.oth_adapter.receive():
                messages.append(
                    {
                        "protocol": "oth_gold",
                        "message_type": "track",
                        "data": track,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "raw": "",
                    }
                )
                self._status["oth_gold"]["messages_received"] += 1
                self._record("oth_gold", "inbound", "track", track)

        if self._status["hla"]["enabled"]:
            for hla_object in self.hla_adapter.get_objects():
                track = self.hla_dis_bridge.sync_from_hla(hla_object)
                if not track:
                    continue
                messages.append(
                    {
                        "protocol": "hla",
                        "message_type": "object_reflection",
                        "data": track,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "raw": "",
                    }
                )
                self._status["hla"]["messages_received"] += 1
                self._record("hla", "inbound", "object_reflection", track)

                # Tactical bidirectional bridge: HLA object state is mirrored back to DIS entity updates.
                if self._status["dis"]["enabled"] and self._status["dis"]["connected"]:
                    dis_entity = {
                        "entity_id": track.get("unit_id", "hla-entity"),
                        "entity_type": "FRIENDLY_UAV",
                        "location": {
                            "lat": float(track.get("position", [0.0, 0.0, 0.0])[0]),
                            "lon": float(track.get("position", [0.0, 0.0, 0.0])[1]),
                            "alt": float(track.get("position", [0.0, 0.0, 0.0])[2]),
                        },
                        "allegiance": "friendly",
                        "status": track.get("status", "active"),
                    }
                    self.dis_adapter.send_entity_update(dis_entity)
                    self._status["dis"]["messages_sent"] += 1
                    self._record("dis", "outbound", "hla_bridge_entity_state", dis_entity)

        if self._status["link22"]["enabled"]:
            for track in self.receive_link22_tracks():
                messages.append(
                    {
                        "protocol": "link22",
                        "message_type": "track",
                        "data": track,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "raw": "",
                    }
                )

        return messages

    def get_message_history(
        self,
        protocol: str | None = None,
        direction: str | None = None,
        limit: int = 50,
    ) -> List[dict]:
        rows = self._history
        if protocol:
            rows = [r for r in rows if r["protocol"] == protocol.lower().strip()]
        if direction:
            rows = [r for r in rows if r["direction"] == direction.lower().strip()]
        return rows[-max(1, limit) :]

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "protocols": self.get_protocol_status(),
            "history_entries": len(self._history),
        }

    @staticmethod
    def _entity_to_interop_track(entity: dict[str, Any]) -> dict[str, Any]:
        entity_id = str(entity.get("entity_id", entity.get("uid", "unknown")))
        location = entity.get("location", entity.get("position", {}))
        if isinstance(location, dict):
            lat = float(location.get("lat", location.get("latitude", location.get("x", 0.0))))
            lon = float(location.get("lon", location.get("longitude", location.get("y", 0.0))))
            alt = float(location.get("alt", location.get("altitude", location.get("z", 0.0))))
        elif isinstance(location, (list, tuple)) and len(location) >= 3:
            lat = float(location[0])
            lon = float(location[1])
            alt = float(location[2])
        else:
            lat = 0.0
            lon = 0.0
            alt = 0.0
        return {
            "unit_id": entity_id,
            "position": [lat, lon, alt],
            "entity_type": str(entity.get("entity_type", "UNKNOWN")),
            "affiliation": str(entity.get("allegiance", entity.get("affiliation", "friendly"))),
            "domain": "ground",
            "status": str(entity.get("status", "active")),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "callsign": str(entity.get("marking", entity_id)),
        }
