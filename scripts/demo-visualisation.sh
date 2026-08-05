#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-4173}"

if [[ ! "$PORT" =~ ^[1-9][0-9]{0,4}$ ]] || ((PORT > 65535)); then
  echo "Port must be an integer between 1 and 65535." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to serve the static demo." >&2
  exit 1
fi

echo "Second Sight visual demo: http://localhost:${PORT}/demo/"
echo "Press Ctrl-C to stop the local server."
python3 -m http.server "$PORT" --directory "$ROOT_DIR"
