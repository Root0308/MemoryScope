#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_path="${project_root}/backend"
frontend_path="${project_root}/frontend"
venv_python="${backend_path}/.venv/bin/python"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11 or newer is required and was not found on PATH." >&2
  exit 1
fi
if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm 11.19.0 is required. Install it with: npm install --global pnpm@11.19.0" >&2
  exit 1
fi

if [[ ! -x "${venv_python}" ]]; then
  python3 -m venv "${backend_path}/.venv"
fi

(cd "${backend_path}" && "${venv_python}" -m pip install --upgrade pip && "${venv_python}" -m pip install -e ".[dev]")
(cd "${frontend_path}" && pnpm install --frozen-lockfile)

echo "MemoryScope dependencies are installed."
