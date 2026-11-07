.PHONY: range range-test range-smoke

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
