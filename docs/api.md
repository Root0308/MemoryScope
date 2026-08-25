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

M4 accepts exactly one method per request: BM25 or Dense. Multi-method comparison is not implemented yet.

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

Requests containing `hybrid` return `422` with `code: method_not_supported`; requests containing both BM25 and Dense return `422` with `code: invalid_methods`. No substitute or fabricated scores are returned.

## Not implemented in M4

Hybrid/RRF, multi-method comparison, charts, and evaluation execution endpoints do not exist yet.
