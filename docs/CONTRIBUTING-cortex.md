# Contributing — Cortex & Cyber Authority

This guide covers pull-request gates for cortex-aligned changes (cyber IR adapters, formal authority models, and `s3m_core` defense modules).

## Branch protection (recommended)

Configure these settings on the default branch (`main`) in GitHub:

| Setting | Value |
|--------|--------|
| Required status checks | `security-core`, `opa`, `tla` |
| Required approving reviews | **1** human review (CODEOWNERS optional) |
| Dismiss stale reviews | On |
| Restrict force pushes | **Enabled** — no force-push to `main` |
| Require conversation resolution | On |

Optional but recommended: enable **pip-audit** and **gitleaks** report uploads as informational checks (they do not block merge).

## Local verification (matches PR `security-core` job)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
grep -vE '^(torch|#)' requirements.txt > /tmp/requirements-ci-core.txt
pip install -r /tmp/requirements-ci-core.txt -r requirements-security.txt -r requirements-api.txt
pip install pytest pytest-mock cryptography

export PYTHONPATH=.
pytest -m "not gpu and not slow" \
  tests/cortex tests/agents s3m_core/tests \
  tests/test_security_api.py tests/test_security_middleware.py \
  tests/test_comms_security.py tests/test_fmn_security.py \
  tests/test_quantum_security_shell.py \
  tests/integration/test_security_across_layers.py
```

When PyTorch is absent, modules that import `torch` are **skipped at collection** with an explicit reason (see `tests/pytest_optional_deps.py`).

## Formal models

- OPA: `opa test configs/opa_policies -v`
- TLA+: `formal/cortex/CyberAuthority.tla` + `formal/roe/roe_model_checker.py`

## Marker conventions

Registered in `pytest.ini`:

- `gpu` — CUDA / PyTorch workloads (excluded from PR CI)
- `slow` — long integration runs (nightly `full` job)
- `cortex` — cortex integration scenarios
- `range` — live-range only; never run in default CI
