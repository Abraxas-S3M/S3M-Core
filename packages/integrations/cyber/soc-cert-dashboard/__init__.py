"""SOC-CERT dashboard integration adapter for S3M."""

from __future__ import annotations

import importlib

SocCertDashboardAdapter = importlib.import_module(
    "packages.integrations.cyber.soc-cert-dashboard.adapter"
).SocCertDashboardAdapter

__all__ = ["SocCertDashboardAdapter"]
