"""Multi-protocol security interoperability manager for S3M."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from services.interop.cot import CotBridge, CotEventFactory, CotTransport
from services.interop.jreap import JREAPBridge
from services.interop.mtf import MTFFormatter, MTFTransport
from services.interop.nffi import NFFIGateway, NFFIMessageBuilder
from services.interop.oth import OTHGoldAdapter
from services.interop.stix import TAXIIClient
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

    def _record(self, protocol: str, direction: str, message_type: str, data: Any, raw: str = "") -> None:
        self._history.append(
            {
                "protocol": protocol,
                "direction": direction,
                "message_type": message_type,
                "data": data,
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

        if protocol in self._status:
            self._status[protocol]["enabled"] = False
            self._status[protocol]["connected"] = False

    def get_protocol_status(self) -> dict:
        return {protocol: dict(state) for protocol, state in self._status.items()}

    def send_entity_update(self, entity: Any) -> dict:
        result = {"dis": False, "c2sim": False, "cot": False, "nffi": False}
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
