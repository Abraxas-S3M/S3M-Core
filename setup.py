"""Wheel/sdist packaging with customer-profile exclusions for offensive tooling."""

from __future__ import annotations

import os

from setuptools import find_packages, setup


def _packages() -> list[str]:
    packages = find_packages(
        where=".",
        include=["src*", "services*", "packages*", "s3m_core*", "apps*"],
    )
    profile = os.environ.get("S3M_BUILD_PROFILE", "customer").strip().lower()
    if profile == "customer":
        packages = [
            pkg
            for pkg in packages
            if pkg != "services.cyber.offensive"
            and not pkg.startswith("services.cyber.offensive.")
        ]
    return packages


setup(
    packages=_packages(),
    package_dir={"": "."},
)
