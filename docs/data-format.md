# MemoryScope Dataset Format 0.1

M1 documents the format but does not yet implement import.

## Root object

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `schema_version` | Yes | string | Must be `0.1` |
| `name` | Yes | string | Human-readable dataset name |
| `conversations` | Yes | array | One or more conversations |
| `evaluation_cases` | No | array | Queries with relevance labels |

## Conversation

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `id` | Yes | string | Unique conversation identifier |
| `messages` | Yes | array | Messages in source order |

## Message

Each message becomes exactly one retrievable memory.

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `id` | Yes | string | Unique across the whole dataset |
| `role` | Yes | string | `user`, `assistant`, `system`, or `tool` |
| `content` | Yes | string | Non-empty text |
| `timestamp` | No | string | ISO 8601 timestamp |
| `metadata` | No | object | Preserved for display; not ranked in v0.1 |

## Evaluation case

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `id` | Yes | string | Unique evaluation-case identifier |
| `query` | Yes | string | Non-empty retrieval query |
| `relevant_memory_ids` | Yes | array of strings | Every ID must reference a message in this dataset |

## Planned validation limits

- Maximum JSON size: 20 MB
- Maximum messages per dataset: 5,000
- Maximum evaluation cases: 200
- Maximum content length per message: 20,000 characters
- Duplicate IDs, empty content, unsupported roles, unknown schema versions, and dangling relevance labels are invalid

See `examples/sample-dataset.json` for a complete example.
