#!/usr/bin/env bash
set -euo pipefail

exec python -m uvicorn services.psp.main:app --host 0.0.0.0 --port "${PORT:-8002}"
