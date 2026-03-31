"""Synthetic tabular generator for tactical cyber, sensor, and logistics datasets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
import csv
import ipaddress
import random
import uuid

try:
    import numpy as _np
except Exception:  # pragma: no cover - fallback path
    _np = None


class TabularGenerator:
    """Generate tabular synthetic datasets to train military analytics pipelines."""

    def __init__(self, backend: str = "auto") -> None:
        if not isinstance(backend, str):
            raise ValueError("backend must be a string")
        self.backend = backend
        self._sdv = None
        if backend in {"auto", "sdv"}:
            try:
                import sdv  # type: ignore

                self._sdv = sdv
                self.backend = "sdv"
            except Exception:
                self.backend = "numpy"
        if self.backend not in {"sdv", "numpy"}:
            self.backend = "numpy"

    def _rand_ip(self) -> str:
        return str(ipaddress.IPv4Address(random.randint(1, (1 << 32) - 1)))

    def _rand_choice(self, values: List[Any]) -> Any:
        if _np is not None:
            return _np.random.choice(values).item()
        return random.choice(values)

    def _rand_uniform(self, low: float, high: float) -> float:
        if _np is not None:
            return float(_np.random.uniform(low, high))
        return random.uniform(low, high)

    def _rand_poisson(self, lam: float) -> int:
        if _np is not None:
            return int(_np.random.poisson(lam))
        return max(0, int(random.gauss(lam, max(1.0, lam * 0.25))))

    def _rand_normal(self, mean: float, std: float) -> float:
        if _np is not None:
            return float(_np.random.normal(mean, std))
        return random.gauss(mean, std)

    def generate_network_traffic(self, n_records: int = 10000, attack_ratio: float = 0.1) -> dict:
        """Generate CIC-IDS-like traffic records for threat classifier rehearsal."""
        if n_records <= 0:
            raise ValueError("n_records must be positive")
        if not 0.0 <= attack_ratio <= 1.0:
            raise ValueError("attack_ratio must be between 0 and 1")

        columns = [
            "timestamp",
            "src_ip",
            "dst_ip",
            "src_port",
            "dst_port",
            "protocol",
            "duration",
            "bytes_in",
            "bytes_out",
            "packets",
            "label",
            "attack_type",
        ]
        protocols = ["TCP", "UDP", "ICMP"]
        normal_ports = [80, 443, 22, 53, 123]
        attack_ports = [1337, 31337, 4444, 5555, 6667]
        attack_types = ["dos", "scan", "exfiltration", "command_and_control", "lateral_movement"]

        rows: List[List[Any]] = []
        for _ in range(n_records):
            is_attack = self._rand_uniform(0.0, 1.0) < attack_ratio
            protocol = self._rand_choice(protocols)
            src_port = int(self._rand_uniform(1024, 65535))
            dst_port = int(self._rand_choice(attack_ports if is_attack else normal_ports))
            duration = max(0.001, self._rand_normal(0.5, 0.3) if not is_attack else self._rand_normal(15.0, 8.0))
            bytes_in = max(1, self._rand_poisson(2000 if not is_attack else 25000))
            bytes_out = max(1, self._rand_poisson(1800 if not is_attack else 40000))
            packets = max(1, self._rand_poisson(40 if not is_attack else 350))
            rows.append(
                [
                    datetime.now(timezone.utc).isoformat(),
                    self._rand_ip(),
                    self._rand_ip(),
                    src_port,
                    dst_port,
                    protocol,
                    round(duration, 3),
                    int(bytes_in),
                    int(bytes_out),
                    int(packets),
                    "attack" if is_attack else "normal",
                    self._rand_choice(attack_types) if is_attack else "none",
                ]
            )

        attack_count = sum(1 for row in rows if row[10] == "attack")
        return {
            "data": rows,
            "columns": columns,
            "stats": {
                "record_count": n_records,
                "attack_count": attack_count,
                "attack_ratio_actual": attack_count / n_records,
            },
        }

    def generate_sensor_telemetry(self, n_records: int = 5000, n_sensors: int = 10, anomaly_ratio: float = 0.05) -> dict:
        """Generate synthetic telemetry with anomaly labels for resilience drills."""
        if n_records <= 0 or n_sensors <= 0:
            raise ValueError("n_records and n_sensors must be positive")
        if not 0.0 <= anomaly_ratio <= 1.0:
            raise ValueError("anomaly_ratio must be between 0 and 1")

        columns = [
            "sensor_id",
            "timestamp",
            "temperature",
            "vibration",
            "signal_strength",
            "power_draw",
            "is_anomaly",
        ]
        rows: List[List[Any]] = []
        for _ in range(n_records):
            sensor_idx = int(self._rand_uniform(1, n_sensors + 1))
            anomaly = self._rand_uniform(0.0, 1.0) < anomaly_ratio
            if anomaly:
                temperature = self._rand_normal(95.0, 12.0)
                vibration = max(0.0, self._rand_normal(8.5, 2.5))
                signal = max(0.0, min(1.0, self._rand_normal(0.25, 0.15)))
                power = max(0.0, self._rand_normal(220.0, 40.0))
            else:
                temperature = self._rand_normal(62.0, 6.0)
                vibration = max(0.0, self._rand_normal(2.1, 0.6))
                signal = max(0.0, min(1.0, self._rand_normal(0.82, 0.08)))
                power = max(0.0, self._rand_normal(145.0, 20.0))
            rows.append(
                [
                    f"sensor-{sensor_idx:03d}",
                    datetime.now(timezone.utc).isoformat(),
                    round(temperature, 3),
                    round(vibration, 3),
                    round(signal, 4),
                    round(power, 3),
                    anomaly,
                ]
            )
        return {
            "data": rows,
            "columns": columns,
            "stats": {
                "record_count": n_records,
                "sensor_count": n_sensors,
                "anomaly_count": sum(1 for row in rows if row[-1]),
            },
        }

    def generate_logistics_data(self, n_records: int = 2000) -> dict:
        """Generate synthetic military logistics flow with disruption outcomes."""
        if n_records <= 0:
            raise ValueError("n_records must be positive")

        columns = [
            "shipment_id",
            "origin",
            "destination",
            "weight",
            "priority",
            "departure_time",
            "arrival_time",
            "status",
            "delay_hours",
        ]
        origins = ["Riyadh Depot", "Jeddah Naval Yard", "Tabuk FOB", "Dammam Hub"]
        destinations = ["Sector Alpha", "Sector Bravo", "Sector Charlie", "Forward Base Delta"]
        priorities = ["low", "medium", "high", "critical"]
        statuses = ["on_time", "delayed", "damaged", "rerouted"]
        rows: List[List[Any]] = []
        for _ in range(n_records):
            departure = datetime.now(timezone.utc)
            transit_hours = max(1.0, self._rand_normal(18.0, 6.0))
            status = self._rand_choice(statuses)
            delay = 0.0
            if status == "delayed":
                delay = max(0.5, self._rand_normal(4.0, 2.0))
            elif status == "damaged":
                delay = max(1.0, self._rand_normal(6.0, 3.0))
            elif status == "rerouted":
                delay = max(2.0, self._rand_normal(8.0, 3.5))
            arrival = departure.timestamp() + (transit_hours + delay) * 3600.0
            rows.append(
                [
                    f"ship-{uuid.uuid4().hex[:12]}",
                    self._rand_choice(origins),
                    self._rand_choice(destinations),
                    round(max(10.0, self._rand_normal(1800.0, 650.0)), 3),
                    self._rand_choice(priorities),
                    departure.isoformat(),
                    datetime.fromtimestamp(arrival, tz=timezone.utc).isoformat(),
                    status,
                    round(delay, 3),
                ]
            )

        return {
            "data": rows,
            "columns": columns,
            "stats": {"record_count": n_records, "status_breakdown": {s: sum(1 for row in rows if row[7] == s) for s in statuses}},
        }

    def save_csv(self, data: dict, filepath: str) -> str:
        """Save generated tabular output to CSV for downstream ML ingestion."""
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        rows = data.get("data", [])
        columns = data.get("columns", [])
        with open(filepath, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(rows)
        return filepath
