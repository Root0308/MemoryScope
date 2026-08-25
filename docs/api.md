# MemoryScope API

Local base URL: `http://127.0.0.1:8000/api/v1`

## Health

### `GET /health`

Returns `200 OK` with service version and SQLite status.

```json
{
  "status": "ok",
  "service": "memoryscope-api",
  "version": "0.1.0",
  "database": { "engine": "sqlite", "status": "configured" }
}
```

## Datasets

### `POST /datasets/import`

Send a schema 0.1 JSON document as the request body with `Content-Type: application/json`. Maximum body size is 20 MB. Returns `201 Created` and the imported dataset summary.

Validation errors return `422`; invalid JSON returns `400`; oversized requests return `413`. Validation responses contain a stable error `code`, a `message`, and Pydantic issue details where available. Storage failure returns `500` after rollback.

### `GET /datasets`

Returns dataset summaries in reverse import order:

```json
{
  "items": [
    {
      "id": "uuid",
      "schema_version": "0.1",
      "name": "memoryscope-sample",
      "imported_at": "2026-08-24T00:00:00Z",
      "conversation_count": 2,
      "memory_count": 4,
      "evaluation_case_count": 2
    }
  ],
  "total": 1
}
```

### `GET /datasets/{id}`

Returns one dataset summary or `404`.

### `GET /datasets/{id}/memories?page=1&page_size=20`

Returns memories in source order. `page` starts at 1; `page_size` is 1–100.

