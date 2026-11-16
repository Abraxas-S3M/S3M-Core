"""S3M repository test package.

Military/tactical context:
This file makes ``tests`` a *regular* package so that ``tests.pytest_optional_deps``
(the plugin that lets Jetson-class edge CI skip modules whose heavy deps are absent)
always resolves to this repository.

Without it, ``tests`` is a PEP 420 namespace package, and any third-party wheel in
site-packages that ships its own top-level ``tests/__init__.py`` takes precedence,
which breaks plugin loading with ``No module named 'tests.pytest_optional_deps'``.
That is exactly the nightly ``full`` CI failure observed from 2026-11-08 onward.
"""
