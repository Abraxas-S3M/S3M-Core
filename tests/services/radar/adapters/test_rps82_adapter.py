from __future__ import annotations

from datetime import timezone

import pytest

from services.radar.adapters.rps82_adapter import RPS82Adapter


def test_parse_raw_data_accepts_single_plot_payload() -> None:
    adapter = RPS82Adapter(radar_id="rps82-alpha")
    plots = adapter.parse_raw_data(
        {
            "timestamp": "2026-04-14T10:00:00Z",
            "range_km": 1.25,
            "bearing_deg": 45.0,
            "elevation_deg": 3.5,
            "velocity_mps": -12.0,
            "rcs_dbsm": -8.0,
            "snr_db": 14.2,
        }
    )
    assert len(plots) == 1
    plot = plots[0]
    assert plot.radar_id == "rps82-alpha"
    assert plot.range_m == pytest.approx(1250.0)
    assert plot.azimuth_deg == pytest.approx(45.0)
    assert plot.timestamp.tzinfo == timezone.utc


def test_parse_raw_data_accepts_plot_list() -> None:
    adapter = RPS82Adapter()
    plots = adapter.parse_raw_data(
        {
            "plots": [
                {"timestamp": "2026-04-14T10:00:00+03:00", "range_m": 1000, "azimuth_deg": 10},
                {"timestamp": "2026-04-14T10:00:01+03:00", "range_m": 2000, "azimuth_deg": 20},
            ]
        }
    )
    assert len(plots) == 2
    assert plots[0].timestamp.tzinfo == timezone.utc
    assert plots[1].range_m == pytest.approx(2000.0)


def test_parse_raw_data_rejects_non_dict_payload() -> None:
    adapter = RPS82Adapter()
    with pytest.raises(ValueError, match="raw_data must be a dictionary"):
        adapter.parse_raw_data(["not", "a", "dict"])  # type: ignore[arg-type]


def test_parse_raw_data_rejects_invalid_plot_shape() -> None:
    adapter = RPS82Adapter()
    with pytest.raises(ValueError, match="raw_data\\['plots'\\] must be a list"):
        adapter.parse_raw_data({"plots": {"timestamp": "2026-04-14T10:00:00Z"}})


def test_parse_raw_data_rejects_invalid_timestamp() -> None:
    adapter = RPS82Adapter()
    with pytest.raises(ValueError, match="timestamp must be valid ISO-8601"):
        adapter.parse_raw_data({"timestamp": "not-a-timestamp", "range_m": 100, "azimuth_deg": 15})
