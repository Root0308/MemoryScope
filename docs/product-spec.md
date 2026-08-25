# MemoryScope v0.1 Product Specification

## Product statement

MemoryScope is a local-first, single-user tool for inspecting and evaluating retrieval over agent conversation memory.

The v0.1 workflow is to import a strict conversation dataset, retrieve message-level memories with BM25, Dense, or Hybrid search, inspect ranking evidence and latency, compare methods, and run annotated Hit Rate, Recall, and MRR evaluation.

## Confirmed decisions

- One message is one retrievable memory; there is no automatic chunking.
- A dataset contains at most 5,000 messages.
- There is one strict JSON format.
- Dense retrieval uses `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` pinned to Hugging Face revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, with exact cosine similarity.
- BM25 will use `rank-bm25`, Unicode NFKC, English tokens, and Chinese character bigrams.
- Hybrid retrieval will use Reciprocal Rank Fusion with constant 60.
- Data remains in local SQLite and conversation content is not uploaded.
- No paid API or API key is required.
- Evaluation cases, Hit Rate, Recall, and MRR are part of v0.1.
- The project uses the MIT License.

## Implemented through M5

M2 implements:

- strict schema 0.1 parsing and validation;
- limits of 20 MB, 5,000 messages, 200 evaluation cases, and 20,000 characters per message;
- atomic SQLite import into `datasets`, `memories`, `evaluation_cases`, and `evaluation_relevances`;
- dataset list/detail, paginated memory preview, and cascading deletion APIs;
- frontend file selection/drag-and-drop, validation feedback, statistics, pagination, deletion confirmation, and UI states;
- automated coverage of valid and invalid import, rollback, pagination, and cascade behavior.

M3 implements:

- deterministic NFKC normalization;
- lowercase letter tokens and numeric tokens;
- Chinese character unigrams plus adjacent bigrams, with punctuation and whitespace as boundaries;
- one SQLite memory as one `rank-bm25` document;
- a process-local, per-dataset BM25 index cache;
- cache clearing after successful import and per-dataset invalidation after successful deletion;
- stable `memory_id` tie-breaking and `top_k` from 1 to 50;
- one BM25 search API and a dedicated Search page with raw scores, evidence, and latency.

M4 implements:

- an injectable embedding provider with fake-provider automated tests and a lazy CPU Sentence Transformer implementation;
- fixed model name and exact revision, 384-dimensional normalized float32 vectors, and embedding version metadata;
- compatible SQLite migrations through schema version 4 plus transactional BLOB persistence;
- first-query batch generation, revision/configuration/corruption detection, rebuild, in-process reuse, and post-restart SQLite reuse;
- exact cosine ranking with stable `memory_id` tie-breaking and `top_k` from 1 to 50;
- Dense response evidence, model/build flags, and model-load, embedding, and search timings;
- a BM25/Dense single-method Search UI with explicit first-download and failure states.

M5 implements:

- one Hybrid request that runs the existing BM25 and Dense branches over `min(N, max(100, 5 * top_k))` candidates each;
- candidate-union Reciprocal Rank Fusion with rank origins at 1 and fixed `rrf_k = 60`;
- zero contribution for a branch in which a candidate is absent, followed by stable `memory_id` tie-breaking;
- explainable results containing raw branch evidence, branch ranks, individual RRF contributions, and final RRF total;
- Dense model signature/build status plus BM25, Dense, fusion, and total timing evidence;
- an enabled Hybrid Search UI with local-model loading states and a per-result scoring explanation.

## Explicitly outside M5

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
