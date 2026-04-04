"""Unit tests for ISA and NUMA detection in the hardware profiler."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.edge_runtime.hardware_profiler import HardwareProfiler, HardwareTier


def test_probe_isa_capabilities_x86_from_proc_cpuinfo(monkeypatch) -> None:
    cpuinfo = "flags\t: fpu sse2 avx2 avx512f avx512_bf16 avx512_vnni\n"
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    monkeypatch.setattr("platform.system", lambda: "Linux")

    def fake_exists(self: Path) -> bool:
        return str(self) == "/proc/cpuinfo"

    def fake_read_text(self: Path, encoding: str = "utf-8", errors: str = "ignore") -> str:
        _ = (encoding, errors)
        if str(self) == "/proc/cpuinfo":
            return cpuinfo
        raise FileNotFoundError(str(self))

    monkeypatch.setattr(Path, "exists", fake_exists)
    monkeypatch.setattr(Path, "read_text", fake_read_text)

    caps = HardwareProfiler._probe_isa_capabilities()
    assert caps["avx2_supported"] is True
    assert caps["avx512_supported"] is True
    assert caps["avx512_bf16_supported"] is True
    assert caps["avx512_vnni_supported"] is True
    assert caps["simd_register_width_bits"] == 512


def test_probe_isa_capabilities_arm_macos_sysctl_fallback(monkeypatch) -> None:
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr(Path, "exists", lambda self: False)

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        cmd = args[0]
        if cmd == ["sysctl", "-a"]:
            return SimpleNamespace(
                returncode=0,
                stdout="hw.optional.neon: 1\nhw.optional.sve: 1\n",
            )
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr("subprocess.run", fake_run)

    caps = HardwareProfiler._probe_isa_capabilities()
    assert caps["arm_neon_supported"] is True
    assert caps["arm_sve_supported"] is True
    assert int(caps["simd_register_width_bits"]) >= 128


def test_probe_numa_nodes_from_sysfs(monkeypatch) -> None:
    class _Entry:
        def __init__(self, name: str):
            self.name = name

        def is_dir(self) -> bool:
            return True

    root = "/sys/devices/system/node"
    monkeypatch.setattr(Path, "exists", lambda self: str(self) == root)

    def fake_iterdir(self: Path):  # type: ignore[no-untyped-def]
        if str(self) == root:
            return iter([_Entry("node0"), _Entry("node1"), _Entry("cpu0")])
        return iter([])

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    assert HardwareProfiler._probe_numa_nodes() == 2


def test_run_populates_isa_fields_and_tier_metadata() -> None:
    profiler = HardwareProfiler()
    isa = {
        "avx2_supported": True,
        "avx512_supported": True,
        "avx512_bf16_supported": True,
        "avx512_vnni_supported": True,
        "arm_neon_supported": False,
        "arm_sve_supported": False,
        "simd_register_width_bits": 512,
    }

    with patch.object(HardwareProfiler, "_probe_cpu_cores", return_value=8), patch.object(
        HardwareProfiler, "_probe_cpu_arch", return_value="x86_64"
    ), patch.object(HardwareProfiler, "_probe_memory", return_value=(32.0, 24.0)), patch.object(
        HardwareProfiler, "_probe_disk", return_value=(256.0, 120.0)
    ), patch.object(
        HardwareProfiler, "_probe_gpu", return_value=(False, None, 0, False)
    ), patch.object(
        HardwareProfiler, "_probe_thermal_zone", return_value=47.5
    ), patch.object(
        HardwareProfiler, "_probe_power_source", return_value="mains"
    ), patch.object(
        HardwareProfiler, "_probe_active_links", return_value=["eth0"]
    ), patch.object(
        HardwareProfiler, "_probe_isa_capabilities", return_value=isa
    ), patch.object(
        HardwareProfiler, "_probe_numa_nodes", return_value=2
    ):
        profile = profiler.run()

    assert profile.tier == HardwareTier.CPU_STANDARD
    assert profile.avx512_bf16_supported is True
    assert profile.numa_node_count == 2
    assert profile.tier_metadata.get("cpu_precision_path") == "avx512_bf16"
    payload = profile.to_dict()
    assert payload["simd_register_width_bits"] == 512
    assert payload["tier_metadata"]["tier_note"] == "cpu_standard_bf16_accelerated"

