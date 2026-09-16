#!/usr/bin/env bash
set -e

DOCKERFILE_PATH=${1:-"Dockerfile"}

if [ ! -f "$DOCKERFILE_PATH" ]; then
  echo "Error: Dockerfile not found at $DOCKERFILE_PATH"
  exit 1
fi

echo "Checking $DOCKERFILE_PATH for hardcoded secrets..."

# Pattern 1: COPY .env
if grep -qE "^COPY\s+\.env" "$DOCKERFILE_PATH"; then
  echo "[FAIL] Found 'COPY .env' in $DOCKERFILE_PATH."
  echo "PARANOIA FRAMEWORK VIOLATION: Never copy .env into the image."
  exit 1
fi

# Pattern 2: Hardcoded sensitive ENV vars (e.g. KEY, TOKEN, SECRET, PASSWORD)
if grep -qE "^ENV\s+.*(KEY|TOKEN|SECRET|PASSWORD|URL)=" "$DOCKERFILE_PATH"; then
  echo "[FAIL] Found hardcoded secrets in ENV instructions in $DOCKERFILE_PATH."
  echo "PARANOIA FRAMEWORK VIOLATION: Inject secrets at runtime instead."
  grep -E "^ENV\s+.*(KEY|TOKEN|SECRET|PASSWORD|URL)=" "$DOCKERFILE_PATH"
  exit 1
fi

echo "[PASS] No hardcoded secrets found in $DOCKERFILE_PATH."
exit 0
