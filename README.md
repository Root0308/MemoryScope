# MemoryScope

MemoryScope is a new, independent, local-first tool for inspecting and evaluating agent memory retrieval. M2 adds strict conversation JSON import, transactional SQLite storage, dataset management, and message-level memory preview.

Implemented through M2:

- React, TypeScript, and Vite frontend
- FastAPI backend and health endpoint
- Strict MemoryScope schema 0.1 validation
- SQLite tables for datasets, memories, evaluation cases, and relevance labels
- Atomic import, dataset list/detail, paginated memories, and cascading deletion
- pytest coverage for validation, limits, rollback, pagination, and deletion

BM25, Dense, Hybrid, retrieval, charts, and evaluation execution are intentionally not implemented yet.

## Requirements

- Git
- Node.js 20.19+ in the 20.x line, or Node.js 22.12+
- npm 10+
- Python 3.11+

No paid API, API key, model download, or external database is required for M2.

## Start the backend on Windows PowerShell

From the repository root:

```powershell
Set-Location ./backend
python -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If PowerShell blocks virtual-environment activation, enable scripts for the current terminal only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Backend addresses:

- Health: <http://127.0.0.1:8000/api/v1/health>
- OpenAPI: <http://127.0.0.1:8000/docs>

## Start the frontend on Windows PowerShell

Open a second PowerShell terminal at the repository root:

```powershell
Set-Location ./frontend
npm install
npm run dev -- --host 127.0.0.1
```

Open <http://127.0.0.1:5173>. Keep the backend terminal running.

## Import the example

Use the page's file picker or drag-and-drop area and select `examples/sample-dataset.json`. The same operation can be checked from PowerShell:

```powershell
$sampleJson = Get-Content -Raw ./examples/sample-dataset.json
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/v1/datasets/import `
  -Method Post `
  -ContentType application/json `
  -Body $sampleJson
```

Import is all-or-nothing: invalid data is rejected and the transaction is rolled back.

## Verification

```powershell
Set-Location ./backend
./.venv/Scripts/Activate.ps1
python -m pytest
```

```powershell
Set-Location ./frontend
npm run typecheck
npm run build
```

## Configuration and local data

See `.env.example`. Defaults are usable without copying the file when commands are run from `backend` and `frontend` as shown above.

- `MEMORYSCOPE_DATABASE_PATH` selects the local SQLite file; default: `backend/data/memoryscope.db` when the backend is started from `backend`.
- `MEMORYSCOPE_CORS_ORIGINS` controls allowed frontend origins.
- `VITE_API_BASE_URL` tells the frontend where the backend is running.

SQLite databases, environment overrides, dependencies, build outputs, Python caches, and future downloaded model files are excluded from Git.

## Documentation

- [Product specification](docs/product-spec.md)
- [Data format](docs/data-format.md)
- [API](docs/api.md)
- [Example dataset](examples/sample-dataset.json)

## License

MemoryScope is licensed under the [MIT License](LICENSE).
