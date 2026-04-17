"""Unit tests for s3m_core.defense.audit tamper-proof workflows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import tarfile
import tempfile
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


def test_merkle_audit_log_append_verify_and_export() -> None:
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
        assert second_hash

        report = audit.verify_integrity()
        assert report.chain_intact is True
        assert report.entries_verified == 2
        assert report.first_broken_entry is None

        exported_json = audit.export(start=t0 - timedelta(seconds=1), end=t0 + timedelta(minutes=1))
        parsed = json.loads(exported_json)
        assert len(parsed) == 2
        assert parsed[1]["entry_hash"] == second_hash

        exported_csv = audit.export(
            start=t0 - timedelta(seconds=1),
            end=t0 + timedelta(minutes=1),
            format="csv",
        )
        assert "session_id" in exported_csv
        assert "execution_gate" in exported_csv


def test_merkle_audit_log_detects_tampering() -> None:
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
        assert report.chain_intact is False
        assert report.first_broken_entry == 1


def test_forensic_snapshot_capture_and_analyze() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        snapshot = ForensicSnapshot(
            snapshot_dir=temp_dir,
            signing_key=b"mission-signing-key",
            execution_history_provider=lambda session: [
                {
                    "timestamp": "2026-01-01T00:00:02+00:00",
                    "command": "cat /secrets/token",
                }
            ],
            egress_traffic_provider=lambda session: [{"timestamp": "2026-01-01T00:00:00+00:00", "dst": "10.1.0.1"}],
            audit_entries_provider=lambda session: [
                {
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "event_type": "credential_access_attempt",
                    "source_layer": "action_gate",
                    "severity": "critical",
                    "details": {"path": "/secrets/token"},
                }
            ],
            sae_timeline_provider=lambda session: [{"timestamp": "2026-01-01T00:00:01+00:00", "feature": 11}],
            emotion_timeline_provider=lambda session: [{"timestamp": "2026-01-01T00:00:02+00:00", "stress": 0.9}],
            verbalizer_provider=lambda session: [{"timestamp": "2026-01-01T00:00:03+00:00", "description": "risk spike"}],
            thinking_text_provider=lambda session: ["step 1", "step 2"],
        )

        archive_path = Path(snapshot.capture("session-77", "container-alpha", "critical_sae"))
        assert archive_path.exists()
        assert Path(f"{archive_path}.sha256").exists()
        assert Path(f"{archive_path}.sig").exists()

        with tarfile.open(archive_path, "r:gz") as archive:
            names = archive.getnames()
        assert any(name.endswith("snapshot_manifest.json") for name in names)
        assert any(name.endswith("audit_entries.json") for name in names)

        report = snapshot.analyze(str(archive_path))
        assert isinstance(report, ForensicReport)
        assert 0.0 <= report.confidence <= 1.0
        assert report.attack_vector_identified
        assert len(report.timeline) >= 1


def test_forensic_snapshot_env_scrubbing_redacts_sensitive_values() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        snapshot = ForensicSnapshot(snapshot_dir=temp_dir)
        fake_env = {
            "PATH": "/usr/bin",
            "API_TOKEN": "secret-token-value",
            "DB_PASSWORD": "super-secret",
            "SAFE_NAME": "mission",
        }

        with patch("s3m_core.defense.audit.forensic_snapshot.os.environ", fake_env):
            archive_path = Path(snapshot.capture("session-100", "container-z", "manual_trigger"))

        with tarfile.open(archive_path, "r:gz") as archive:
            env_member = next(item for item in archive.getnames() if item.endswith("environment.json"))
            payload = json.loads(archive.extractfile(env_member).read().decode("utf-8"))  # type: ignore[union-attr]
            variables = payload["variables"]
            assert variables["API_TOKEN"] == "[REDACTED]"
            assert variables["DB_PASSWORD"] == "[REDACTED]"
            assert variables["PATH"] == "/usr/bin"


def test_incident_reporter_generate_export_and_alert() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        reporter = IncidentReporter(output_dir=temp_dir)
        forensic_report = ForensicReport(
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
        now = datetime.now(timezone.utc)
        audit_entries = [
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
        report = reporter.generate_report(
            threat_assessment=ThreatAssessment(
                severity="high",
                category="policy_bypass",
                score=0.91,
                summary="Autonomous workflow attempted to bypass egress policy.",
                impacted_assets=["egress_proxy", "orchestrator"],
                recommended_actions=["Isolate session", "Start forensic triage"],
            ),
            forensic_report=forensic_report,
            audit_entries=audit_entries,
        )
        assert report.report_id.startswith("IR-")
        assert report.severity == "high"
        assert report.title_ar
        assert len(report.evidence) >= 1

        pdf_path = Path(temp_dir) / "incident.pdf"
        reporter.export_pdf(report, str(pdf_path))
        assert pdf_path.exists()
        assert "S3M INCIDENT REPORT" in pdf_path.read_text(encoding="utf-8")

        reporter.send_alert(report, ["email", "slack", "sms", "dashboard"])
        alerts_dir = Path(temp_dir) / "alerts"
        assert (alerts_dir / f"{report.report_id}_email.json").exists()
        assert (alerts_dir / f"{report.report_id}_dashboard.json").exists()
