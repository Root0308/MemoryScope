# MemoryScope API

Base URL for local development: `http://127.0.0.1:8000/api/v1`

## Implemented in M1

### `GET /health`

Reports whether the API is running and whether the local SQLite target is configured.

Example response:

```json
{
  "status": "ok",
  "service": "memoryscope-api",
  "version": "0.1.0",
  "database": {
    "engine": "sqlite",
    "status": "configured"
  }
}
```

The M1 health endpoint does not create or query database tables.

## Reserved for later milestones

Dataset import, memory listing, retrieval, comparison, and evaluation endpoints are intentionally not implemented in M1. They will be added incrementally after the foundation is accepted.
