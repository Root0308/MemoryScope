# MemoryScope

MemoryScope is a new, independent, local-first tool for inspecting and evaluating agent memory retrieval. M7 supports single BM25, local multilingual Dense, explainable Hybrid RRF, one-query three-method comparison, and labelled Recall@k/MRR@k evaluation over imported message-level memories.

Implemented through M7:

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
- Evaluation API over imported `evaluation_cases`, with macro Recall@k, macro MRR@k, average latency, and standard-median P50 latency
- Three-method evaluation cards, quality/latency charts, and per-case evidence with no-hit and no-label states
- pytest coverage using an injectable fake provider; the test suite never downloads the real model

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

The timing chart contains only `bm25_ms`, `dense_ms`, and `hybrid_fusion_ms`; shared preparation is displayed separately and is not repeated across methods. Compare remains exploratory rank inspection. The Evaluation mode described below uses imported human relevance labels.

## Evaluate the example

Open the dataset workspace and choose **Evaluation**. The sample contains two deliberately small, human-readable cases. Choose `k` from 1 to 50 and run all three methods locally.

PowerShell API example:

```powershell
$evaluationBody = @{
  k = 3
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/v1/datasets/<dataset-id>/evaluate `
  -Method Post `
  -ContentType application/json `
  -Body $evaluationBody
```

For one case with relevant set `R` and returned top-k IDs `T`, MemoryScope calculates:

- `Recall@k = |R ∩ T| / |R|`.
- `RR@k = 1 / r` when the first relevant result is at one-based rank `r <= k`; otherwise `0`.
- Dataset Recall@k and MRR@k are macro averages: each case contributes equal weight.
- `average_latency_ms` is the arithmetic mean of the per-case method stage.
- `p50_latency_ms` is the standard median; for an even sample count it averages the two middle values.

Each eval query computes BM25 and Dense rankings once and reuses them for Hybrid. Dense encodes one query vector per case. Method latency semantics match Compare: BM25 is lexical scoring/ranking, Dense is query encoding plus cosine ranking, and Hybrid is RRF fusion only. Model initialization, vector inspection/build, and other shared preparation appear once in `preparation_ms` rather than being attributed to every method.

Metrics depend entirely on manually supplied `relevant_memory_ids`. They are not automatic truth labels, a statistical significance test, or evidence that a method generalizes beyond the imported local dataset. Evaluation runs are not stored as history.

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
