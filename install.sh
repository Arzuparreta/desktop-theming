#!/usr/bin/env bash
# Preview installation by default. Never installs desktop components or packages.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$repo/scripts/install-platform.py" "$@"
