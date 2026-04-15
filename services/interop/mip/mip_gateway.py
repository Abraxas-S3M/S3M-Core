"""MIP gateway implementing a tactical DEM-style exchange workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from services.interop.mip.mip_data_model import MIPDataModel, MIPOperationalInfoGroup
from services.interop.mip.mip_object_mapper import MIPObjectMapper


class MIPGateway:
    """Core MIP 4.3 gateway with publish/subscribe and offline XML queueing."""

    def __init__(self, config: dict):
        cfg = dict(config or {})
        self.config = cfg
        self.baseline = str(cfg.get("baseline", "4.3"))
        self.data_model_name = str(cfg.get("data_model", "MIM"))
        self.gateway_url = cfg.get("gateway_url")
        self.available_oigs = list(
            cfg.get("oig_categories", ["operations", "intelligence", "logistics", "plans", "cop"])
        )
        self.publish_interval_seconds = int(cfg.get("publish_interval_seconds", 10))
        self.outbox_dir = Path(str(cfg.get("outbox_dir", "data/interop/mip_outbox/")))
        self.inbox_dir = Path(str(cfg.get("inbox_dir", "data/interop/mip_inbox/")))
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

        self.data_model = MIPDataModel()
        self.mapper = MIPObjectMapper(self.data_model)
        self.connected = False
        self.partner_gateway_url: str | None = None
        self.partner_oigs: list[str] = []
        self.last_error: str | None = None
        self.published_oigs: list[MIPOperationalInfoGroup] = []
        self._received_updates: list[Any] = []
        self._subscriptions: dict[str, list[Callable[[Any], None]]] = {}

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def connect(self, partner_gateway_url: str) -> bool:
        partner = str(partner_gateway_url or "").strip()
        if not partner:
            self.connected = False
            self.partner_gateway_url = None
            self.last_error = "partner_gateway_url is required"
            return False
        self.partner_gateway_url = partner
        self.connected = True
        self.partner_oigs = list(self.available_oigs)
        # Tactical context: DEM handshake advertises OIG categories before any COP/order exchange.
        self._received_updates.append(
            {
                "event": "dem_handshake",
                "time": self._iso_now(),
                "partner_gateway_url": self.partner_gateway_url,
                "local_oigs": list(self.available_oigs),
                "partner_oigs": list(self.partner_oigs),
            }
        )
        self.last_error = None
        return True

    def _oig_payload_objects(self, oig: MIPOperationalInfoGroup) -> list[Any]:
        payload: list[Any] = []
        for item_id in oig.items:
            if item_id in self.data_model.object_items:
                payload.append(self.data_model.object_items[item_id])
                loc = self.data_model.locations.get(item_id)
                if loc is not None:
                    payload.append(loc)
            elif item_id in self.data_model.action_tasks:
                payload.append(self.data_model.action_tasks[item_id])
        payload.append(oig)
        return payload

    def _write_outbox_xml(self, xml: str, category: str) -> Path:
        message_id = f"mip-{category}-{uuid4().hex[:10]}"
        path = self.outbox_dir / f"{message_id}.xml"
        path.write_text(xml, encoding="utf-8")
        return path

    def publish_oig(self, oig: MIPOperationalInfoGroup) -> bool:
        if not isinstance(oig, MIPOperationalInfoGroup):
            self.last_error = "publish_oig requires MIPOperationalInfoGroup"
            return False
        self.data_model.oigs[oig.oig_id] = oig
        xml = self.data_model.to_xml(self._oig_payload_objects(oig))
        self.published_oigs.append(oig)
        if not self.connected:
            self._write_outbox_xml(xml, oig.category)
            return True
        update = {
            "event": "oig_publish",
            "time": self._iso_now(),
            "category": oig.category,
            "oig_id": oig.oig_id,
            "xml": xml,
            "partner_gateway_url": self.partner_gateway_url,
        }
        self._received_updates.append(update)
        for callback in self._subscriptions.get(oig.category, []):
            callback(update)
        return True

    def subscribe_oig(self, oig_category: str, callback) -> bool:
        category = str(oig_category or "").strip().lower()
        if category not in self.available_oigs:
            self.last_error = f"Unsupported OIG category: {category}"
            return False
        if not callable(callback):
            self.last_error = "callback must be callable"
            return False
        self._subscriptions.setdefault(category, []).append(callback)
        self.last_error = None
        return True

    def exchange_cop(self, tracks: list[dict]) -> int:
        friendly_count = 0
        cop_oig = self.data_model.create_oig(category="cop", unit_id="s3m-cop")
        for track in list(tracks or []):
            if not isinstance(track, dict):
                continue
            track_type = self.mapper._extract_track_type(track)
            hostility = self.mapper._derive_hostility(track, track_type)
            if hostility != "friend":
                continue
            obj, location = self.mapper.s3m_track_to_mip(track)
            cop_oig.items.extend([obj.object_item_id, location.object_item_id])
            friendly_count += 1
        self.publish_oig(cop_oig)
        return friendly_count

    def _load_inbox_updates(self) -> list[Any]:
        updates: list[Any] = []
        for path in sorted(self.inbox_dir.glob("*.xml")):
            xml = path.read_text(encoding="utf-8")
            updates.append(
                {
                    "event": "inbox_xml",
                    "path": str(path),
                    "parsed": self.data_model.from_xml(xml),
                }
            )
        return updates

    def receive_updates(self) -> list:
        updates = list(self._received_updates)
        updates.extend(self._load_inbox_updates())
        self._received_updates.clear()
        return updates

    def disconnect(self):
        self.connected = False
        self.partner_gateway_url = None
        self.partner_oigs = []

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "baseline": self.baseline,
            "data_model": self.data_model_name,
            "connected": self.connected,
            "gateway_url": self.gateway_url,
            "partner_gateway_url": self.partner_gateway_url,
            "available_oigs": list(self.available_oigs),
            "partner_oigs": list(self.partner_oigs),
            "subscriptions": {k: len(v) for k, v in self._subscriptions.items()},
            "publish_interval_seconds": self.publish_interval_seconds,
            "published_oig_count": len(self.published_oigs),
            "offline_outbox_count": len(list(self.outbox_dir.glob("*.xml"))),
            "inbox_count": len(list(self.inbox_dir.glob("*.xml"))),
            "last_error": self.last_error,
        }
