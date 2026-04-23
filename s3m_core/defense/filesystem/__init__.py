"""Filesystem defense layer for mission auditability and tamper detection."""

from .credential_scrubber import CredentialFinding, CredentialScrubber, ScrubReport
from .git_guardian import DiffReport, GitGuardian, HistoryReport
from .integrity_monitor import FileChangeEvent, FilesystemIntegrityMonitor, IntegrityReport
from .overlay_manager import FileChange, OverlayFSManager, OverlayMount

__all__ = [
    "CredentialFinding",
    "CredentialScrubber",
    "DiffReport",
    "FileChange",
    "FileChangeEvent",
    "FilesystemIntegrityMonitor",
    "GitGuardian",
    "HistoryReport",
    "IntegrityReport",
    "OverlayFSManager",
    "OverlayMount",
    "ScrubReport",
]
