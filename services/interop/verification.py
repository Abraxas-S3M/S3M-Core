"""Interoperability verification suites for coalition protocol conformance."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
from typing import List

from services.interop.cot.cot_event import CotEventFactory
from services.interop.c2sim.message_factory import C2SIMMessageFactory
from services.interop.dis.coordinate_converter import DISCoordinateConverter
from services.interop.dis.dead_reckoning import DISDeadReckoning
from services.interop.dis.pdu_factory import DISPDUFactory
from services.interop.mtf import MTFFormatter
from services.interop.nffi import NFFIMessageBuilder
from services.interop.registry import InteropRegistry
from services.interop.stix.taxii_client import TAXIIClient
from services.interop.symbology import SIDCGenerator, SymbologyMapper
from services.interop.models import (
    DISEntityID,
    DISEntityType,
    DISLinearVelocity,
    DISOrientation,
    DISWorldCoordinate,
    MSDLScenario,
)
from services.interop.msdl.generator import MSDLGenerator
from services.interop.msdl.parser import MSDLParser
from src.security.interop.dis_adapter import DIS_ENTITY_MAP


class InteropVerifier:
    """Runs interoperability checks against local protocol implementations."""

    def __init__(self):
        self.dis_factory = DISPDUFactory()
        self.coord = DISCoordinateConverter()
        self.dr = DISDeadReckoning()
        self.c2 = C2SIMMessageFactory()
        self.cot = CotEventFactory()
        self.nffi = NFFIMessageBuilder()
        self.mtf = MTFFormatter()
        self.msdl_gen = MSDLGenerator()
        self.msdl_parser = MSDLParser()

    def verify_dis_conformance(self) -> dict:
        results: List[dict] = []
        passed = 0
        failed = 0

        try:
            entity_id = DISEntityID(1, 1, 100)
            entity_type = DISEntityType(1, 1, 178, 1, 0, 0, 0)
            position = DISWorldCoordinate.from_lat_lon_alt(24.7136, 46.6753, 620.0)
            orientation = DISOrientation(0.1, 0.0, 0.0)
            velocity = DISLinearVelocity(10.0, 0.0, 0.0)
            pdu = self.dis_factory.encode_entity_state(
                entity_id=entity_id,
                entity_type=entity_type,
                position=position,
                orientation=orientation,
                velocity=velocity,
                force_id=1,
                exercise_id=1,
                marking="SAUDI-TANK",
            )
            decoded = self.dis_factory.decode_entity_state(pdu)
            ok = decoded["entity_id"] == entity_id and decoded["marking"] == "SAUDI-TANK"
            results.append({"test": "entity_state_roundtrip", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "entity_state_roundtrip", "passed": False, "error": str(exc)})
            failed += 1

        try:
            x, y, z = self.coord.lla_to_ecef(24.7136, 46.6753, 620.0)
            lat, lon, alt = self.coord.ecef_to_lla(x, y, z)
            err = self._distance_lla(24.7136, 46.6753, 620.0, lat, lon, alt)
            ok = err < 1.0
            results.append({"test": "coordinate_roundtrip", "passed": ok, "error_m": err})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "coordinate_roundtrip", "passed": False, "error": str(exc)})
            failed += 1

        try:
            projected = self.dr.extrapolate(
                {
                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "velocity": {"x": 10.0, "y": 0.0, "z": 0.0},
                    "orientation": {"psi": 0.0, "theta": 0.0, "phi": 0.0},
                },
                dt_seconds=2.0,
                algorithm=2,
            )
            ok = abs(projected["position"]["x"] - 20.0) < 1e-6
            results.append({"test": "dead_reckoning_fpw", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "dead_reckoning_fpw", "passed": False, "error": str(exc)})
            failed += 1

        try:
            pdu = self.dis_factory.encode_stop_freeze(exercise_id=1, reason=2)
            pdu_type = int(self.dis_factory.identify_pdu_type(pdu))
            ok = pdu_type == 14
            results.append({"test": "header_validation", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "header_validation", "passed": False, "error": str(exc)})
            failed += 1

        return {"tests_passed": passed, "tests_failed": failed, "results": results}

    def verify_c2sim_conformance(self) -> dict:
        results: List[dict] = []
        passed = 0
        failed = 0

        try:
            order_xml = self.c2.create_order(
                order_id="order-1",
                issuer="HQ",
                task_type="Advance",
                assigned_units=["unit-1"],
                waypoints=[(24.7, 46.6, 0)],
                roe="self-defense",
            )
            order = self.c2.parse_order(order_xml)
            ok = order["order_id"] == "order-1" and order["assigned_units"] == ["unit-1"]
            results.append({"test": "order_roundtrip", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "order_roundtrip", "passed": False, "error": str(exc)})
            failed += 1

        try:
            report_xml = self.c2.create_report("rep-1", "unit-1", "PositionReport", {"lat": "24.7"})
            report = self.c2.parse_report(report_xml)
            ok = report["report_type"] == "PositionReport"
            results.append({"test": "report_roundtrip", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "report_roundtrip", "passed": False, "error": str(exc)})
            failed += 1

        try:
            init_xml = self.c2.create_initialization(
                {"scenario_id": "scn-1", "name": "Init", "forces": [], "environment": {"terrain": "desert"}}
            )
            init = self.c2.parse_initialization(init_xml)
            ok = init["scenario_id"] == "scn-1" and "environment" in init
            results.append({"test": "initialization_roundtrip", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "initialization_roundtrip", "passed": False, "error": str(exc)})
            failed += 1

        try:
            ok = self.c2.namespace in self.c2.create_order(
                "o2", "HQ", "Move", ["u1"], [(24.0, 46.0, 0)], "self-defense"
            )
            results.append({"test": "namespace_correctness", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "namespace_correctness", "passed": False, "error": str(exc)})
            failed += 1

        return {"tests_passed": passed, "tests_failed": failed, "results": results}

    def verify_cot_conformance(self) -> dict:
        """Verify CoT gateway correctness for tactical ATAK interoperability."""
        results: List[dict] = []
        passed = 0
        failed = 0

        try:
            sample = {
                "unit_id": "cot-1",
                "entity_type": "FRIENDLY_UGV",
                "affiliation": "friendly",
                "domain": "ground",
                "position": [24.7136, 46.6753, 620.0],
                "heading": 90.0,
                "speed": 11.0,
                "callsign": "S3M-COT1",
                "time": "2026-01-01T00:00:00Z",
            }
            xml = self.cot.build_event(sample)
            parsed = self.cot.parse_event(xml)
            ok = parsed["uid"] == "cot-1" and parsed["affiliation"] == "friendly"
            results.append({"test": "cot_roundtrip", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "cot_roundtrip", "passed": False, "error": str(exc)})
            failed += 1

        try:
            ok = True
            for key, payload in DIS_ENTITY_MAP.items():
                upper = key.upper()
                if upper.startswith("FRIENDLY_"):
                    affiliation = "friendly"
                elif upper.startswith("ENEMY_"):
                    affiliation = "hostile"
                elif upper.startswith("UNKNOWN"):
                    affiliation = "unknown"
                else:
                    affiliation = "neutral"
                domain = {2: "air", 3: "surface"}.get(int(payload.get("domain", 1)), "ground")
                cot_type = self.cot._s3m_type_to_cot(key, affiliation, domain)
                if not cot_type.startswith("a-"):
                    ok = False
                    break
            results.append({"test": "cot_type_mapping_all_entities", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "cot_type_mapping_all_entities", "passed": False, "error": str(exc)})
            failed += 1

        try:
            # Tactical geolocation fidelity check for CENTCOM common reference point.
            riyadh_track = {
                "unit_id": "riyadh-ref",
                "entity_type": "FRIENDLY_UGV",
                "affiliation": "friendly",
                "domain": "ground",
                "lat": 24.7136,
                "lon": 46.6753,
                "hae": 612.0,
            }
            xml = self.cot.build_event(riyadh_track)
            parsed = self.cot.parse_event(xml)
            err = self._distance_lla(24.7136, 46.6753, 612.0, parsed["lat"], parsed["lon"], parsed["hae"])
            ok = err < 0.5
            results.append({"test": "cot_coordinate_accuracy_riyadh", "passed": ok, "error_m": err})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "cot_coordinate_accuracy_riyadh", "passed": False, "error": str(exc)})
            failed += 1

        return {"tests_passed": passed, "tests_failed": failed, "results": results}

    def verify_nffi_conformance(self) -> dict:
        """Verify NFFI build/parse behavior for coalition blue-force exchange."""
        results: List[dict] = []
        passed = 0
        failed = 0

        try:
            tracks = [
                {
                    "unit_id": "falcon-11",
                    "position": [24.7136, 46.6753, 620.0],
                    "role": "friendly_armor",
                    "status": "active",
                    "updated_at": "2026-04-15T12:30:45+00:00",
                }
            ]
            xml = self.nffi.build_message(tracks=tracks, country_iso3="SAU", system_id="S3M-FALCON")
            parsed = self.nffi.parse_message(xml)
            ok = len(parsed) == 1 and parsed[0]["unit_id"] == "falcon-11"
            results.append({"test": "nffi_roundtrip", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "nffi_roundtrip", "passed": False, "error": str(exc)})
            failed += 1

        try:
            registry = InteropRegistry()
            iso3 = registry.get_iso3_codes()
            ok = iso3.get(178) == "SAU" and iso3.get(223) == "ARE" and iso3.get(225) == "USA"
            results.append({"test": "nffi_country_code_mapping", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "nffi_country_code_mapping", "passed": False, "error": str(exc)})
            failed += 1

        try:
            ok = (
                self.nffi._status_to_nffi("active") == "OPERATIONAL"
                and self.nffi._status_to_nffi("damaged") == "DEGRADED"
                and self.nffi._status_to_nffi("destroyed") == "DESTROYED"
                and self.nffi._nffi_to_status("DEGRADED") == "damaged"
            )
            results.append({"test": "nffi_status_mapping", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "nffi_status_mapping", "passed": False, "error": str(exc)})
            failed += 1

        return {"tests_passed": passed, "tests_failed": failed, "results": results}

    def verify_symbology_conformance(self) -> dict:
        """Verify SIDC generation and validation across known entity catalogs."""
        results: List[dict] = []
        passed = 0
        failed = 0

        try:
            all_valid = True
            for entity_name in DIS_ENTITY_MAP:
                sidc = SymbologyMapper.map_track_symbology(
                    {
                        "entity_type": entity_name,
                        "type": entity_name,
                        "affiliation": "friendly" if entity_name.startswith("FRIENDLY_") else "hostile",
                        "domain": "land",
                    }
                )
                if not SIDCGenerator.is_valid_sidc(sidc):
                    all_valid = False
                    break
            results.append({"test": "sidc_generation_all_entity_types", "passed": all_valid})
            passed += int(all_valid)
            failed += int(not all_valid)
        except Exception as exc:
            results.append({"test": "sidc_generation_all_entity_types", "passed": False, "error": str(exc)})
            failed += 1

        try:
            all_dis_valid = True
            for entity_name, payload in DIS_ENTITY_MAP.items():
                dis_type = DISEntityType(
                    kind=int(payload["kind"]),
                    domain=int(payload["domain"]),
                    country=int(payload["country"]),
                    category=int(payload["category"]),
                    subcategory=int(payload.get("subcategory", 0)),
                    specific=0,
                    extra=0,
                )
                sidc = SymbologyMapper.map_track_symbology(
                    {
                        "dis_entity_type": dis_type,
                        "force_id": 1 if entity_name.startswith("FRIENDLY_") else 2,
                    }
                )
                if not SIDCGenerator.is_valid_sidc(sidc):
                    all_dis_valid = False
                    break
            results.append({"test": "sidc_from_dis_entity_type", "passed": all_dis_valid})
            passed += int(all_dis_valid)
            failed += int(not all_dis_valid)
        except Exception as exc:
            results.append({"test": "sidc_from_dis_entity_type", "passed": False, "error": str(exc)})
            failed += 1

        return {"tests_passed": passed, "tests_failed": failed, "results": results}

    def verify_msdl_conformance(self) -> dict:
        results: List[dict] = []
        passed = 0
        failed = 0
        try:
            scenario = MSDLScenario(
                scenario_id="msdl-1",
                name="MSDL Test",
                description="Verification scenario",
                forces=[],
                environment={"terrain": "desert", "weather": "clear"},
                overlay={"boundaries": ["A"]},
                version="1.0",
                created_at=datetime.now(timezone.utc),
            )
            xml = self.msdl_gen.generate(scenario)
            parsed = self.msdl_parser.parse(xml)
            ok = parsed.scenario_id == "msdl-1" and parsed.name == "MSDL Test"
            results.append({"test": "msdl_roundtrip", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "msdl_roundtrip", "passed": False, "error": str(exc)})
            failed += 1

        return {"tests_passed": passed, "tests_failed": failed, "results": results}

    def verify_mtf_conformance(self) -> dict:
        results: List[dict] = []
        passed = 0
        failed = 0

        try:
            xml = self.mtf.format_message(
                report_type="INTSUM",
                content={
                    "summary_text": "Enemy coastal activity increased in sector bravo.",
                    "assessment_text": "Pattern indicates reconnaissance prior to probing action.",
                },
                originator="S3M INTEL CENTER",
                classification="SECRET",
            )
            parsed = self.mtf.parse_message(xml)
            ok = parsed["message_type"] == "INTSUM"
            results.append({"test": "mtf_intsum_roundtrip", "passed": ok})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "mtf_intsum_roundtrip", "passed": False, "error": str(exc)})
            failed += 1

        try:
            dtg = self.mtf._build_dtg(datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc))
            ok = dtg == "151430Z APR 2026"
            results.append({"test": "mtf_dtg_format", "passed": ok, "value": dtg})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "mtf_dtg_format", "passed": False, "error": str(exc)})
            failed += 1

        try:
            mapped = self.mtf._classification_to_nato("TOP_SECRET")
            ok = mapped == "COSMIC TOP SECRET"
            results.append({"test": "mtf_classification_mapping", "passed": ok, "value": mapped})
            passed += int(ok)
            failed += int(not ok)
        except Exception as exc:
            results.append({"test": "mtf_classification_mapping", "passed": False, "error": str(exc)})
            failed += 1

        return {"tests_passed": passed, "tests_failed": failed, "results": results}

    def verify_coordinate_accuracy(self) -> dict:
        tests = [
            ("Riyadh", 24.7136, 46.6753, 0.0),
            ("Mecca", 21.4225, 39.8262, 0.0),
        ]
        rows: List[dict] = []
        passed = 0
        failed = 0
        for name, lat, lon, alt in tests:
            x, y, z = self.coord.lla_to_ecef(lat, lon, alt)
            r_lat, r_lon, r_alt = self.coord.ecef_to_lla(x, y, z)
            err = self._distance_lla(lat, lon, alt, r_lat, r_lon, r_alt)
            ok = err < 1.0
            rows.append({"test": name, "passed": ok, "error_m": err})
            passed += int(ok)
            failed += int(not ok)
        return {"tests_passed": passed, "tests_failed": failed, "results": rows}

    def verify_taxii_transport_readiness(self) -> dict:
        """Validate local TAXII transport readiness without external network calls."""
        results: List[dict] = []
        passed = 0
        failed = 0

        client = TAXIIClient(server_url="http://localhost", collection_id="default")
        outbox_ok = Path(client.outbox_dir).exists()
        inbox_ok = Path(client.inbox_dir).exists()
        status = client.health_check()

        checks = [
            ("taxii_outbox_available", outbox_ok),
            ("taxii_inbox_available", inbox_ok),
            ("taxii_health_shape", {"offline_outbox_count", "cached_inbox_count", "connected"}.issubset(status.keys())),
        ]
        for name, ok in checks:
            results.append({"test": name, "passed": bool(ok)})
            passed += int(bool(ok))
            failed += int(not bool(ok))

        return {"tests_passed": passed, "tests_failed": failed, "results": results}

    def run_full_verification(self) -> dict:
        dis = self.verify_dis_conformance()
        c2 = self.verify_c2sim_conformance()
        cot = self.verify_cot_conformance()
        nffi = self.verify_nffi_conformance()
        symbology = self.verify_symbology_conformance()
        mtf = self.verify_mtf_conformance()
        msdl = self.verify_msdl_conformance()
        coords = self.verify_coordinate_accuracy()
        taxii = self.verify_taxii_transport_readiness()
        total_passed = (
            dis["tests_passed"]
            + c2["tests_passed"]
            + cot["tests_passed"]
            + nffi["tests_passed"]
            + symbology["tests_passed"]
            + mtf["tests_passed"]
            + msdl["tests_passed"]
            + coords["tests_passed"]
            + taxii["tests_passed"]
        )
        total_failed = (
            dis["tests_failed"]
            + c2["tests_failed"]
            + cot["tests_failed"]
            + nffi["tests_failed"]
            + symbology["tests_failed"]
            + mtf["tests_failed"]
            + msdl["tests_failed"]
            + coords["tests_failed"]
            + taxii["tests_failed"]
        )
        return {
            "summary": {"tests_passed": total_passed, "tests_failed": total_failed},
            "dis": dis,
            "c2sim": c2,
            "cot": cot,
            "nffi": nffi,
            "symbology": symbology,
            "mtf": mtf,
            "msdl": msdl,
            "coordinates": coords,
            "taxii": taxii,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def generate_report(self, results: dict) -> str:
        summary = results.get("summary", {})
        lines = [
            "S3M Interoperability Verification Report",
            f"Passed: {summary.get('tests_passed', 0)}",
            f"Failed: {summary.get('tests_failed', 0)}",
            "",
        ]
        for suite_name in ("dis", "c2sim", "cot", "nffi", "symbology", "mtf", "msdl", "coordinates", "taxii"):
            suite = results.get(suite_name, {})
            lines.append(f"[{suite_name.upper()}]")
            for row in suite.get("results", []):
                status = "PASS" if row.get("passed") else "FAIL"
                detail = row.get("error_m", row.get("error", ""))
                lines.append(f"- {status} {row.get('test')}: {detail}")
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _distance_lla(lat1: float, lon1: float, alt1: float, lat2: float, lon2: float, alt2: float) -> float:
        r = 6378137.0
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(1e-15, 1.0 - a)))
        horizontal = r * c
        return math.sqrt(horizontal * horizontal + (alt2 - alt1) ** 2)
