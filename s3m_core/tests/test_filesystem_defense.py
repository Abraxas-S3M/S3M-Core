"""Unit tests for filesystem defense controls in S3M core."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

from s3m_core.defense.filesystem.credential_scrubber import CredentialScrubber
from s3m_core.defense.filesystem.git_guardian import GitGuardian
from s3m_core.defense.filesystem.integrity_monitor import FilesystemIntegrityMonitor
from s3m_core.defense.filesystem.overlay_manager import OverlayFSManager


def test_integrity_monitor_baseline_and_verify_detects_drift(tmp_path: Path) -> None:
    """Mission file hash drift should be detected as tampering."""
    root = tmp_path / "mission_workspace"
    root.mkdir()
    (root / "orders.txt").write_text("alpha\n", encoding="utf-8")
    (root / "to_delete.txt").write_text("remove-me\n", encoding="utf-8")

    monitor = FilesystemIntegrityMonitor([str(root)])
    baseline = monitor.baseline(str(root))
    assert "orders.txt" in baseline
    assert "to_delete.txt" in baseline

    (root / "orders.txt").write_text("bravo\n", encoding="utf-8")
    (root / "intel.txt").write_text("new-file\n", encoding="utf-8")
    (root / "to_delete.txt").unlink()

    report = monitor.verify_integrity()
    assert report.tampered is True
    assert any(path.endswith("orders.txt") for path in report.modified)
    assert any(path.endswith("intel.txt") for path in report.added)
    assert any(path.endswith("to_delete.txt") for path in report.deleted)


def test_integrity_monitor_severity_classification() -> None:
    """Severity should escalate for system and credential-relevant paths."""
    monitor = FilesystemIntegrityMonitor(["/tmp"])
    assert monitor._classify_severity("/etc/passwd") == "critical"
    assert monitor._classify_severity("/workspace/.env") == "suspicious"
    assert monitor._classify_severity("/workspace/mission/notes.txt") == "routine"


def test_overlay_manager_get_changes_and_commit(tmp_path: Path, monkeypatch) -> None:
    """Overlay upperdir should expose complete and auditable change inventory."""
    base = tmp_path / "base"
    base.mkdir()
    (base / "keep.txt").write_text("original\n", encoding="utf-8")

    manager = OverlayFSManager(str(base), work_dir=str(tmp_path / "overlay_work"))

    def _fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("s3m_core.defense.filesystem.overlay_manager.subprocess.run", _fake_run)
    mount = manager.create_overlay("session-01")

    upper = Path(mount.upper_path)
    (upper / "keep.txt").write_text("updated\n", encoding="utf-8")
    (upper / "created.txt").write_text("new\n", encoding="utf-8")
    (upper / ".wh.deleted.txt").write_text("", encoding="utf-8")

    changes = manager.get_changes("session-01")
    summary = {(change.path, change.change_type) for change in changes}
    assert ("keep.txt", "modified") in summary
    assert ("created.txt", "created") in summary
    assert ("deleted.txt", "deleted") in summary

    manager.commit_changes("session-01", approved_paths=["keep.txt", "created.txt"])
    assert (base / "keep.txt").read_text(encoding="utf-8") == "updated\n"
    assert (base / "created.txt").read_text(encoding="utf-8") == "new\n"

    manager.discard("session-01")


def test_git_guardian_installs_hooks_and_audits_commit(tmp_path: Path) -> None:
    """Guardian should produce tactical audit signals for risky commit contents."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Agent"], cwd=repo, check=True)

    (repo / "app.py").write_text("print('hello')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, check=True)

    workflow_dir = repo / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    creds = repo / "creds.sh"
    creds.write_text("OPENAI_API_KEY=sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456\n", encoding="utf-8")
    creds.chmod(0o755)
    subprocess.run(["git", "add", ".github/workflows/ci.yml", "creds.sh"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "add ci and script"], cwd=repo, check=True)

    guardian = GitGuardian([str(repo)])
    guardian.install_hooks(str(repo))
    assert (repo / ".git" / "hooks" / "pre-receive").exists()
    assert (repo / ".git" / "hooks" / "post-receive").exists()

    history = guardian.verify_history(str(repo))
    assert history.total_commits >= 2
    assert len(history.merkle_root) == 64

    audit = guardian.diff_audit("HEAD")
    assert any(hit["pattern"] == "openai_key" for hit in audit.credential_hits)
    assert "creds.sh" in audit.new_executables
    assert any("workflows" in path for path in audit.cicd_changes)


def test_credential_scrubber_scan_scrub_and_environment(tmp_path: Path) -> None:
    """Credential scrubber should discover and redact secrets aggressively."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env_file = workspace / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456\n", encoding="utf-8")

    scrubber = CredentialScrubber([str(workspace)])
    findings = scrubber.scan()
    assert findings
    assert any(finding.credential_type == "openai_key" for finding in findings)

    report = scrubber.scrub(str(env_file), mode="redact")
    assert report.total_findings > 0
    assert report.files_modified >= 1
    assert "[REDACTED]" in env_file.read_text(encoding="utf-8")

    os.environ["TEST_API_TOKEN"] = "secret-token"
    scrubber.scrub_environment()
    assert "TEST_API_TOKEN" not in os.environ
    assert os.environ["TEST_API_TOKEN_VAULT_REF"] == "vault://d04/test_api_token"

    scrubber.install_watcher()
    scrubber.stop_watcher()
