import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { fetchDataset, searchDatasetBM25 } from "../../api/datasets";
import type { BM25SearchResponse, DatasetSummary } from "../../types/datasets";

type Props = {
  datasetId: string;
  onBack: () => void;
};

type SearchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; response: BM25SearchResponse }
  | { kind: "error"; message: string };

function formatScore(score: number) {
  return score.toFixed(6);
}

export function SearchPage({ datasetId, onBack }: Props) {
  const [dataset, setDataset] = useState<DatasetSummary | null>(null);
  const [datasetError, setDatasetError] = useState<string | null>(null);
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedTopK = Number(topK);
    if (!Number.isInteger(parsedTopK) || parsedTopK < 1 || parsedTopK > 50) {
      setState({ kind: "error", message: "top_k must be an integer from 1 to 50." });
      return;
    }
    if (!query.trim()) {
      setState({ kind: "error", message: "Enter a query before searching." });
      return;
    }

    setState({ kind: "loading" });
    try {
      const response = await searchDatasetBM25(datasetId, query, parsedTopK);
      setState({ kind: "success", response });
    } catch (error) {
      setState({ kind: "error", message: error instanceof Error ? error.message : "Search failed." });
    }
  }

  return (
    <div className="search-page">
      <button className="back-button" type="button" onClick={onBack}>← Back to datasets</button>

      <section className="panel search-hero" aria-labelledby="search-title">
        <div>
          <p className="section-label">BM25 SEARCH</p>
          <h2 id="search-title">{dataset?.name ?? "Dataset search"}</h2>
          {dataset && <p className="search-subtitle">{dataset.memory_count} message-level memories · no automatic chunking</p>}
          {datasetError && <div className="feedback feedback-error" role="alert">{datasetError}</div>}
        </div>
        <div className="method-grid" aria-label="Retrieval methods">
          <div className="method-card method-active"><strong>BM25</strong><span>Active in M3</span></div>
          <div className="method-card"><strong>Dense</strong><span>Later milestone</span></div>
          <div className="method-card"><strong>Hybrid</strong><span>Later milestone</span></div>
        </div>
      </section>

      <section className="panel search-form-panel" aria-label="BM25 query">
        <form onSubmit={(event) => void handleSubmit(event)}>
          <label htmlFor="search-query">Query</label>
          <textarea
            id="search-query" rows={3} value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="用户喜欢什么界面主题？"
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
              {state.kind === "loading" ? "Searching…" : "Search memories"}
            </button>
          </div>
        </form>
      </section>

      {state.kind === "idle" && (
        <div className="state-box search-state">Enter a query to rank this dataset with BM25.</div>
      )}
      {state.kind === "loading" && (
        <div className="state-box search-state" role="status">Searching indexed memories…</div>
      )}
      {state.kind === "error" && (
        <div className="state-box state-error search-state" role="alert">{state.message}</div>
      )}
      {state.kind === "success" && state.response.results.length === 0 && (
        <div className="state-box search-state">No results for this query.</div>
      )}
      {state.kind === "success" && state.response.results.length > 0 && (
        <section className="search-results" aria-labelledby="results-title">
          <div className="results-heading">
            <div><p className="section-label">RESULTS</p><h2 id="results-title">BM25 ranking</h2></div>
            <div className="timing-summary">
              <strong>{state.response.timing.total_ms.toFixed(3)} ms</strong>
              <span>{state.response.timing.cache_hit ? "cached index" : "index built"}</span>
            </div>
          </div>
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
                <div className="score-box"><span>BM25 raw</span><strong>{formatScore(result.bm25_raw)}</strong></div>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
