#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend_path="${project_root}/frontend"

if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm 11.19.0 is required. Install it with: npm install --global pnpm@11.19.0" >&2
  exit 1
fi
if [[ ! -d "${frontend_path}/node_modules" ]]; then
  echo "Frontend dependencies are missing. Run ./scripts/setup.sh first." >&2
  exit 1
fi

cd "${frontend_path}"
exec pnpm run dev -- --host 127.0.0.1
