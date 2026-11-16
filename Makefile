.PHONY: range range-test range-smoke cortex-slice cortex-slice-test cortex-contract cortex-contract-test

PYTHON ?= python3

range:
	$(PYTHON) range/run_range.py --all-scenarios

range-test:
	$(PYTHON) -m pytest tests/range/ -q

range-smoke: range-test
	@if command -v sudo >/dev/null 2>&1; then \
		sudo iptables -C OUTPUT -d 203.0.113.53 -j REJECT 2>/dev/null || \
			sudo iptables -I OUTPUT -d 203.0.113.53 -j REJECT; \
		sudo iptables -C OUTPUT -d 8.8.8.8 -j REJECT 2>/dev/null || \
			sudo iptables -I OUTPUT -d 8.8.8.8 -j REJECT; \
	fi
	$(MAKE) range

# Cortex vertical slice (SIM-002, SIM-005) against the loopback mock XiiD MCP server.
cortex-slice:
	$(PYTHON) -m range.run_cortex_slice --scenario all

cortex-slice-test:
	$(PYTHON) -m pytest tests/cortex/test_vertical_slice.py -q

# Cortex cycle over the S3M control-plane MCP contract v0.1 (reference server, loopback).
cortex-contract:
	$(PYTHON) -m range.run_contract_cycle --scenario all

cortex-contract-test:
	$(PYTHON) -m pytest tests/cortex/test_mcp_contract.py -q
