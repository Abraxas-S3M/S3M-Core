"""Full interoperability integration test for Phase 16 adapter wiring.

Military/tactical context:
This suite validates coalition track crossfeed and report generation pathways
so commanders can trust common operating picture consistency across protocols.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from services.interop import InteropVerifier
from services.interop.cot import CotBridge, CotEventFactory, CotTransport
from services.interop.mtf import MTFFormatter
from services.interop.nffi import NFFIGateway, NFFIMessageBuilder
from src.force_awareness import ForceAwarenessManager
from src.security.interop import InteropManager


class _OfflineCotTransport(CotTransport):
    def __init__(self, config: dict):
        super().__init__(config)
        self._rx: List[str] = []

    def send(self, xml: str) -> bool:
        self._rx.append(xml)
        return True

    def receive(self) -> str | None:
        if not self._rx:
            return None
        return self._rx.pop(0)


class _OfflineNFFIGateway(NFFIGateway):
    def __init__(self, config: dict, message_builder: NFFIMessageBuilder):
        super().__init__(config=config, message_builder=message_builder)
        self._rx: List[str] = []

    def publish_friendly_tracks(self, tracks: List[dict]) -> int:
        xml = self.message_builder.build_message(
            tracks=tracks,
            country_iso3=self.track_source_country,
            system_id=self.system_id,
        )
        self._rx.append(xml)
        return len(self.message_builder.parse_message(xml))

    def receive_coalition_tracks(self) -> List[dict]:
        tracks: List[dict] = []
        while self._rx:
            xml = self._rx.pop(0)
            tracks.extend(self.message_builder.parse_message(xml))
        return tracks


def _sample_dis_entity() -> Dict[str, Any]:
    return {
        "entity_id": "blue-interop-1",
        "allegiance": "friendly",
        "entity_type": "FRIENDLY_UGV",
        "location": {"lat": 24.7136, "lon": 46.6753, "alt": 620.0},
        "orientation": {"psi": 0.0, "theta": 0.0, "phi": 0.0},
        "velocity": {"x": 7.5, "y": 0.0, "z": 0.0},
        "status": "active",
        "marking": "FALCON-1",
    }


def _sample_cot_track() -> Dict[str, Any]:
    return {
        "unit_id": "coalition-cot-1",
        "entity_type": "FRIENDLY_UAV",
        "affiliation": "friendly",
        "domain": "air",
        "position": [24.7200, 46.6800, 650.0],
        "speed": 55.0,
        "heading": 75.0,
        "callsign": "COALITION-UAV",
    }


def test_full_interop_integration_flow(tmp_path: Path) -> None:
    manager = InteropManager()

    cot_transport = _OfflineCotTransport({"cot": {"outbox_dir": str(tmp_path / "cot_outbox")}})
    cot_factory = CotEventFactory({})
    manager._cot_transport = cot_transport
    manager._cot_event_factory = cot_factory
    manager.cot_bridge = CotBridge(transport=cot_transport, event_factory=cot_factory)

    nffi_gateway = _OfflineNFFIGateway(
        config={
            "transport_profile": "IP-1",
            "gateway_url": None,
            "track_source_country": "SAU",
            "system_id": "S3M-FALCON",
            "outbox_dir": str(tmp_path / "nffi_outbox"),
            "inbox_dir": str(tmp_path / "nffi_inbox"),
        },
        message_builder=NFFIMessageBuilder(),
    )
    manager.nffi_builder = nffi_gateway.message_builder
    manager.nffi_gateway = nffi_gateway

    manager._status["cot"]["enabled"] = True
    manager._status["cot"]["connected"] = True
    manager._status["nffi"]["enabled"] = True
    manager._status["nffi"]["connected"] = True
    manager._status["mtf"]["enabled"] = True
    manager._status["mtf"]["connected"] = False

    # DIS publish should crossfeed into CoT + NFFI when adapters are enabled.
    result = manager.send_entity_update(_sample_dis_entity())
    assert result["cot"] is True
    assert result["nffi"] is True

    cot_tracks = manager.cot_bridge.ingest_received()
    nffi_tracks = manager.nffi_gateway.receive_coalition_tracks()
    assert len(cot_tracks) >= 1
    assert len(nffi_tracks) >= 1

    # Simulate inbound CoT and verify ForceAwareness ingest path.
    manager.cot_bridge.publish_tracks([_sample_cot_track()])
    inbound_cot = manager.cot_bridge.ingest_received()
    assert len(inbound_cot) == 1
    force_awareness = ForceAwarenessManager()
    ingest = force_awareness.ingest_tracks(inbound_cot)
    assert ingest["accepted"] == 1
    assert ingest["track_count"] == 1

    # Generate APP-11 INTSUM.
    mtf_out = manager.send_mtf_message(
        report_type="INTSUM",
        content={
            "summary_text": "Coalition air and land tracks synchronized across gateways.",
            "assessment_text": "Interoperability posture remains stable under offline constraints.",
        },
        originator="S3M J2",
        classification="SECRET",
    )
    assert mtf_out["accepted"] is True
    formatter = MTFFormatter()
    parsed = formatter.parse_message(
        formatter.format_message(
            report_type="INTSUM",
            content={
                "summary_text": "Coalition air and land tracks synchronized across gateways.",
                "assessment_text": "Interoperability posture remains stable under offline constraints.",
            },
            originator="S3M J2",
            classification="SECRET",
        )
    )
    assert parsed["message_type"] == "INTSUM"

    verification = InteropVerifier().run_full_verification()
    assert verification["summary"]["tests_failed"] == 0
