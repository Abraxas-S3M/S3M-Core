"""Unit tests for GPS denial/spoof monitoring."""

from __future__ import annotations

from src.navigation.localization.gps_monitor import GPSMonitor
from src.navigation.models import GPSQuality


def test_excellent_quality_detection():
    monitor = GPSMonitor()
    status = monitor.update(satellites=10, hdop=1.2, fix_type="3d", position=(0.0, 0.0, 0.0))
    assert status.quality == GPSQuality.EXCELLENT


def test_denied_quality_no_satellites():
    monitor = GPSMonitor()
    status = monitor.update(satellites=0, hdop=20.0, fix_type="none", position=None)
    assert status.quality == GPSQuality.DENIED
    assert monitor.is_denied() is True


def test_spoofed_detection_large_jump():
    monitor = GPSMonitor()
    monitor.update(satellites=9, hdop=1.8, fix_type="3d", position=(0.0, 0.0, 0.0))
    status = monitor.update(satellites=9, hdop=1.8, fix_type="3d", position=(1500.0, 0.0, 0.0))
    assert status.quality == GPSQuality.SPOOFED


def test_degraded_detection_borderline_hdop():
    monitor = GPSMonitor()
    status = monitor.update(satellites=4, hdop=9.0, fix_type="3d", position=(1.0, 2.0, 0.0))
    assert status.quality == GPSQuality.DEGRADED


def test_quality_transition_history():
    monitor = GPSMonitor()
    monitor.update(satellites=10, hdop=1.0, fix_type="3d", position=(0.0, 0.0, 0.0))
    monitor.update(satellites=2, hdop=20.0, fix_type="none", position=None)
    history = monitor.get_quality_history(limit=10)
    assert len(history) >= 1
    assert history[-1]["to"] in {"DENIED", "SPOOFED", "DEGRADED", "GOOD", "EXCELLENT"}


def test_simulate_denial_restore():
    monitor = GPSMonitor()
    monitor.simulate_denial()
    assert monitor.current_status.quality == GPSQuality.DENIED
    monitor.simulate_restore()
    assert monitor.current_status.quality == GPSQuality.GOOD
