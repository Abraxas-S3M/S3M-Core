#!/usr/bin/env python3
"""Demo focused on predictive maintenance model behavior."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from services.maintenance.models import (
    Asset,
    AssetCondition,
    AssetStatus,
    AssetType,
    SensorTelemetry,
)
from services.maintenance.predictive import FailureClassifier, RULEstimator


def _engine_asset(index: int) -> Asset:
    return Asset(
        asset_id=f"eng-{index}",
        name="Turbofan Engine",
        designation=f"TF-{index:03d}",
        asset_type=AssetType.AIRCRAFT,
        status=AssetStatus.OPERATIONAL,
        condition=AssetCondition.GOOD,
        serial_number=f"TF-SN-{index:03d}",
        manufacturer="S3M Aero",
        model="TF-900",
        acquisition_date=datetime.now(timezone.utc) - timedelta(days=700),
        operating_hours=1000 + index * 250,
        cycles=1800 + index * 100,
        location="Air Wing",
        assigned_unit="Engine Shop",
    )


def _generate_history(asset_id: str, cycles: int = 200) -> list[SensorTelemetry]:
    now = datetime.now(timezone.utc)
    points = []
    temp = 420.0
    vib = 2.2
    pressure = 38.0
    for i in range(cycles):
        temp += random.uniform(0.12, 0.6)
        vib += random.uniform(0.01, 0.04)
        pressure -= random.uniform(0.02, 0.08)
        points.append(
            SensorTelemetry(
                asset_id=asset_id,
                timestamp=now - timedelta(minutes=(cycles - i) * 5),
                readings={
                    **{f"sensor_{j}": random.uniform(-1.0, 1.0) for j in range(1, 22)},
                    "temperature_c": temp,
                    "vibration_g": vib,
                    "pressure_psi": pressure,
                    "oil_temp_c": 90.0 + (temp - 420.0) * 0.2,
                    "rpm": 12000 + random.uniform(-120, 120),
                    "fuel_flow_rate": 0.8 + random.uniform(-0.05, 0.08),
                    "rpm_deviation_pct": abs(random.uniform(-2.0, 2.0)),
                },
                operating_mode="cruise",
            )
        )
    return points


def main() -> None:
    random.seed(17)
    estimator = RULEstimator(model_backend="auto")
    classifier = FailureClassifier()

    assets = [_engine_asset(i + 1) for i in range(5)]
    histories = [_generate_history(asset.asset_id) for asset in assets]

    print("=== S3M Predictive Model Demo ===")
    print(f"Backend selected: {estimator.get_model_info()['backend']}")

    for asset, history in zip(assets, histories):
        pred = estimator.predict(history, asset)
        failure = classifier.classify(history[-1], asset.asset_type)
        print(
            f"{asset.designation}: RUL={pred.rul_hours:.1f}h "
            f"risk={pred.risk_level} conf={pred.confidence:.2f} "
            f"failure={failure['failure_mode']}"
        )
        print(
            f"  Degradation curve sample: temp_start={history[0].readings['temperature_c']:.1f} "
            f"temp_end={history[-1].readings['temperature_c']:.1f} "
            f"vib_end={history[-1].readings['vibration_g']:.2f}"
        )

    print("\\nComparison mode:")
    print("- Rule-based predictions always available in offline mode.")
    print("- ML predictions activate automatically if model artifacts and libraries exist.")


if __name__ == "__main__":
    main()
