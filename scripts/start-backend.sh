#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_path="${project_root}/backend"
venv_python="${backend_path}/.venv/bin/python"

if [[ ! -x "${venv_python}" ]]; then
  echo "Backend environment is missing. Run ./scripts/setup.sh first." >&2
  exit 1
fi

env_args=()
if [[ -f "${project_root}/.env" ]]; then
  env_args=(--env-file "${project_root}/.env")
fi

cd "${backend_path}"
exec "${venv_python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 "${env_args[@]}"
