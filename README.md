# MemoryScope

MemoryScope is a local-first retrieval inspection and evaluation tool for agent memory. Version 0.1 is being built as a new, independent open-source project.

This repository currently contains only the M1 foundation:

- React, TypeScript, and Vite frontend
- FastAPI backend with `GET /api/v1/health`
- SQLite configuration placeholder
- pytest coverage for the health endpoint
- v0.1 product, data-format, and API documentation

JSON import, BM25, Dense retrieval, Hybrid retrieval, charts, and evaluation are intentionally not implemented in M1.

## Requirements

- Git
- Node.js 20.19 or newer in the 20.x line, or Node.js 22.12 or newer
- npm 10 or newer
- Python 3.11 or newer

No paid API, API key, or external database is required.

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

The backend is available at:

- Health: <http://127.0.0.1:8000/api/v1/health>
- OpenAPI: <http://127.0.0.1:8000/docs>

## Start the frontend on Windows PowerShell

Open a second PowerShell terminal at the repository root:

```powershell
Set-Location ./frontend
npm install
npm run dev
```

Then open <http://127.0.0.1:5173>. Keep the backend running so the page can display its health status.

If pnpm is preferred:

```powershell
Set-Location ./frontend
pnpm install
pnpm dev
```

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

## Configuration

The defaults work for local development. See `.env.example` for the available environment variables.

The example SQLite path is relative to the `backend` working directory used by the PowerShell commands above. The file is a configuration reference; the M1 defaults work without copying it.

- `MEMORYSCOPE_DATABASE_PATH` is reserved for the local SQLite file.
- `MEMORYSCOPE_CORS_ORIGINS` controls allowed browser origins.
- `VITE_API_BASE_URL` tells the frontend where the backend is running.

The SQLite location is configured but M1 does not create schemas or import data.

## Project documentation

- [Product specification](docs/product-spec.md)
- [Data format](docs/data-format.md)
- [API](docs/api.md)
- [Example dataset](examples/sample-dataset.json)

## License

MemoryScope is licensed under the MIT License. See [LICENSE](LICENSE).
