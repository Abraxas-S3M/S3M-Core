from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_validate_dataset_catalog_script_succeeds() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/catalog/validate_dataset_catalog.py"],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path.cwd(),
    )
    assert result.returncode == 0, result.stderr
    assert "Catalog validation PASSED." in result.stdout


def test_print_dataset_routes_script_outputs_expected_cases() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/catalog/print_dataset_routes.py"],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path.cwd(),
    )
    assert result.returncode == 0, result.stderr
    for needle in [
        "track=saudi_mod domains=['risk_readiness']",
        "track=saudi_mod domains=['cop_intel']",
        "track=saudi_mod domains=['cyber_electronic_warfare']",
        "track=saudi_mod domains=['logistics_sustainment']",
        "track=saudi_mod domains=['bilingual']",
    ]:
        assert needle in result.stdout
