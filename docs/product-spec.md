# MemoryScope v0.1 Product Specification

## Product statement

MemoryScope is a local-first, single-user tool for inspecting and evaluating retrieval over agent conversation memory.

The v0.1 workflow is to import a strict conversation dataset, retrieve message-level memories with BM25, Dense, or Hybrid search, inspect ranking evidence and latency, compare methods, and run annotated Hit Rate, Recall, and MRR evaluation.

## Confirmed decisions

- One message is one retrievable memory; there is no automatic chunking.
- A dataset contains at most 5,000 messages.
- There is one strict JSON format.
- Dense retrieval will use `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` with exact cosine similarity.
- BM25 will use `rank-bm25`, Unicode NFKC, English tokens, and Chinese character bigrams.
- Hybrid retrieval will use Reciprocal Rank Fusion with constant 60.
- Data remains in local SQLite and conversation content is not uploaded.
- No paid API or API key is required.
- Evaluation cases, Hit Rate, Recall, and MRR are part of v0.1.
- The project uses the MIT License.

## Implemented through M2

M2 implements:

- strict schema 0.1 parsing and validation;
- limits of 20 MB, 5,000 messages, 200 evaluation cases, and 20,000 characters per message;
- atomic SQLite import into `datasets`, `memories`, `evaluation_cases`, and `evaluation_relevances`;
- dataset list/detail, paginated memory preview, and cascading deletion APIs;
- frontend file selection/drag-and-drop, validation feedback, statistics, pagination, deletion confirmation, and UI states;
- automated coverage of valid and invalid import, rollback, pagination, and cascade behavior.

No embedding is generated through M3.

## M3 acceptance scope

M3 implements:

- deterministic NFKC normalization;
- lowercase letter tokens and numeric tokens;
- Chinese character unigrams plus adjacent bigrams, with punctuation and whitespace as boundaries;
- one SQLite memory as one `rank-bm25` document;
- a process-local, per-dataset BM25 index cache;
- cache clearing after successful import and per-dataset invalidation after successful deletion;
- stable `memory_id` tie-breaking and `top_k` from 1 to 50;
- one BM25 search API and a dedicated Search page with raw scores, evidence, and latency;
- explicit rejection of Dense and Hybrid rather than placeholder results.

## Explicitly outside M3

- Sentence Transformer loading and embeddings
- Dense and Hybrid/RRF retrieval
- Three-method comparison and charts
- Evaluation execution and metric calculation

## v0.1 non-goals

- Authentication or multiple users
- Cloud synchronization or conversation upload
- Paid APIs or LLM answer generation
- ANN, vector databases, or distributed search
- Automatic chunking, reranking, background queues, or live agent integrations
- Model selection and tuning interfaces

## Independent implementation

MemoryScope started from an empty repository. It does not copy code, structure, data, figures, benchmarks, charts, or prose from the earlier group project.
