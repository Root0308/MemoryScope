# MemoryScope v0.1 Product Specification

## Product statement

MemoryScope is a local-first, single-user tool for inspecting and evaluating retrieval over agent conversation memory.

The core workflow is:

1. Import one strictly validated conversation JSON dataset.
2. Search message-level memories with BM25, Dense, or Hybrid retrieval.
3. Inspect rankings, score components, and retrieval latency.
4. Compare retrieval methods.
5. Evaluate annotated queries with Hit Rate, Recall, and MRR.

## Confirmed v0.1 decisions

- One message is one retrievable memory; there is no automatic chunking.
- A dataset contains at most 5,000 messages.
- There is one strict JSON format.
- Dense retrieval uses `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Dense search uses exact cosine similarity, not ANN.
- BM25 uses `rank-bm25`.
- Text normalization uses Unicode NFKC, English tokens, and Chinese character bigrams.
- Hybrid retrieval uses Reciprocal Rank Fusion with a rank constant of 60.
- Data is stored in local SQLite and conversation content is not uploaded.
- No paid API or API key is required.
- Evaluation cases, Hit Rate, Recall, and MRR are part of v0.1.
- The project is licensed under MIT.

## M1 scope

M1 provides only the runnable frontend and backend foundation, health reporting, SQLite configuration, tests, and documentation.

## Explicitly outside M1

- JSON import and validation runtime
- Database schema creation
- BM25 retrieval
- Sentence Transformer loading and embeddings
- Dense or Hybrid retrieval
- Retrieval visualization
- Evaluation execution

## v0.1 non-goals

- Authentication or multiple users
- Cloud synchronization
- Paid APIs or LLM answer generation
- HNSW, vector databases, or distributed search
- Automatic chunking
- Reranking
- Live agent integrations
- Model selection and tuning interfaces
- Background job queues

## Independent implementation

MemoryScope starts from an empty repository. It does not copy code, project structure, data, figures, benchmarks, or prose from the earlier group project.
