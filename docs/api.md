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

Deletes the dataset and all related memories, evaluation cases, and relevance rows in SQLite. Returns `204 No Content` or `404`.

## Not implemented in M2

Retrieval, scores, BM25, Dense, Hybrid, visual comparison, and evaluation execution endpoints do not exist yet.
