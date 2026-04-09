# SOC-Multitool Integration Wrapper

This wrapper integrates the [SOC-Multitool](https://github.com/zdhenard42/SOC-Multitool) repository into S3M defensive cyber workflows.

## Military/Tactical Context

The adapter supports analyst tempo by exposing repeatable investigation workflows that can be used in disconnected mission environments.

## Capabilities

- Manifest-driven metadata loading
- Airgapped fixture execution
- Secure parameter validation
- Optional local repository indexing for markdown workflow references

## Configuration

- `SOC_MULTITOOL_REPO_PATH` or `S3M_SOC_MULTITOOL_REPO_PATH`
- `INTEGRATION_VENDOR_ROOT` or `S3M_INTEGRATION_VENDOR_ROOT`
- `S3M_AIRGAPPED=true` for fixture mode

