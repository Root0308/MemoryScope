# MemoryScope

MemoryScope is a new, independent, local-first tool for inspecting and evaluating agent memory retrieval. M6 supports single BM25, local multilingual Dense, explainable Hybrid RRF, and one-query three-method rank comparison over imported message-level memories.

Implemented through M6:

- React, TypeScript, and Vite frontend
- FastAPI backend and health endpoint
- Strict MemoryScope schema 0.1 validation
- SQLite tables for datasets, memories, evaluation cases, and relevance labels
- Atomic import, dataset list/detail, paginated memories, and cascading deletion
- `rank-bm25` retrieval with per-dataset process-local index caching
- Unicode NFKC, lowercased word/number tokens, and Chinese unigram/bigram tokenization
- Stable score ties ordered by memory ID, `top_k` from 1 to 50, result evidence, and timing
- Local CPU embeddings with `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, pinned to Hugging Face revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`
- float32 embedding BLOBs in SQLite with model/configuration metadata and compatible schema migration
- Exact cosine similarity, stable ties, transactional vector builds, corruption detection, and persisted reuse
- Hybrid retrieval over the BM25/Dense candidate union with deterministic Reciprocal Rank Fusion (`rrf_k = 60`)
- Per-result branch ranks, raw diagnostic scores, RRF contributions, candidate-pool size, and stage timings
- Compare API that executes BM25 and Dense once, reuses their candidate ranks for Hybrid, and encodes the Dense query once
- Responsive three-column results, accessible rank matrix, and Recharts timing visualization with shared preparation shown separately
- pytest coverage using an injectable fake provider; the test suite never downloads the real model

Recall, MRR, evaluation-case execution, and aggregate evaluation reports are intentionally not implemented yet; those belong to M7.

## Requirements

- Git
- Node.js 20.19+ in the 20.x line, or Node.js 22.12+
- npm 10+
- Python 3.11+

No paid API, API key, or external database is required. Installing the backend includes the local Sentence Transformer runtime. The first Dense or Hybrid query downloads the fixed public model unless it is already cached.

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

## Search the example

In the frontend, choose **Search** on a dataset. **Single Search** preserves the BM25, Dense, and Hybrid workflows. **Compare Methods** accepts one query and `top_k`, then shows three result columns, a memory-aligned rank matrix, and method-specific timing bars. BM25 raw and Dense cosine values remain visible only in their own result columns; the comparison is based on ranks, not a shared score scale.

PowerShell API example, replacing `<dataset-id>` with the imported dataset ID:

```powershell
$searchBody = @{
  query = "用户喜欢什么界面主题？"
  methods = @("bm25")
  top_k = 10
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/v1/datasets/<dataset-id>/search `
  -Method Post `
  -ContentType application/json `
  -Body $searchBody
```

BM25 indexes are built from SQLite memories on first search and reused in the backend process. Successful dataset import clears cached indexes; successful deletion invalidates that dataset's index.

Dense API example:

```powershell
$denseBody = @{
  query = "What interface theme does the user prefer?"
  methods = @("dense")
  top_k = 10
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/v1/datasets/<dataset-id>/search `
  -Method Post `
  -ContentType application/json `
  -Body $denseBody
```

On the first Dense request, MemoryScope loads or downloads the model, creates missing memory embeddings in a single SQLite transaction, and performs exact cosine search. Later requests reuse matching BLOBs. Restarting the backend reloads the model into memory but still reuses SQLite embeddings.

The model name alone is not used as an embedding identity. MemoryScope passes the exact revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` to Sentence Transformer and persists it with every embedding. A missing or different revision forces a transactional dataset rebuild.

Hybrid API example:

```powershell
$hybridBody = @{
  query = "用户喜欢什么界面主题？"
  methods = @("hybrid")
  top_k = 10
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/v1/datasets/<dataset-id>/search `
  -Method Post `
  -ContentType application/json `
  -Body $hybridBody
```

For each branch, Hybrid retrieves `min(dataset_memory_count, max(100, 5 * top_k))` candidates. It takes the candidate union and computes `1 / (60 + rank)` for each available branch; a missing branch contributes zero. The final score is the sum of those rank contributions, with `memory_id` as the stable tie-break. BM25 raw scores and Dense cosine similarities have different scales: they are never directly added or normalized together.

Compare API example:

```powershell
$compareBody = @{
  query = "用户喜欢什么界面主题？"
  top_k = 10
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/v1/datasets/<dataset-id>/search/compare `
  -Method Post `
  -ContentType application/json `
  -Body $compareBody
```

A Compare request calculates the BM25 and Dense candidate rankings once and reuses them for Hybrid. The Dense query vector is encoded once. `comparison_rows` aligns the top-k result union by `memory_id`; a method rank is `null` when that memory is outside that method's top-k.

Compare timing fields deliberately separate shared and method-specific work:

- `preparation_ms`: BM25 index access/build plus Dense dataset loading, model initialization, and memory-vector inspection/build.
- `bm25_ms`: BM25 query scoring and stable ranking only.
- `dense_ms`: one query embedding plus exact cosine scoring and stable ranking.
- `hybrid_fusion_ms`: RRF fusion of the already-computed candidate ranks.
- `total_ms`: full request wall-clock time, including response alignment/assembly.

The timing chart contains only `bm25_ms`, `dense_ms`, and `hybrid_fusion_ms`; shared preparation is displayed separately and is not repeated across methods. Compare is an exploratory rank-inspection tool, not formal evaluation. Recall and MRR arrive in M7.

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
- `MEMORYSCOPE_MODEL_CACHE_PATH` selects the model cache; default: `backend/.model-cache`.
- `MEMORYSCOPE_MODEL_OFFLINE=true` prevents downloads and requires a complete cached model.
- `VITE_API_BASE_URL` tells the frontend where the backend is running.

The fixed model cache is approximately 500 MB (exact size varies by package/model revision). Python ML dependencies consume additional virtual-environment disk space. With a complete cache, Dense and Hybrid work offline; without it, offline Dense/Hybrid return a clear model initialization error while BM25 remains available.

On Windows without Developer Mode, Hugging Face may warn that cache symlinks are unavailable. MemoryScope still works and stores ordinary files in the configured cache, but downloading can temporarily use more disk space.

SQLite databases, environment overrides, dependencies, build outputs, Python caches, and downloaded model files are excluded from Git.

## Documentation

- [Product specification](docs/product-spec.md)
- [Data format](docs/data-format.md)
- [API](docs/api.md)
- [Example dataset](examples/sample-dataset.json)

## License

MemoryScope is licensed under the [MIT License](LICENSE).
