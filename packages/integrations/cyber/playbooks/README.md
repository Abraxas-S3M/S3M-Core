# Playbooks Integration Wrapper

This wrapper integrates the [Playbooks](https://github.com/socfortress/Playbooks) repository into S3M cyber workflows.

## Military/Tactical Context

The adapter enables SOC operators to access incident-response playbooks during high-tempo defensive operations, including fully disconnected (airgapped) deployments on edge platforms.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local availability without external API calls
- Returns deterministic fixture responses in airgapped mode
- Optionally indexes a local repository mirror for markdown playbook references

## Configuration

- `PLAYBOOKS_REPO_PATH` or `S3M_PLAYBOOKS_REPO_PATH`: explicit local checkout path
- `INTEGRATION_VENDOR_ROOT` or `S3M_INTEGRATION_VENDOR_ROOT`: common local vendor root
- `S3M_AIRGAPPED=true`: force fixture-only execution

## Example

```python
from importlib import import_module

Adapter = import_module("packages.integrations.cyber.playbooks.adapter").PlaybooksAdapter
adapter = Adapter(mode="airgapped")
result = adapter.execute({"query": "ransomware", "limit": 5})
```

