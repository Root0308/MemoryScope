import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { fetchDataset, searchDataset } from "../../api/datasets";
import type {
  DatasetSummary,
  SearchMethod,
  SearchResponse,
} from "../../types/datasets";

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

function methodLabel(method: SearchMethod) {
  return method === "bm25" ? "BM25" : "Dense";
}

export function SearchPage({ datasetId, onBack }: Props) {
  const [dataset, setDataset] = useState<DatasetSummary | null>(null);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [method, setMethod] = useState<SearchMethod>("bm25");
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState("10");
  const [state, setState] = useState<SearchState>({ kind: "idle" });

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
          <button className="method-card" type="button" disabled>
            <strong>Hybrid</strong><span>Later milestone</span>
          </button>
        </div>
      </section>

      {method === "dense" && (
        <aside className="dense-notice" aria-label="Dense model information">
          <strong>Local multilingual model</strong>
          <span>sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 · CPU · exact cosine</span>
          <span>Revision e8f8c211226b894fcb81acc59f3b34ba3efd5f42</span>
          <span>First use may download the model. Cached dataset embeddings are reused from SQLite.</span>
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
      {state.kind === "error" && (
        <div className="state-box state-error search-state" role="alert">
          <strong>{state.method === "dense" ? "Dense search could not complete." : "Search could not complete."}</strong>
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
          {state.response.method === "dense" && (
            <div className="model-status">
              <div><span>Model</span><strong>{state.response.model.name}</strong></div>
              <div><span>Revision</span><strong>{state.response.model.model_revision}</strong></div>
              <div><span>Configuration</span><strong>{state.response.model.dimension}d · {state.response.model.normalized ? "normalized" : "not normalized"}</strong></div>
              <div><span>Model this request</span><strong>{state.response.model.initialized_this_request ? "initialized" : "already loaded"}</strong></div>
              <div><span>Memory vectors</span><strong>{state.response.model.memory_embeddings_built ? "built" : "reused"}</strong></div>
              <div><span>Model load</span><strong>{state.response.timing.model_load_ms.toFixed(3)} ms</strong></div>
              <div><span>Memory embedding</span><strong>{state.response.timing.memory_embedding_ms.toFixed(3)} ms</strong></div>
              <div><span>Query embedding</span><strong>{state.response.timing.query_embedding_ms.toFixed(3)} ms</strong></div>
              <div><span>Cosine search</span><strong>{state.response.timing.search_ms.toFixed(3)} ms</strong></div>
            </div>
          )}
          <p className="results-context">
            Showing {state.response.results.length} of {state.response.total_memories} memories · top_k {state.response.top_k}
          </p>
          <div className="result-list">
            {state.response.results.map((result) => (
              <article className="result-card" key={result.memory_id}>
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
                <div className={`score-box score-${resultMethod}`}>
                  <span>{"bm25_raw" in result ? "BM25 raw" : "cosine similarity"}</span>
                  <strong>{formatScore("bm25_raw" in result ? result.bm25_raw : result.dense_cosine)}</strong>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
