#!/usr/bin/env bash
set -euo pipefail

# Simple helper to serve the static frontend locally.
# Usage: ./setup.sh [PORT]

PORT="${1:-4173}"

cd "$(dirname "$0")"
echo "Serving frontend on http://localhost:${PORT}"
python -m http.server "${PORT}"