```json
{
  "items": [
    {
      "id": "mem-001",
      "conversation_id": "conv-001",
      "position": 0,
      "role": "user",
      "content": "我更喜欢深色主题。",
      "timestamp": "2026-08-20T10:00:00Z",
      "metadata": { "source": "sample" }
    }
  ],
  "total": 4,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

### `DELETE /datasets/{id}`

Deletes the dataset and all related memories, embeddings, evaluation cases, and relevance rows in SQLite. Returns `204 No Content` or `404`.

### `POST /datasets/{id}/search`

M5 accepts exactly one method per request: BM25, Dense, or Hybrid. A request such as `methods: ["bm25", "dense"]` is a later comparison workflow and returns `422` with `code: invalid_methods`.

BM25 request:

```json
{
  "query": "用户喜欢什么界面主题？",
  "methods": ["bm25"],
  "top_k": 10
}
```

`top_k` must be an integer from 1 to 50. Empty, whitespace-only, and punctuation-only queries return `422`. A missing dataset returns `404`.

Example response:

```json
{
  "query": "用户喜欢什么界面主题？",
  "method": "bm25",
  "top_k": 10,
  "total_memories": 4,
  "timing": {
    "total_ms": 0.186,
    "index_ms": 0.003,
    "search_ms": 0.183,
    "cache_hit": true
  },
  "results": [
    {
      "final_rank": 1,
      "memory_id": "mem-001",
      "conversation_id": "conv-001",
      "role": "user",
      "content": "我更喜欢深色主题。",
      "timestamp": "2026-08-20T18:00:00+08:00",
      "metadata": { "source": "sample" },
      "bm25_raw": 4.6173414449274865,
      "bm25_rank": 1
    }
  ]
}
```

Timing is measured in milliseconds and varies by machine. Equal BM25 scores are ordered by `memory_id`. The first request may build the process-local index; later requests can report `cache_hit: true`.

Dense request:

```json
{
  "query": "What interface theme does the user prefer?",
  "methods": ["dense"],
  "top_k": 10
}
```

Dense response shape:

```json
{
  "query": "What interface theme does the user prefer?",
  "method": "dense",
  "top_k": 10,
  "total_memories": 4,
  "model": {
    "name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "model_revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
    "dimension": 384,
    "normalized": true,
    "embedding_version": "memoryscope-dense-v1",
    "initialized_this_request": true,
    "memory_embeddings_built": true
  },
  "timing": {
    "total_ms": 842.317,
    "model_load_ms": 610.221,
    "memory_embedding_ms": 205.472,
    "query_embedding_ms": 25.913,
    "search_ms": 0.128
  },
  "results": [
    {
      "final_rank": 1,
      "memory_id": "mem-001",
      "conversation_id": "conv-001",
      "role": "user",
      "content": "我更喜欢深色主题。",
      "timestamp": "2026-08-20T18:00:00+08:00",
      "metadata": { "source": "sample" },
      "dense_cosine": 0.731245,
      "dense_rank": 1
    }
  ]
}
```

Dense timing is separated into model loading, memory embedding inspection/build, query embedding, and exact cosine search. `initialized_this_request` reports process-local model initialization. `memory_embeddings_built` reports whether any memory vectors were generated or rebuilt; `false` means compatible SQLite BLOBs were reused.

The first Dense request may download the fixed model revision, then creates missing vectors transactionally. The exact revision is passed to Sentence Transformer and returned as `model.model_revision`. A missing/different revision, any other model/configuration mismatch, or invalid stored vector causes a full dataset rebuild. Model load failure returns `503` with `code: model_initialization_failed`; embedding generation or transactional persistence failures return `500` with explicit codes and no fabricated results.

Hybrid request:

```json
{
  "query": "用户喜欢什么界面主题？",
  "methods": ["hybrid"],
  "top_k": 10
}
```

Hybrid response shape:

```json
{
  "query": "用户喜欢什么界面主题？",
  "method": "hybrid",
  "top_k": 10,
  "total_memories": 4,
  "candidate_pool_size": 4,
  "rrf_k": 60,
  "model": {
    "name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "model_revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
    "dimension": 384,
    "normalized": true,
    "embedding_version": "memoryscope-dense-v1",
    "initialized_this_request": false,
    "memory_embeddings_built": false
  },
  "timing": {
    "total_ms": 29.412,
    "fusion_ms": 0.093,
    "bm25": {
      "total_ms": 0.251,
      "index_ms": 0.003,
      "search_ms": 0.248,
      "cache_hit": true
    },
    "dense": {
      "total_ms": 28.972,
      "model_load_ms": 0.006,
      "memory_embedding_ms": 0.241,
      "query_embedding_ms": 28.541,
      "search_ms": 0.184
    }
  },
  "results": [
    {
      "final_rank": 1,
      "memory_id": "mem-001",
      "conversation_id": "conv-001",
      "role": "user",
      "content": "我更喜欢深色主题。",
      "timestamp": "2026-08-20T18:00:00+08:00",
      "metadata": { "source": "sample" },
      "bm25_raw_score": 4.6173414449274865,
      "bm25_rank": 1,
      "dense_cosine": 0.731245,
      "dense_rank": 2,
      "rrf_bm25": 0.01639344262295082,
      "rrf_dense": 0.016129032258064516,
      "rrf_total": 0.03252247488101534
    }
  ]
}
```

Each branch receives `min(total_memories, max(100, 5 * top_k))` candidates. MemoryScope takes the candidate union, assigns one-based branch ranks, and calculates:

- `rrf_bm25 = 1 / (60 + bm25_rank)`
- `rrf_dense = 1 / (60 + dense_rank)`
- `rrf_total = rrf_bm25 + rrf_dense`

If a result is absent from one branch candidate pool, that branch's rank and raw score are `null` and its RRF contribution is `0`. BM25 raw scores and cosine similarities are not directly comparable and are never added or normalized together. Equal branch scores and equal `rrf_total` values are resolved by ascending `memory_id`.

The Hybrid `model` object is the Dense embedding identity/signature and lifecycle state. Its name, exact revision, dimension, normalized flag, and embedding version must all match persisted vectors; otherwise the M4 transactional rebuild behavior applies. The nested timing object separates BM25, Dense, and RRF fusion work.

Unknown methods return `422` with `code: method_not_supported`. No substitute or fabricated scores are returned.

## Not implemented in M5

Multi-method comparison, charts, and evaluation execution endpoints do not exist yet.
