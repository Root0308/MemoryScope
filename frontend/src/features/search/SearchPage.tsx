import { lazy, Suspense, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { fetchDataset, searchDataset } from "../../api/datasets";
import type {
  DenseSearchResponse,
  DatasetSummary,
  HybridSearchResponse,
  HybridSearchResult,
  SearchMethod,
  SearchResponse,
} from "../../types/datasets";

const ComparePanel = lazy(() =>
  import("./ComparePanel").then((module) => ({ default: module.ComparePanel })),
);

type Props = {
  datasetId: string;
  onBack: () => void;
};

type SearchState =
  | { kind: "idle" }
  | { kind: "loading"; method: SearchMethod }
  | { kind: "success"; response: SearchResponse }
  | { kind: "error"; method: SearchMethod; message: string };

function formatScore(score: number) {
  return score.toFixed(6);
}

function formatOptionalScore(score: number | null) {
  return score === null ? "—" : formatScore(score);
}

function formatOptionalRank(rank: number | null) {
  return rank === null ? "not in pool" : `rank #${rank}`;
}

function methodLabel(method: SearchMethod) {
  if (method === "bm25") return "BM25";
  if (method === "dense") return "Dense";
  return "Hybrid";
}

function ModelStatus({ response }: { response: DenseSearchResponse | HybridSearchResponse }) {
  const timing = response.method === "dense" ? response.timing : response.timing.dense;
  return (
    <div className="model-status">
      <div><span>Model</span><strong>{response.model.name}</strong></div>
      <div><span>Revision</span><strong>{response.model.model_revision}</strong></div>
      <div><span>Embedding version</span><strong>{response.model.embedding_version}</strong></div>
      <div><span>Configuration</span><strong>{response.model.dimension}d · {response.model.normalized ? "normalized" : "not normalized"}</strong></div>
      <div><span>Model this request</span><strong>{response.model.initialized_this_request ? "initialized" : "already loaded"}</strong></div>
      <div><span>Memory vectors</span><strong>{response.model.memory_embeddings_built ? "built" : "reused"}</strong></div>
      <div><span>Model load</span><strong>{timing.model_load_ms.toFixed(3)} ms</strong></div>
      <div><span>Memory embedding</span><strong>{timing.memory_embedding_ms.toFixed(3)} ms</strong></div>
      <div><span>Query embedding</span><strong>{timing.query_embedding_ms.toFixed(3)} ms</strong></div>
      <div><span>Cosine search</span><strong>{timing.search_ms.toFixed(3)} ms</strong></div>
      {response.method === "hybrid" && (
        <>
          <div><span>BM25 branch</span><strong>{response.timing.bm25.total_ms.toFixed(3)} ms</strong></div>
          <div><span>Dense branch</span><strong>{response.timing.dense.total_ms.toFixed(3)} ms</strong></div>
          <div><span>RRF fusion</span><strong>{response.timing.fusion_ms.toFixed(3)} ms</strong></div>
        </>
      )}
    </div>
  );
}

function HybridScoreExplanation({ result }: { result: HybridSearchResult }) {
  return (
    <div className="hybrid-explanation" aria-label={`Scoring explanation for ${result.memory_id}`}>
      <div>
        <span>BM25 raw</span>
        <strong>{formatOptionalScore(result.bm25_raw_score)}</strong>
        <small>{formatOptionalRank(result.bm25_rank)}</small>
      </div>
      <div>
        <span>Dense cosine</span>
        <strong>{formatOptionalScore(result.dense_cosine)}</strong>
        <small>{formatOptionalRank(result.dense_rank)}</small>
      </div>
      <div>
        <span>RRF from BM25</span>
        <strong>{formatScore(result.rrf_bm25)}</strong>
        <small>{result.bm25_rank === null ? "0 contribution" : `1 / (60 + ${result.bm25_rank})`}</small>
      </div>
      <div>
        <span>RRF from Dense</span>
        <strong>{formatScore(result.rrf_dense)}</strong>
        <small>{result.dense_rank === null ? "0 contribution" : `1 / (60 + ${result.dense_rank})`}</small>
      </div>
      <div className="rrf-total-detail">
        <span>RRF total</span>
        <strong>{formatScore(result.rrf_total)}</strong>
        <small>rank contributions only</small>
      </div>
    </div>
  );
}

export function SearchPage({ datasetId, onBack }: Props) {
  const [dataset, setDataset] = useState<DatasetSummary | null>(null);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [method, setMethod] = useState<SearchMethod>("bm25");
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState("10");
  const [state, setState] = useState<SearchState>({ kind: "idle" });
  const [viewMode, setViewMode] = useState<"single" | "compare">("single");

  useEffect(() => {
    const controller = new AbortController();
    setDataset(null);
    setDatasetError(null);
    void fetchDataset(datasetId, controller.signal)
      .then(setDataset)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setDatasetError(error instanceof Error ? error.message : "Could not load dataset.");
      });
    return () => controller.abort();
  }, [datasetId]);

  function chooseMethod(nextMethod: SearchMethod) {
    setMethod(nextMethod);
    setState({ kind: "idle" });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedTopK = Number(topK);
    if (!Number.isInteger(parsedTopK) || parsedTopK < 1 || parsedTopK > 50) {
      setState({ kind: "error", method, message: "top_k must be an integer from 1 to 50." });
      return;
    }
    if (!query.trim()) {
      setState({ kind: "error", method, message: "Enter a query before searching." });
      return;
    }

    setState({ kind: "loading", method });
    try {
      const response = await searchDataset(datasetId, query, method, parsedTopK);
      setState({ kind: "success", response });
    } catch (error) {
      setState({
        kind: "error",
        method,
        message: error instanceof Error ? error.message : "Search failed.",
      });
    }
  }

  const resultMethod = state.kind === "success" ? state.response.method : method;

  return (
    <div className="search-page">
      <button className="back-button" type="button" onClick={onBack}>← Back to datasets</button>

      <div className="search-mode-switch" role="group" aria-label="Search page mode">
        <button
          type="button"
          className={viewMode === "single" ? "mode-active" : ""}
          aria-pressed={viewMode === "single"}
          onClick={() => setViewMode("single")}
        >
          Single Search
        </button>
        <button
          type="button"
          className={viewMode === "compare" ? "mode-active" : ""}
          aria-pressed={viewMode === "compare"}
          onClick={() => setViewMode("compare")}
        >
          Compare Methods
        </button>
      </div>

      {viewMode === "compare" ? (
        <Suspense fallback={<div className="state-box search-state" role="status">Loading comparison workspace…</div>}>
          <ComparePanel dataset={dataset} datasetError={datasetError} datasetId={datasetId} />
        </Suspense>
      ) : (
        <>

      <section className="panel search-hero" aria-labelledby="search-title">
        <div>
          <p className="section-label">{methodLabel(method).toUpperCase()} SEARCH</p>
          <h2 id="search-title">{dataset?.name ?? "Dataset search"}</h2>
          {dataset && <p className="search-subtitle">{dataset.memory_count} message-level memories · no automatic chunking</p>}
          {datasetError && <div className="feedback feedback-error" role="alert">{datasetError}</div>}
        </div>
        <div className="method-grid" aria-label="Retrieval methods">
          <button
            className={`method-card ${method === "bm25" ? "method-active" : ""}`}
            type="button"
            aria-pressed={method === "bm25"}
            disabled={state.kind === "loading"}
            onClick={() => chooseMethod("bm25")}
          >
            <strong>BM25</strong><span>Lexical · available</span>
          </button>
          <button
            className={`method-card ${method === "dense" ? "method-active" : ""}`}
            type="button"
            aria-pressed={method === "dense"}
            disabled={state.kind === "loading"}
            onClick={() => chooseMethod("dense")}
          >
            <strong>Dense</strong><span>Local cosine · available</span>
          </button>
          <button
            className={`method-card ${method === "hybrid" ? "method-active" : ""}`}
            type="button"
            aria-pressed={method === "hybrid"}
            disabled={state.kind === "loading"}
            onClick={() => chooseMethod("hybrid")}
          >
            <strong>Hybrid</strong><span>BM25 + Dense RRF · available</span>
          </button>
        </div>
      </section>

      {(method === "dense" || method === "hybrid") && (
        <aside className="dense-notice" aria-label="Dense model information">
          <strong>Local multilingual model</strong>
          <span>sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 · CPU · exact cosine</span>
          <span>Revision e8f8c211226b894fcb81acc59f3b34ba3efd5f42</span>
          <span>First use may download the model. Cached dataset embeddings are reused from SQLite.</span>
        </aside>
      )}
      {method === "hybrid" && (
        <aside className="hybrid-notice" aria-label="Hybrid scoring information">
          <strong>Rank fusion, not raw-score addition</strong>
          <span>BM25 raw scores and cosine similarities use different scales and cannot be compared directly.</span>
          <span>Each branch retrieves a fixed candidate pool; final ordering uses only 1 / (60 + branch rank).</span>
        </aside>
      )}

      <section className="panel search-form-panel" aria-label={`${methodLabel(method)} query`}>
        <form onSubmit={(event) => void handleSubmit(event)}>
          <label htmlFor="search-query">Query</label>
          <textarea
            id="search-query" rows={3} value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={method === "dense" ? "What interface theme does the user prefer?" : "用户喜欢什么界面主题？"}
            disabled={!dataset || state.kind === "loading"}
          />
          <div className="search-controls">
            <label htmlFor="top-k">top_k
              <input
                id="top-k" type="number" min="1" max="50" step="1"
                value={topK} onChange={(event) => setTopK(event.target.value)}
                disabled={!dataset || state.kind === "loading"}
              />
            </label>
            <button type="submit" disabled={!dataset || state.kind === "loading"}>
              {state.kind === "loading" ? "Searching…" : `Search with ${methodLabel(method)}`}
            </button>
          </div>
        </form>
      </section>

      {state.kind === "idle" && (
        <div className="state-box search-state">
          Enter a query to rank this dataset with {methodLabel(method)}.
        </div>
      )}
      {state.kind === "loading" && state.method === "bm25" && (
        <div className="state-box search-state" role="status">Searching indexed memories…</div>
      )}
      {state.kind === "loading" && state.method === "dense" && (
        <div className="state-box dense-progress search-state" role="status">
          <strong>Preparing local Dense search…</strong>
          <span>Initializing the Sentence Transformer; first use may download it.</span>
          <span>Checking SQLite and generating any missing dataset vectors.</span>
          <span>Computing the query vector and exact cosine ranking.</span>
        </div>
      )}
      {state.kind === "loading" && state.method === "hybrid" && (
        <div className="state-box dense-progress search-state" role="status">
          <strong>Preparing Hybrid search…</strong>
          <span>Running the cached BM25 branch over the fixed candidate pool.</span>
          <span>Initializing the local Dense model and checking SQLite vectors.</span>
          <span>Fusing branch ranks with deterministic RRF (k = 60).</span>
        </div>
      )}
      {state.kind === "error" && (
        <div className="state-box state-error search-state" role="alert">
          <strong>{state.method === "bm25" ? "Search could not complete." : `${methodLabel(state.method)} search could not complete.`}</strong>
          <p>{state.message}</p>
        </div>
      )}
      {state.kind === "success" && state.response.results.length === 0 && (
        <div className="state-box search-state">No results for this query.</div>
      )}
      {state.kind === "success" && state.response.results.length > 0 && (
        <section className="search-results" aria-labelledby="results-title">
          <div className="results-heading">
            <div><p className="section-label">RESULTS</p><h2 id="results-title">{methodLabel(resultMethod)} ranking</h2></div>
            <div className="timing-summary">
              <strong>{state.response.timing.total_ms.toFixed(3)} ms</strong>
              <span>
                {state.response.method === "bm25"
                  ? (state.response.timing.cache_hit ? "cached index" : "index built")
                  : (state.response.model.memory_embeddings_built ? "dataset vectors built" : "SQLite vectors reused")}
              </span>
            </div>
          </div>
          {state.response.method !== "bm25" && <ModelStatus response={state.response} />}
          {state.response.method === "hybrid" && (
            <div className="hybrid-scale-note">
              <strong>How this ranking works</strong>
              <span>BM25 raw and Dense cosine values are shown for diagnosis only. They are not added or normalized together.</span>
              <span>Final rank comes from RRF contributions computed from each branch rank with k = {state.response.rrf_k}.</span>
            </div>
          )}
          <p className="results-context">
            Showing {state.response.results.length} of {state.response.total_memories} memories · top_k {state.response.top_k}
            {state.response.method === "hybrid" && (
              <> · {state.response.candidate_pool_size} candidates per branch · rrf_k {state.response.rrf_k}</>
            )}
          </p>
          <div className="result-list">
            {state.response.results.map((result) => (
              <article className={`result-card ${"rrf_total" in result ? "result-card-hybrid" : ""}`} key={result.memory_id}>
                <div className="rank-badge" aria-label={`Rank ${result.final_rank}`}>{result.final_rank}</div>
                <div className="result-body">
                  <div className="result-meta">
                    <span className={`role role-${result.role}`}>{result.role}</span>
                    <code>{result.memory_id}</code>
                    <span>conversation {result.conversation_id}</span>
                    {result.timestamp && <time>{new Date(result.timestamp).toLocaleString()}</time>}
                  </div>
                  <p>{result.content}</p>
                </div>
                {"rrf_total" in result ? (
                  <>
                    <div className="score-box score-hybrid">
                      <span>RRF total</span>
                      <strong>{formatScore(result.rrf_total)}</strong>
                    </div>
                    <HybridScoreExplanation result={result} />
                  </>
                ) : (
                  <div className={`score-box score-${resultMethod}`}>
                    <span>{"bm25_raw" in result ? "BM25 raw" : "cosine similarity"}</span>
                    <strong>{formatScore("bm25_raw" in result ? result.bm25_raw : result.dense_cosine)}</strong>
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
        </>
      )}
    </div>
  );
}
