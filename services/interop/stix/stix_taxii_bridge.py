"""Bridge TAXII feeds with local STIX processing and tactical watchlists."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Event, Lock, Thread
import time
from typing import Any
from uuid import uuid4

from services.interop.stix.taxii_client import TAXIIClient
from src.apps.intel.stix_processor import STIXProcessor
from src.apps.intel.watchlists import WatchlistStore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class STIXTAXIIBridge:
    """Coordinates TAXII transport with local watchlist ingest/export."""

    def __init__(
        self,
        taxii_client: TAXIIClient,
        stix_processor: STIXProcessor,
        watchlist_store: WatchlistStore | None = None,
    ) -> None:
        self.taxii_client = taxii_client
        self.stix_processor = stix_processor
        self.watchlist_store = watchlist_store or WatchlistStore(stix_processor=stix_processor)

        self._last_poll: str | None = None
        self._objects_received = 0
        self._objects_contributed = 0
        self._last_errors: list[str] = []

        self._sync_lock = Lock()
        self._poll_thread: Thread | None = None
        self._stop_event = Event()

    def sync_feed(self, collection_id: str | None = None) -> dict:
        """Poll TAXII, import STIX objects, and update local watchlists."""
        with self._sync_lock:
            response = {"new_indicators": 0, "new_threat_actors": 0, "errors": []}
            self._last_poll = _utc_now_iso()

            try:
                objects = self.taxii_client.poll(collection_id=collection_id)
            except Exception as exc:
                err = f"poll_failed: {exc}"
                response["errors"].append(err)
                self._last_errors.append(err)
                return response

            if not objects:
                return response

            bundle_payload = {
                "type": "bundle",
                "id": f"bundle--{uuid4()}",
                "objects": objects,
            }

            temp_path: str | None = None
            imported: list[dict[str, Any]] = []
            try:
                with NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as temp_file:
                    json.dump(bundle_payload, temp_file, ensure_ascii=True)
                    temp_path = temp_file.name
                imported = self.stix_processor.import_bundle(temp_path)
            except Exception as exc:
                err = f"import_failed: {exc}"
                response["errors"].append(err)
                self._last_errors.append(err)
                imported = []
            finally:
                if temp_path and Path(temp_path).exists():
                    Path(temp_path).unlink()

            for entity in imported:
                try:
                    category = str(entity.get("category", "")).strip()
                    if not category:
                        continue
                    self.watchlist_store.upsert_entity(category, entity)
                except Exception as exc:
                    err = f"watchlist_update_failed: {exc}"
                    response["errors"].append(err)
                    self._last_errors.append(err)

            for item in objects:
                item_type = str(item.get("type", "")).strip().lower()
                if item_type == "indicator":
                    response["new_indicators"] += 1
                elif item_type == "threat-actor":
                    response["new_threat_actors"] += 1

            self._objects_received += len(objects)
            return response

    def contribute_watchlist(self, watchlist_name: str) -> bool:
        """Export one local watchlist category as STIX and publish to TAXII."""
        category = self.watchlist_store.normalize_category(watchlist_name)
        bundle = self.watchlist_store.export_stix(category)
        if hasattr(bundle, "serialize"):
            payload = json.loads(str(bundle.serialize()))
        elif isinstance(bundle, dict):
            payload = dict(bundle)
        else:
            raise ValueError("watchlist export returned unsupported bundle format")

        ok = self.taxii_client.publish(payload)
        if ok:
            self._objects_contributed += len(payload.get("objects", []))
        return ok

    def schedule_polling(self, interval_seconds: int) -> None:
        """Start or restart periodic TAXII polling loop."""
        if int(interval_seconds) <= 0:
            raise ValueError("interval_seconds must be greater than zero")
        self.stop_polling()

        interval = int(interval_seconds)
        self._stop_event.clear()

        def _loop() -> None:
            while not self._stop_event.is_set():
                # Tactical context: regular polling keeps coalition IOC feeds synced
                # when disconnected units intermittently regain transport links.
                self.sync_feed()
                if self._stop_event.wait(interval):
                    break
                time.sleep(0.01)

        self._poll_thread = Thread(target=_loop, name="stix-taxii-poller", daemon=True)
        self._poll_thread.start()

    def stop_polling(self) -> None:
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)
        self._poll_thread = None

    def get_sync_status(self) -> dict:
        """Return current bridge synchronization counters and health snapshots."""
        return {
            "last_poll": self._last_poll,
            "objects_received": self._objects_received,
            "objects_contributed": self._objects_contributed,
            "errors": self._last_errors[-20:],
            "polling_active": bool(self._poll_thread and self._poll_thread.is_alive()),
            "taxii_transport": self.taxii_client.health_check(),
        }
