"""NVG exchange orchestration for coalition tactical overlay interoperability."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import threading
from time import sleep
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from services.interop.nvg.nvg_builder import NVGBuilder
from services.interop.nvg.nvg_parser import NVGParser


class NVGOverlayExchange:
    """Coordinate NVG publish/receive workflows for COP and mission overlays."""

    def __init__(
        self,
        config: dict | None = None,
        builder: NVGBuilder | None = None,
        parser: NVGParser | None = None,
    ):
        cfg = dict(config or {})
        if isinstance(cfg.get("nvg"), dict):
            cfg = dict(cfg["nvg"])
        self.config = cfg
        self.publish_interval_seconds = max(1, int(cfg.get("publish_interval_seconds", 10)))
        self.outbox_dir = Path(str(cfg.get("outbox_dir", "data/interop/nvg_outbox/")))
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

        self.builder = builder or NVGBuilder(cfg)
        self.parser = parser or NVGParser(cfg)
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_stop = threading.Event()
        self._stream_source: Optional[Callable[[], Dict[str, Any]]] = None

        self._stats = {
            "published": 0,
            "received": 0,
            "stream_pushes": 0,
            "errors": 0,
            "last_publish_time": None,
            "last_receive_time": None,
            "last_file": None,
            "streaming": False,
        }
        self._last_cop_xml = ""
        self._last_overlay_xml = ""

    def publish_cop_overlay(self, tracks: List[dict], mission_layers: Any) -> str:
        """Publish complete COP as NVG by merging tracks and mission graphics."""
        try:
            self.builder.clear()
            self.builder.add_tracks(tracks if isinstance(tracks, list) else [])
            if isinstance(mission_layers, list):
                for layer in mission_layers:
                    if isinstance(layer, dict):
                        self.builder.add_mission_layer(layer)
            elif isinstance(mission_layers, dict):
                self.builder.add_mission_layer(mission_layers)
            xml = self.builder.build()
            self._last_cop_xml = xml
            self._record_publish(xml, artifact_type="cop")
            return xml
        except Exception:
            self._stats["errors"] += 1
            raise

    def publish_operational_overlay(self, mission_layer: dict) -> str:
        """Publish planning and control graphics only as NVG overlay XML."""
        try:
            xml = self.builder.from_mission_layer(mission_layer if isinstance(mission_layer, dict) else {})
            self._last_overlay_xml = xml
            self._record_publish(xml, artifact_type="overlay")
            return xml
        except Exception:
            self._stats["errors"] += 1
            raise

    def receive_overlay(self, xml_str: str) -> dict:
        """Ingest partner NVG XML and return S3M tracks plus mission-layer graphics."""
        try:
            parsed = self.parser.parse(xml_str)
            tracks = self.parser.to_tracks(parsed)
            mission_layer = self.parser.to_mission_layer(parsed)
            self._stats["received"] += 1
            self._stats["last_receive_time"] = datetime.now(timezone.utc).isoformat()
            return {
                "tracks": tracks,
                "mission_layer": mission_layer,
                "parsed": parsed,
            }
        except Exception:
            self._stats["errors"] += 1
            raise

    def start_streaming(self, source: Callable[[], Dict[str, Any]] | None = None) -> bool:
        """Start periodic NVG publishing loop for coalition COP synchronization."""
        if self._stream_thread is not None and self._stream_thread.is_alive():
            return True
        if source is not None:
            self._stream_source = source
        if self._stream_source is None:
            return False
        self._stream_stop.clear()
        self._stream_thread = threading.Thread(target=self._stream_loop, name="nvg-stream", daemon=True)
        self._stream_thread.start()
        self._stats["streaming"] = True
        return True

    def stop_streaming(self) -> None:
        """Stop periodic NVG publish loop."""
        self._stream_stop.set()
        if self._stream_thread is not None and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=2.0)
        self._stream_thread = None
        self._stats["streaming"] = False

    def stream_once(self, payload: Dict[str, Any] | None = None) -> str:
        """Execute one streaming publish cycle and return generated NVG XML."""
        data = payload
        if data is None:
            if self._stream_source is None:
                raise ValueError("stream source is not configured")
            data = self._stream_source()
        if not isinstance(data, dict):
            raise ValueError("stream payload must be a dictionary")
        tracks = data.get("tracks", [])
        mission_layers = data.get("mission_layers", data.get("mission_layer", []))
        xml = self.publish_cop_overlay(tracks=tracks, mission_layers=mission_layers)
        self._stats["stream_pushes"] += 1
        return xml

    def get_latest_cop_xml(self) -> str:
        """Return latest published COP NVG XML, if available."""
        return self._last_cop_xml

    def get_latest_overlay_xml(self) -> str:
        """Return latest published operational overlay NVG XML, if available."""
        return self._last_overlay_xml

    def export_current_cop_file(self, tracks: List[dict], mission_layers: Any) -> Path:
        """Build and persist a COP NVG artifact for file-based coalition exchange."""
        xml = self.publish_cop_overlay(tracks=tracks, mission_layers=mission_layers)
        return self._write_outbox(xml, artifact_type="cop-export")

    def status(self) -> dict:
        """Return NVG exchange and streaming telemetry."""
        return {
            "status": "operational",
            "publish_interval_seconds": self.publish_interval_seconds,
            "outbox_dir": str(self.outbox_dir),
            **self._stats,
        }

    def _stream_loop(self) -> None:
        while not self._stream_stop.is_set():
            try:
                self.stream_once()
            except Exception:
                self._stats["errors"] += 1
            self._stream_stop.wait(timeout=self.publish_interval_seconds)

    def _record_publish(self, xml: str, artifact_type: str) -> None:
        self._stats["published"] += 1
        self._stats["last_publish_time"] = datetime.now(timezone.utc).isoformat()
        path = self._write_outbox(xml, artifact_type=artifact_type)
        self._stats["last_file"] = str(path)

    def _write_outbox(self, xml: str, artifact_type: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"nvg-{artifact_type}-{timestamp}-{uuid4().hex[:8]}.xml"
        target = self.outbox_dir / name
        target.write_text(str(xml), encoding="utf-8")
        return target

