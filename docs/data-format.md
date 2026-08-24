# MemoryScope Dataset Format 0.1

M2 enforces one strict JSON object. Unknown fields and type coercion are rejected. The request body itself is JSON, not multipart form data.

## Root object

| Field | Required | Type | Constraint |
| --- | --- | --- | --- |
| `schema_version` | Yes | string | Exactly `0.1` |
| `name` | Yes | string | Non-empty after trimming; max 200 characters |
| `conversations` | Yes | array | At least one conversation |
| `evaluation_cases` | No | array | Defaults to empty; at most 200 |

## Conversation

| Field | Required | Type | Constraint |
| --- | --- | --- | --- |
| `id` | Yes | string | Non-empty, unique in the dataset, max 200 characters |
| `messages` | Yes | array | At least one message |

## Message / memory

Every message is stored as exactly one memory in source order. There is no automatic chunking or embedding in M2.

| Field | Required | Type | Constraint |
| --- | --- | --- | --- |
| `id` | Yes | string | Unique across every message in the dataset; max 200 characters |
| `role` | Yes | string | `user`, `assistant`, `system`, or `tool` |
| `content` | Yes | string | Non-blank; at most 20,000 characters |
| `timestamp` | No | string or null | Valid ISO 8601 datetime |
| `metadata` | No | object or null | Keys are strings; values must be valid JSON values |

## Evaluation case

| Field | Required | Type | Constraint |
| --- | --- | --- | --- |
| `id` | Yes | string | Unique among evaluation cases; max 200 characters |
| `query` | Yes | string | Non-blank; at most 20,000 characters |
| `relevant_memory_ids` | Yes | string array | Non-empty, unique IDs; every ID must reference a message in the same dataset |

`evaluation_cases` may be omitted when no relevance annotations exist.

## Import limits and rejection

- JSON request: at most 20 MB
- Messages: at most 5,000 total across all conversations
- Evaluation cases: at most 200
- Message content: at most 20,000 characters
- Invalid JSON, an unsupported version, extra fields, wrong types, blank content, invalid roles, duplicates, and dangling relevance IDs are rejected
- A rejected or failed import leaves no dataset, memory, case, or relevance rows behind

See [`examples/sample-dataset.json`](../examples/sample-dataset.json) for a complete accepted file.
