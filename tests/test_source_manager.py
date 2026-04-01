from __future__ import annotations

from pathlib import Path

from src.apps.intel.models import SourceType
from src.apps.intel.osint.source_manager import SourceManager


def test_create_default_sources_returns_12_sources(tmp_path: Path) -> None:
    cfg = tmp_path / "sources.yaml"
    manager = SourceManager(sources_config=str(cfg))
    created = manager.create_default_sources()
    assert len(created) == 12
    assert len(manager.get_sources(active_only=False)) == 12


def test_default_source_regions_and_reliability(tmp_path: Path) -> None:
    cfg = tmp_path / "sources.yaml"
    manager = SourceManager(sources_config=str(cfg))
    manager.create_default_sources()
    sources = manager.get_sources(active_only=False)
    red_sea_source = [s for s in sources if s.name == "Red Sea Maritime Intel"][0]
    assert "Red Sea" in red_sea_source.regions_covered
    assert red_sea_source.reliability.value == "A_RELIABLE"


def test_register_source_and_get_source(tmp_path: Path) -> None:
    cfg = tmp_path / "sources.yaml"
    manager = SourceManager(sources_config=str(cfg))
    source = manager.register_source(
        name="Test Feed",
        source_type="NEWS_FEED",
        reliability="B_USUALLY_RELIABLE",
        regions=["Arabian Peninsula"],
        topics=["diplomacy"],
        language="en",
        frequency="daily",
    )
    fetched = manager.get_source(source.source_id)
    assert fetched is not None
    assert fetched.name == "Test Feed"


def test_get_sources_filter_by_type_and_region(tmp_path: Path) -> None:
    cfg = tmp_path / "sources.yaml"
    manager = SourceManager(sources_config=str(cfg))
    manager.create_default_sources()
    maritime = manager.get_sources(source_type=SourceType.MARITIME_AIS, active_only=False)
    assert len(maritime) >= 2
    gulf = manager.get_sources(region="Persian Gulf", active_only=False)
    assert any("Persian Gulf" in s.regions_covered for s in gulf)


def test_deactivate_source_sets_active_false(tmp_path: Path) -> None:
    cfg = tmp_path / "sources.yaml"
    manager = SourceManager(sources_config=str(cfg))
    src = manager.register_source(
        name="Deactivate Me",
        source_type="ACADEMIC",
        reliability="F_UNKNOWN",
        regions=["Global"],
        topics=["regional_stability"],
        language="en",
        frequency="manual",
    )
    manager.deactivate_source(src.source_id)
    assert manager.get_source(src.source_id).active is False
