"""Unit tests for austere edge hardware capability profiling."""

from __future__ import annotations

import builtins
from types import ModuleType, SimpleNamespace
from unittest.mock import mock_open, patch

from src.edge_runtime.hardware_profiler import HardwareProfiler, HardwareTier, NodeProfile


def test_node_profile_to_dict_rounding_and_tier_value() -> None:
    profile = NodeProfile(
        tier=HardwareTier.EDGE_GPU,
        cpu_cores=8,
        cpu_arch="aarch64",
        ram_total_gb=15.987,
        ram_available_gb=8.123,
        disk_total_gb=249.876,
        disk_free_gb=101.555,
        gpu_detected=True,
        gpu_name="Jetson",
        gpu_memory_mb=8192,
        cuda_available=True,
        thermal_zone_c=55.4,
        power_source="vehicle",
        active_links=["eth0"],
    )

    data = profile.to_dict()
    assert data["tier"] == "edge_gpu"
    assert data["ram_total_gb"] == 15.99
    assert data["disk_free_gb"] == 101.56
    assert data["active_links"] == ["eth0"]


def test_classify_vehicle_node_when_gpu_and_vehicle_power() -> None:
    tier = HardwareProfiler._classify(cores=8, ram_gb=32, gpu=True, thermal=60.0, power="vehicle")
    assert tier is HardwareTier.VEHICLE_NODE


def test_classify_fixed_site_when_large_gpu_host() -> None:
    tier = HardwareProfiler._classify(cores=16, ram_gb=64, gpu=True, thermal=None, power="mains")
    assert tier is HardwareTier.FIXED_SITE


def test_classify_cpu_austere_on_low_core_count() -> None:
    tier = HardwareProfiler._classify(cores=4, ram_gb=32, gpu=False, thermal=None, power="mains")
    assert tier is HardwareTier.CPU_AUSTERE


def test_probe_memory_conservative_fallback_on_error() -> None:
    with patch("builtins.open", side_effect=OSError("denied")):
        total, avail = HardwareProfiler._probe_memory()
    assert total == 4.0
    assert avail == 2.0


def test_probe_power_prefers_battery_then_vehicle_then_mains() -> None:
    with patch("os.path.exists", side_effect=lambda p: p == "/sys/class/power_supply/BAT0"):
        assert HardwareProfiler._probe_power() == "battery"

    with patch("os.path.exists", side_effect=lambda p: p == "/sys/bus/i2c/drivers/ina3221"):
        assert HardwareProfiler._probe_power() == "vehicle"

    with patch("os.path.exists", return_value=False):
        assert HardwareProfiler._probe_power() == "mains"


def test_probe_links_returns_only_non_loopback_up_interfaces() -> None:
    fake_files = {
        "/sys/class/net/eth0/operstate": "up",
        "/sys/class/net/wlan0/operstate": "down",
    }
    real_open = builtins.open

    def _open(path: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if path in fake_files:
            return mock_open(read_data=fake_files[path]).return_value
        return real_open(path, *args, **kwargs)

    with patch("os.listdir", return_value=["lo", "eth0", "wlan0"]), patch(
        "os.path.exists", side_effect=lambda p: p in fake_files
    ), patch("builtins.open", side_effect=_open):
        links = HardwareProfiler._probe_links()

    assert links == ["eth0"]


def test_probe_gpu_uses_torch_cuda_when_available(monkeypatch) -> None:
    fake_torch = ModuleType("torch")
    fake_torch.cuda = SimpleNamespace(
        is_available=lambda: True,
        get_device_name=lambda index: "Jetson Orin",
        get_device_properties=lambda index: SimpleNamespace(total_memory=16 * 1024 * 1024 * 1024),
    )

    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    detected, name, memory_mb, cuda_ok = HardwareProfiler._probe_gpu()
    assert (detected, name, memory_mb, cuda_ok) == (True, "Jetson Orin", 16384, True)


def test_run_builds_profile_with_detected_links() -> None:
    profiler = HardwareProfiler()

    with patch.object(HardwareProfiler, "_probe_memory", return_value=(16.0, 8.0)), patch.object(
        HardwareProfiler, "_probe_disk", return_value=(128.0, 64.0)
    ), patch.object(
        HardwareProfiler, "_probe_gpu", return_value=(False, None, 0, False)
    ), patch.object(
        HardwareProfiler, "_probe_thermal", return_value=49.0
    ), patch.object(
        HardwareProfiler, "_probe_power", return_value="mains"
    ), patch.object(
        HardwareProfiler, "_probe_links", return_value=["eth0", "wlan0"]
    ), patch(
        "os.cpu_count", return_value=8
    ), patch(
        "platform.machine", return_value="x86_64"
    ):
        profile = profiler.run()

    assert profile.tier is HardwareTier.CPU_STANDARD
    assert profile.active_links == ["eth0", "wlan0"]
    assert profiler.profile is profile
