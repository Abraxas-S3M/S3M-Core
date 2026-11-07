#!/bin/sh
# Build-time gate: customer Cortex images must not ship offensive cyber tooling.
set -eu

ROOT="${CORTEX_APP_ROOT:-/opt/s3m}"
OFFENSIVE="${ROOT}/services/cyber/offensive"

if [ -d "${OFFENSIVE}" ] || [ -e "${OFFENSIVE}" ]; then
  echo "CORTEX BUILD FAILURE: ${OFFENSIVE} is present; customer profile forbids offensive modules." >&2
  exit 1
fi

if [ "${S3M_BUILD_PROFILE:-}" != "customer" ]; then
  echo "CORTEX BUILD FAILURE: S3M_BUILD_PROFILE must be 'customer' (got '${S3M_BUILD_PROFILE:-unset}')." >&2
  exit 1
fi

echo "Cortex customer profile check passed (no offensive modules)."
