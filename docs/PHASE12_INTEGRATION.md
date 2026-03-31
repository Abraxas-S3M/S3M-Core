# Phase 12 Integration and Hardening

Classification: UNCLASSIFIED - FOUO

## Integration Tests
- `tests/integration/test_ooda_observe.py`
- `tests/integration/test_ooda_orient.py`
- `tests/integration/test_ooda_decide.py`
- `tests/integration/test_ooda_act.py`
- `tests/integration/test_ooda_full_loop.py`
- `tests/integration/test_simulation_to_training.py`
- `tests/integration/test_domain_app_pipelines.py`
- `tests/integration/test_dashboard_all_layers.py`
- `tests/integration/test_security_across_layers.py`
- `tests/integration/test_arabic_pipeline.py`

## Memory Budget Manager Usage
```python
from src.optimization import MemoryBudgetManager
mgr = MemoryBudgetManager(total_budget_gb=48)
mgr.register('llm_core', 'llm_core', 12000, priority=1)
print(mgr.generate_budget_report())
```

## Startup Sequencer
```python
from src.optimization import StartupSequencer
sequencer = StartupSequencer()
print(sequencer.run())
```

## Docker Deployment
- `docker/Dockerfile` for production
- `docker/Dockerfile.dev` for development
- `docker/docker-compose.yml` for service orchestration

## Smoke Test and Full Demo
- `python scripts/smoke_test.py`
- `python scripts/full_system_demo.py`

## Deployment Profiles
- `configs/deployment/development.yaml`
- `configs/deployment/production.yaml`
- `configs/deployment/field.yaml`

## Final Field Checklist
- [ ] Checklist 01: verify integration control and operator sign-off.
- [ ] Checklist 02: verify integration control and operator sign-off.
- [ ] Checklist 03: verify integration control and operator sign-off.
- [ ] Checklist 04: verify integration control and operator sign-off.
- [ ] Checklist 05: verify integration control and operator sign-off.
- [ ] Checklist 06: verify integration control and operator sign-off.
- [ ] Checklist 07: verify integration control and operator sign-off.
- [ ] Checklist 08: verify integration control and operator sign-off.
- [ ] Checklist 09: verify integration control and operator sign-off.
- [ ] Checklist 10: verify integration control and operator sign-off.
- [ ] Checklist 11: verify integration control and operator sign-off.
- [ ] Checklist 12: verify integration control and operator sign-off.
- [ ] Checklist 13: verify integration control and operator sign-off.
- [ ] Checklist 14: verify integration control and operator sign-off.
- [ ] Checklist 15: verify integration control and operator sign-off.
- [ ] Checklist 16: verify integration control and operator sign-off.
- [ ] Checklist 17: verify integration control and operator sign-off.
- [ ] Checklist 18: verify integration control and operator sign-off.
- [ ] Checklist 19: verify integration control and operator sign-off.
- [ ] Checklist 20: verify integration control and operator sign-off.
- [ ] Checklist 21: verify integration control and operator sign-off.
- [ ] Checklist 22: verify integration control and operator sign-off.
- [ ] Checklist 23: verify integration control and operator sign-off.
- [ ] Checklist 24: verify integration control and operator sign-off.
- [ ] Checklist 25: verify integration control and operator sign-off.
- [ ] Checklist 26: verify integration control and operator sign-off.
- [ ] Checklist 27: verify integration control and operator sign-off.
- [ ] Checklist 28: verify integration control and operator sign-off.
- [ ] Checklist 29: verify integration control and operator sign-off.
- [ ] Checklist 30: verify integration control and operator sign-off.
- [ ] Checklist 31: verify integration control and operator sign-off.
- [ ] Checklist 32: verify integration control and operator sign-off.
- [ ] Checklist 33: verify integration control and operator sign-off.
- [ ] Checklist 34: verify integration control and operator sign-off.
- [ ] Checklist 35: verify integration control and operator sign-off.
- [ ] Checklist 36: verify integration control and operator sign-off.
- [ ] Checklist 37: verify integration control and operator sign-off.
- [ ] Checklist 38: verify integration control and operator sign-off.
- [ ] Checklist 39: verify integration control and operator sign-off.
- [ ] Checklist 40: verify integration control and operator sign-off.
- [ ] Checklist 41: verify integration control and operator sign-off.
- [ ] Checklist 42: verify integration control and operator sign-off.
- [ ] Checklist 43: verify integration control and operator sign-off.
- [ ] Checklist 44: verify integration control and operator sign-off.
- [ ] Checklist 45: verify integration control and operator sign-off.
- [ ] Checklist 46: verify integration control and operator sign-off.
- [ ] Checklist 47: verify integration control and operator sign-off.
- [ ] Checklist 48: verify integration control and operator sign-off.
- [ ] Checklist 49: verify integration control and operator sign-off.
- [ ] Checklist 50: verify integration control and operator sign-off.
- [ ] Checklist 51: verify integration control and operator sign-off.
- [ ] Checklist 52: verify integration control and operator sign-off.
- [ ] Checklist 53: verify integration control and operator sign-off.
- [ ] Checklist 54: verify integration control and operator sign-off.
- [ ] Checklist 55: verify integration control and operator sign-off.
- [ ] Checklist 56: verify integration control and operator sign-off.
- [ ] Checklist 57: verify integration control and operator sign-off.
- [ ] Checklist 58: verify integration control and operator sign-off.
- [ ] Checklist 59: verify integration control and operator sign-off.
- [ ] Checklist 60: verify integration control and operator sign-off.
- [ ] Checklist 61: verify integration control and operator sign-off.
- [ ] Checklist 62: verify integration control and operator sign-off.
- [ ] Checklist 63: verify integration control and operator sign-off.
- [ ] Checklist 64: verify integration control and operator sign-off.
- [ ] Checklist 65: verify integration control and operator sign-off.
- [ ] Checklist 66: verify integration control and operator sign-off.
- [ ] Checklist 67: verify integration control and operator sign-off.
- [ ] Checklist 68: verify integration control and operator sign-off.
- [ ] Checklist 69: verify integration control and operator sign-off.
- [ ] Checklist 70: verify integration control and operator sign-off.
- [ ] Checklist 71: verify integration control and operator sign-off.
- [ ] Checklist 72: verify integration control and operator sign-off.
- [ ] Checklist 73: verify integration control and operator sign-off.
- [ ] Checklist 74: verify integration control and operator sign-off.
- [ ] Checklist 75: verify integration control and operator sign-off.
- [ ] Checklist 76: verify integration control and operator sign-off.
- [ ] Checklist 77: verify integration control and operator sign-off.
- [ ] Checklist 78: verify integration control and operator sign-off.
- [ ] Checklist 79: verify integration control and operator sign-off.
- [ ] Checklist 80: verify integration control and operator sign-off.