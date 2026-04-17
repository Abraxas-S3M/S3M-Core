#!/usr/bin/env python3
"""Unit tests for S3M tamper-proof audit and forensics layer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from s3m_core.defense.audit import (
    AuditEntry,
    ForensicReport,
    ForensicSnapshot,
    IncidentReporter,
    MerkleAuditLog,
    ThreatAssessment,
    TimelineEvent,
)


class TestMerkleAuditLog(unittest.TestCase):
    def test_append_verify_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "audit.jsonl"
            audit = MerkleAuditLog(str(log_path))

            t0 = datetime.now(timezone.utc)
            first_hash = audit.append(
                AuditEntry(
                    timestamp=t0,
                    session_id="sess-1",
                    event_type="policy_check",
                    source_layer="action_gate",
                    severity="medium",
                    details={"rule": "no_external_api"},
                    previous_hash="GENESIS",
                )
            )
            second_hash = audit.append(
                AuditEntry(
                    timestamp=t0 + timedelta(seconds=3),
                    session_id="sess-1",
                    event_type="tool_execute",
                    source_layer="execution_gate",
                    severity="high",
                    details={"tool": "shell"},
                    previous_hash=first_hash,
                )
            )
            self.assertTrue(second_hash)

            report = audit.verify_integrity()
            self.assertTrue(report.chain_intact)
            self.assertEqual(report.entries_verified, 2)
            self.assertIsNone(report.first_broken_entry)

            exported_json = audit.export(start=t0 - timedelta(seconds=1), end=t0 + timedelta(minutes=1))
            parsed = json.loads(exported_json)
            self.assertEqual(len(parsed), 2)
            self.assertEqual(parsed[1]["entry_hash"], second_hash)

            exported_csv = audit.export(
                start=t0 - timedelta(seconds=1),
                end=t0 + timedelta(minutes=1),
                format="csv",
            )
            self.assertIn("session_id", exported_csv)
            self.assertIn("execution_gate", exported_csv)

    def test_verify_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "audit.jsonl"
            audit = MerkleAuditLog(str(log_path))
            t0 = datetime.now(timezone.utc)
            first_hash = audit.append(
                AuditEntry(
                    timestamp=t0,
                    session_id="sess-2",
                    event_type="alert",
                    source_layer="sae_monitor",
                    severity="critical",
                    details={"feature": "security_bypass"},
                    previous_hash="GENESIS",
                )
            )
            audit.append(
                AuditEntry(
                    timestamp=t0 + timedelta(seconds=1),
                    session_id="sess-2",
                    event_type="containment",
                    source_layer="orchestrator",
                    severity="high",
                    details={"mode": "halt"},
                    previous_hash=first_hash,
                )
            )

            rows = log_path.read_text(encoding="utf-8").splitlines()
            first_entry = json.loads(rows[0])
            first_entry["details"] = {"feature": "tampered"}
            rows[0] = json.dumps(first_entry, ensure_ascii=False, sort_keys=True)
            log_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

            report = MerkleAuditLog(str(log_path)).verify_integrity()
            self.assertFalse(report.chain_intact)
            self.assertEqual(report.first_broken_entry, 1)

    def test_verify_raises_without_read_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "audit.jsonl"
            audit = MerkleAuditLog(str(log_path))
            t0 = datetime.now(timezone.utc)
            audit.append(
                AuditEntry(
                    timestamp=t0,
                    session_id="sess-3",
                    event_type="init",
                    source_layer="monitoring",
                    severity="low",
                    details={"ok": True},
                    previous_hash="GENESIS",
                )
            )
            with patch("pathlib.Path.open", side_effect=PermissionError("blocked")):
                with self.assertRaises(PermissionError):
                    audit.verify_integrity()


class TestForensicSnapshot(unittest.TestCase):
    def test_capture_produces_signed_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = ForensicSnapshot(
                snapshot_dir=temp_dir,
                signing_key=b"mission-signing-key",
                execution_history_provider=lambda session: [
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "command": "python mission.py",
                    }
                ],
                egress_traffic_provider=lambda session: [{"timestamp": "2026-01-01T00:00:00+00:00", "dst": "10.1.0.1"}],
                audit_entries_provider=lambda session: [
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "event_type": "threat_detected",
                        "source_layer": "monitoring",
                        "severity": "critical",
                        "details": {"target": "/workspace/configs/ops.yaml"},
                    }
                ],
                sae_timeline_provider=lambda session: [{"timestamp": "2026-01-01T00:00:01+00:00", "feature": 11}],
                emotion_timeline_provider=lambda session: [{"timestamp": "2026-01-01T00:00:02+00:00", "stress": 0.9}],
                verbalizer_provider=lambda session: [{"timestamp": "2026-01-01T00:00:03+00:00", "description": "risk spike"}],
                thinking_text_provider=lambda session: ["step 1", "step 2"],
            )

            archive_path = Path(snapshot.capture("session-77", "container-alpha", "critical_sae"))
            self.assertTrue(archive_path.exists())
            self.assertTrue(Path(f"{archive_path}.sha256").exists())
            self.assertTrue(Path(f"{archive_path}.sig").exists())

            with tarfile.open(archive_path, "r:gz") as archive:
                names = archive.getnames()
            self.assertTrue(any(name.endswith("snapshot_manifest.json") for name in names))
            self.assertTrue(any(name.endswith("audit_entries.json") for name in names))

    def test_analyze_returns_forensic_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot = ForensicSnapshot(
                snapshot_dir=temp_dir,
                audit_entries_provider=lambda session: [
                    {
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "event_type": "credential_access_attempt",
                        "source_layer": "action_gate",
                        "severity": "critical",
                        "details": {"path": "/secrets/token"},
                    }
                ],
                execution_history_provider=lambda session: [
                    {
                        "timestamp": "2026-01-01T00:00:02+00:00",
                        "command": "cat /secrets/token",
                    }
                ],
            )
            archive_path = snapshot.capture("session-78", "container-beta", "credential_anomaly")
            report = snapshot.analyze(archive_path)
            self.assertIsInstance(report, ForensicReport)
            self.assertGreaterEqual(report.confidence, 0.0)
            self.assertLessEqual(report.confidence, 1.0)
            self.assertTrue(report.attack_vector_identified)
            self.assertGreaterEqual(len(report.timeline), 1)

    def test_environment_capture_scrubs_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                "os.environ",
                {"S3M_TOKEN": "secret-value", "SAFE_VAR": "safe-value"},
                clear=False,
            ):
                snapshot = ForensicSnapshot(snapshot_dir=temp_dir)
                archive_path = Path(snapshot.capture("session-80", "container-gamma", "scrub_test"))

            extract_dir = Path(temp_dir) / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive_path, "r:gz") as archive:
                archive.extractall(path=extract_dir)
            env_files = list(extract_dir.rglob("environment.json"))
            self.assertTrue(env_files)
            env_payload = json.loads(env_files[0].read_text(encoding="utf-8"))
            self.assertEqual(env_payload["variables"]["S3M_TOKEN"], "[REDACTED]")
            self.assertEqual(env_payload["variables"]["SAFE_VAR"], "safe-value")


class TestIncidentReporter(unittest.TestCase):
    def _sample_forensic_report(self) -> ForensicReport:
        return ForensicReport(
            incident_summary="Suspicious egress and policy bypass observed.",
            attack_vector_identified="Suspicious outbound network/egress behavior detected.",
            data_compromised=["/workspace/configs/route.yaml"],
            timeline=[
                TimelineEvent(
                    timestamp=datetime.now(timezone.utc),
                    event="egress_spike",
                    source="egress_proxy",
                    details={"dst": "10.20.30.40"},
                )
            ],
            root_cause="Policy exception path lacked strict containment.",
            recommendations=["Block non-allowlisted egress", "Rotate mission tokens"],
            confidence=0.82,
        )

    def _sample_audit_entries(self) -> list[AuditEntry]:
        now = datetime.now(timezone.utc)
        return [
            AuditEntry(
                timestamp=now,
                session_id="session-99",
                event_type="egress_proxy_alert",
                source_layer="egress_proxy",
                severity="high",
                details={"target": "10.20.30.40"},
                previous_hash="GENESIS",
            ),
            AuditEntry(
                timestamp=now + timedelta(seconds=2),
                session_id="session-99",
                event_type="containment_initiated",
                source_layer="orchestrator",
                severity="critical",
                details={"action": "halt"},
                previous_hash="abc123",
            ),
        ]

    def test_generate_export_and_alert(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reporter = IncidentReporter(output_dir=temp_dir)
            report = reporter.generate_report(
                threat_assessment=ThreatAssessment(
                    severity="high",
                    category="policy_bypass",
                    score=0.91,
                    summary="Autonomous workflow attempted to bypass egress policy.",
                    impacted_assets=["egress_proxy", "orchestrator"],
                    recommended_actions=["Isolate session", "Start forensic triage"],
                ),
                forensic_report=self._sample_forensic_report(),
                audit_entries=self._sample_audit_entries(),
            )
            self.assertTrue(report.report_id.startswith("IR-"))
            self.assertEqual(report.severity, "high")
            self.assertTrue(report.title_ar)
            self.assertGreaterEqual(len(report.evidence), 1)

            pdf_path = Path(temp_dir) / "incident.pdf"
            reporter.export_pdf(report, str(pdf_path))
            self.assertTrue(pdf_path.exists())
            self.assertIn("S3M INCIDENT REPORT", pdf_path.read_text(encoding="utf-8"))

            reporter.send_alert(report, ["email", "slack", "sms", "dashboard"])
            alerts_dir = Path(temp_dir) / "alerts"
            self.assertTrue((alerts_dir / f"{report.report_id}_email.json").exists())
            self.assertTrue((alerts_dir / f"{report.report_id}_dashboard.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
