#!/usr/bin/env bash
# Nightly: regenerate report JSON, rebuild the static site, push to the HF Space.
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/boreas report
(cd site && npm run build)
if command -v hf >/dev/null 2>&1; then
  hf upload sidnov6/boreas site/out . --repo-type space
else
  echo "hf CLI not found; skipping Space deploy"
fi
