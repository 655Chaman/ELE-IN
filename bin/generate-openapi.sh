#!/bin/bash
# PARANOIA LAYER 1: CI/CD Stagnation Prevention
# This script must be run during build/deployment to guarantee openapi.json is never stale.

set -e
cd "$(dirname "$0")/.."

echo "[OpenAPI] Bootstrapping secure dummy environment..."
# We use a dummy 2048-bit RSA public key to bypass the startup security check safely without needing production keys.
DUMMY_PUB_KEY="LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUF4dFdEWUJzakdPV1JwV0JTVUJ4NQpWbThLc2tYY2JuOVF0dkVEd2NkaFpBS3RVUEdDVVo4cVB6UXMxdmlCSkpjUmFzY3E2Vitnb01GdElSdTJrdmVvCnY1cFdHdnVCZVU0d2F3VEtveTFKTnhuMnNwMzRSSW1maHg1SUhvSEhkMVlTMnl1QzZjazlJRllIMkJNTG0vRGgKY0lDUGhEMEt0eExGazBKZ2l3ZUM5bmtuWDFzTmZXRU1mNXBwK2pjSFI3ZDRVR0JDUkIrOXk0QThweTFybGVHeApyNEhidkh0VDB1RkRpM3JrSFpVNnVGdWpRa200bzVNQldqckFObkZqRHQ1UlgvbmV6bzMxTE0xcFcrczU0ZjVlCkxiMS96bXkza3d2aERBYkVSdG15REZsaW9vZFpFWDU3V3I4UzlTMFhEeVMrWllGMm1DdjY1d2QxV1hZRWJUdEgKSHdJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=="

export SUPABASE_JWT_SECRET="dummy_secret_for_generation_only_please_ignore"
export COOKIE_PUBLIC_KEY="$DUMMY_PUB_KEY"

echo "[OpenAPI] Activating backend virtual environment..."
if [ -d "backend/venv" ]; then
    source backend/venv/bin/activate
fi

echo "[OpenAPI] Generating live schema..."
python3 -c "
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.getcwd()))
from core.backend.main import app

with open('openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)
"

echo "[OpenAPI] Success. openapi.json is now perfectly synced with the codebase."
