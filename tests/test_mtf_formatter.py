"""Tests for APP-11 XML-MTF formatter behavior."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from xml.etree import ElementTree as ET

from services.interop.mtf.mtf_formatter import MTFFormatter


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _find(root: ET.Element, local_name: str) -> ET.Element | None:
    for node in root.iter():
        if _tag(node) == local_name:
            return node
    return None


def test_format_intsum_valid_xml():
    formatter = MTFFormatter(config={"originator": "S3M INTEL CENTER"})
    xml = formatter.format_message(
        report_type="INTSUM",
        content={
            "period_from": "150600Z APR 2026",
            "period_to": "151800Z APR 2026",
            "summary_text": "Enemy naval patrol tempo has increased near chokepoints.",
            "assessment_text": "Likely coercive signaling prior to diplomatic talks.",
        },
        originator="S3M J2",
        classification="SECRET",
    )
    root = ET.fromstring(xml)
    assert _tag(root) == "message"
    assert _find(root, "INTSUM") is not None
    assert _find(root, "PERIOD") is not None
    assert _find(root, "ASSESSMENT") is not None


def test_format_sitrep_valid_xml():
    formatter = MTFFormatter()
    xml = formatter.format_message(
        report_type="SITREP",
        content={
            "sitrep_text": "Friendly lines remain stable along sector alpha.",
            "ops_text": "ISR sorties increased by 20 percent over baseline.",
            "logistics_text": "Fuel and ammunition stocks remain above 72-hour threshold.",
        },
        originator="S3M J3",
        classification="CONFIDENTIAL",
    )
    root = ET.fromstring(xml)
    assert _find(root, "SITREP") is not None
    assert _find(root, "OPERATIONS") is not None
    assert _find(root, "LOGISTICS") is not None


def test_dtg_format_nato():
    formatter = MTFFormatter()
    dtg = formatter._build_dtg(datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc))
    assert dtg == "151430Z APR 2026"
    assert re.fullmatch(r"\d{6}Z [A-Z]{3} \d{4}", dtg)


def test_classification_mapping_all():
    formatter = MTFFormatter()
    assert formatter._classification_to_nato("UNCLASSIFIED") == "UNCLASSIFIED"
    assert formatter._classification_to_nato("FOUO") == "NATO UNCLASSIFIED"
    assert formatter._classification_to_nato("CONFIDENTIAL") == "NATO CONFIDENTIAL"
    assert formatter._classification_to_nato("SECRET") == "NATO SECRET"
    assert formatter._classification_to_nato("TOP_SECRET") == "COSMIC TOP SECRET"


def test_parse_message_roundtrip_intsum():
    formatter = MTFFormatter(config={"originator": "S3M INTEL CENTER"})
    xml = formatter.format_message(
        report_type="INTSUM",
        content={
            "period_from": "150600Z APR 2026",
            "period_to": "151800Z APR 2026",
            "summary_text": "Pattern of UAV reconnaissance continues in corridor delta.",
            "assessment_text": "Recommend persistent surveillance and route hardening.",
        },
        originator="S3M J2",
        classification="SECRET",
    )
    parsed = formatter.parse_message(xml)
    assert parsed["message_type"] == "INTSUM"
    assert parsed["content"]["summary_text"] == "Pattern of UAV reconnaissance continues in corridor delta."
    assert parsed["content"]["assessment_text"] == "Recommend persistent surveillance and route hardening."
    assert parsed["content"]["period_from"] == "150600Z APR 2026"
    assert parsed["content"]["period_to"] == "151800Z APR 2026"


def test_originator_from_config():
    formatter = MTFFormatter(config={"originator": "NATO-HQ"})
    xml = formatter.format_message(
        report_type="INTSUM",
        content={"summary_text": "Summary", "assessment_text": "Assessment"},
        originator="",
        classification="UNCLASSIFIED",
    )
    parsed = formatter.parse_message(xml)
    assert parsed["originator"] == "NATO-HQ"


def test_serial_auto_increments():
    formatter = MTFFormatter(config={"start_serial": 15})
    first = formatter.parse_message(
        formatter.format_message(
            report_type="INTSUM",
            content={"summary_text": "s1", "assessment_text": "a1"},
            originator="HQ",
            classification="UNCLASSIFIED",
        )
    )
    second = formatter.parse_message(
        formatter.format_message(
            report_type="INTSUM",
            content={"summary_text": "s2", "assessment_text": "a2"},
            originator="HQ",
            classification="UNCLASSIFIED",
        )
    )
    assert int(second["serial_number"]) == int(first["serial_number"]) + 1
