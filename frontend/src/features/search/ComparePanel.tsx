import { useEffect, useRef, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { compareDatasetSearch } from "../../api/datasets";
import type {
  BM25SearchResult,
  CompareSearchResponse,
  DatasetSummary,
  DenseSearchResult,
  HybridSearchResult,
} from "../../types/datasets";

type Props = {
  dataset: DatasetSummary | null;
  datasetError: string | null;
  datasetId: string;
};

type CompareState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; response: CompareSearchResponse }
  | { kind: "error"; message: string };

type MethodResult = BM25SearchResult | DenseSearchResult | HybridSearchResult;

const TIMING_COLORS = ["#61d4bd", "#7fb6ea", "#e1c96e"];

function formatScore(score: number) {
  return score.toFixed(6);
}

function identityColor(memoryId: string) {
  let hash = 0;
  for (const character of memoryId) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360} 58% 58%)`;
}

function resultScore(result: MethodResult): { label: string; value: string } {
  if ("bm25_raw" in result) {
    return { label: "BM25 raw", value: formatScore(result.bm25_raw) };
  }
  if ("rrf_total" in result) {
    return { label: "RRF total", value: formatScore(result.rrf_total) };
  }
  return { label: "cosine", value: formatScore(result.dense_cosine) };
}

function MethodColumn({
  label,
  note,
  results,
}: {
  label: string;
  note: string;
  results: MethodResult[];
}) {
  return (
    <section className="compare-method-column" aria-label={`${label} results`}>
      <header><div><h3>{label}</h3><p>{note}</p></div><span>{results.length}</span></header>
      {results.length === 0 ? (
        <div className="compare-empty">No results in this top_k.</div>
      ) : (
        <div className="compare-method-list">
          {results.map((result) => {
            const score = resultScore(result);
            const style = { "--memory-color": identityColor(result.memory_id) } as CSSProperties;
            return (
              <article className="compare-result-card" key={result.memory_id} style={style}>
                <div className="compare-result-rank">#{result.final_rank}</div>
                <code>{result.memory_id}</code>
                <p>{result.content}</p>
                <div><span>{score.label}</span><strong>{score.value}</strong></div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function RankCell({ rank, topK }: { rank: number | null; topK: number }) {
  if (rank === null) return <span className="rank-missing" aria-label="Not in top k">—</span>;
  const width = `${Math.max(18, ((topK - rank + 1) / topK) * 100)}%`;
  return (
    <div className="rank-track" aria-label={`Rank ${rank}`}>
      <span style={{ width }}>{`#${rank}`}</span>
    </div>
  );
}

function TimingCard({ label, value, children }: { label: string; value: number; children: ReactNode }) {
  return (
    <div className="compare-shared-timing">
      <span>{label}</span><strong>{value.toFixed(3)} ms</strong><small>{children}</small>
    </div>
  );
}

export function ComparePanel({ dataset, datasetError, datasetId }: Props) {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState("10");
  const [state, setState] = useState<CompareState>({ kind: "idle" });
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedTopK = Number(topK);
    if (!Number.isInteger(parsedTopK) || parsedTopK < 1 || parsedTopK > 50) {
      setState({ kind: "error", message: "top_k must be an integer from 1 to 50." });
      return;
    }
    if (!query.trim()) {
      setState({ kind: "error", message: "Enter a query before comparing methods." });
      return;
    }

    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setState({ kind: "loading" });
    try {
      const response = await compareDatasetSearch(
        datasetId,
        query,
        parsedTopK,
        controller.signal,
      );
      setState({ kind: "success", response });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setState({
        kind: "error",
        message: error instanceof Error ? error.message : "Method comparison failed.",
      });
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }

  const response = state.kind === "success" ? state.response : null;
  const noResults = response !== null
    && response.bm25_results.length === 0
    && response.dense_results.length === 0
    && response.hybrid_results.length === 0;
  const noLexicalMatches = response !== null
    && response.bm25_results.length > 0
    && response.bm25_results.every((result) => result.bm25_raw === 0);
  const chartData = response === null ? [] : [
    { phase: "BM25 ranking", milliseconds: response.timing.bm25_ms },
    { phase: "Dense query + rank", milliseconds: response.timing.dense_ms },
    { phase: "Hybrid fusion", milliseconds: response.timing.hybrid_fusion_ms },
  ];

  return (
    <>
      <section className="panel compare-hero" aria-labelledby="compare-title">
        <div>
          <p className="section-label">THREE-METHOD COMPARISON</p>
          <h2 id="compare-title">{dataset?.name ?? "Dataset comparison"}</h2>
          {dataset && <p className="search-subtitle">{dataset.memory_count} message-level memories · one shared query snapshot</p>}
          {datasetError && <div className="feedback feedback-error" role="alert">{datasetError}</div>}
        </div>
        <div className="compare-hero-note">
          <strong>Compare ranks, not raw score scales</strong>
          <span>BM25 raw and Dense cosine use different units. Hybrid reuses their candidate ranks with RRF.</span>
        </div>
      </section>

      <aside className="dense-notice" aria-label="Compare model preparation information">
        <strong>One local Dense pass per comparison</strong>
        <span>The query vector is encoded once. BM25 and Dense candidate rankings are reused by Hybrid.</span>
        <span>First use may initialize/download the fixed model and build missing SQLite vectors.</span>
      </aside>

      <section className="panel search-form-panel" aria-label="Compare methods query">
        <form onSubmit={(event) => void handleSubmit(event)}>
          <label htmlFor="compare-query">Query</label>
          <textarea
            id="compare-query" rows={3} value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="用户喜欢什么界面主题？"
            disabled={!dataset || state.kind === "loading"}
          />
          <div className="search-controls">
            <label htmlFor="compare-top-k">top_k
              <input
                id="compare-top-k" type="number" min="1" max="50" step="1"
                value={topK} onChange={(event) => setTopK(event.target.value)}
                disabled={!dataset || state.kind === "loading"}
              />
            </label>
            <button type="submit" disabled={!dataset || state.kind === "loading"}>
              {state.kind === "loading" ? "Comparing…" : "Compare BM25, Dense & Hybrid"}
            </button>
          </div>
        </form>
      </section>

      {state.kind === "idle" && <div className="state-box search-state">Run one query to compare all three rankings.</div>}
      {state.kind === "loading" && (
        <div className="state-box dense-progress search-state" role="status">
          <strong>Preparing three-method comparison…</strong>
          <span>Initializing the local model and checking shared SQLite vectors.</span>
          <span>Encoding the query once and ranking BM25/Dense candidate pools.</span>
          <span>Reusing those candidates for Hybrid RRF and rank alignment.</span>
        </div>
      )}
      {state.kind === "error" && (
        <div className="state-box state-error search-state" role="alert">
          <strong>Method comparison could not complete.</strong><p>{state.message}</p>
        </div>
      )}
      {noResults && <div className="state-box search-state">No results were returned by any method.</div>}

      {response !== null && !noResults && (
        <section className="compare-results" aria-labelledby="compare-results-title">
          <div className="results-heading">
            <div><p className="section-label">COMPARISON</p><h2 id="compare-results-title">Rankings for one shared query</h2></div>
            <div className="timing-summary"><strong>{response.timing.total_ms.toFixed(3)} ms</strong><span>{response.model.memory_embeddings_built ? "dataset vectors built" : "SQLite vectors reused"}</span></div>
          </div>

          <div className="compare-model-status">
            <div><span>Model</span><strong>{response.model.name}</strong></div>
            <div><span>Revision</span><strong>{response.model.model_revision}</strong></div>
            <div><span>Configuration</span><strong>{response.model.dimension}d · {response.model.normalized ? "normalized" : "not normalized"}</strong></div>
            <div><span>Embedding version</span><strong>{response.model.embedding_version}</strong></div>
            <div className="compare-signature"><span>Embedding signature</span><code>{response.model.embedding_signature}</code></div>
            <div><span>Memory vectors</span><strong>{response.model.memory_embeddings_built ? "built" : "reused"}</strong></div>
          </div>

          <div className="hybrid-scale-note compare-scale-note">
            <strong>BM25 与 Dense 原始分数尺度不同；此处比较排名，不直接比较原始分数。</strong>
            <span>Hybrid uses the same {response.candidate_pool_size} candidates per branch with rrf_k {response.rrf_k}. Compare is exploratory inspection, not Recall/MRR evaluation.</span>
          </div>
          {noLexicalMatches && (
            <div className="compare-no-match" role="status">
              No lexical BM25 matches were found; deterministic zero-score ranks are shown while Dense and Hybrid remain available.
            </div>
          )}

          <div className="compare-method-grid">
            <MethodColumn label="BM25" note="raw lexical score" results={response.bm25_results} />
            <MethodColumn label="Dense" note="cosine similarity" results={response.dense_results} />
            <MethodColumn label="Hybrid" note="RRF total" results={response.hybrid_results} />
          </div>

          <section className="panel compare-rank-panel" aria-labelledby="rank-matrix-title">
            <div className="panel-heading"><div><p className="section-label">RANK MATRIX</p><h2 id="rank-matrix-title">Memory alignment across methods</h2></div><span className="count-badge">{response.comparison_rows.length}</span></div>
            <div className="rank-table-wrap">
              <table className="rank-table">
                <thead><tr><th>Memory</th><th>Content</th><th>BM25 rank</th><th>Dense rank</th><th>Hybrid rank</th></tr></thead>
                <tbody>
                  {response.comparison_rows.map((row) => (
                    <tr key={row.memory_id}>
                      <th scope="row"><code style={{ borderColor: identityColor(row.memory_id) }}>{row.memory_id}</code></th>
                      <td><span className="rank-content">{row.content}</span></td>
                      <td><RankCell rank={row.bm25_rank} topK={response.top_k} /></td>
                      <td><RankCell rank={row.dense_rank} topK={response.top_k} /></td>
                      <td><RankCell rank={row.hybrid_rank} topK={response.top_k} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel compare-timing-panel" aria-labelledby="timing-chart-title">
            <div className="panel-heading"><div><p className="section-label">TIMING</p><h2 id="timing-chart-title">Method-specific compute</h2></div><span className="limit-note">milliseconds</span></div>
            <div className="compare-shared-grid">
              <TimingCard label="Shared preparation" value={response.timing.preparation_ms}>model, vectors, dataset/index preparation</TimingCard>
              <TimingCard label="Total request" value={response.timing.total_ms}>preparation + three ranking stages + response assembly</TimingCard>
            </div>
            <div className="timing-chart" role="img" aria-label="Bar chart comparing BM25 ranking, Dense query and ranking, and Hybrid fusion milliseconds">
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={chartData} margin={{ top: 12, right: 12, bottom: 24, left: 4 }}>
                  <CartesianGrid stroke="#1d3b42" vertical={false} />
                  <XAxis dataKey="phase" tick={{ fill: "#89a1a8", fontSize: 12 }} interval={0} angle={-8} textAnchor="end" height={54} />
                  <YAxis tick={{ fill: "#738b92", fontSize: 11 }} unit=" ms" width={66} />
                  <Tooltip formatter={(value) => [`${Number(value).toFixed(3)} ms`, "Elapsed"]} contentStyle={{ background: "#0a1d22", border: "1px solid #29464e", borderRadius: 8 }} />
                  <Bar dataKey="milliseconds" radius={[7, 7, 0, 0]}>
                    {chartData.map((entry, index) => <Cell key={entry.phase} fill={TIMING_COLORS[index]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="timing-values-table" aria-label="Timing values">
              {chartData.map((entry) => <div key={entry.phase}><span>{entry.phase}</span><strong>{entry.milliseconds.toFixed(3)} ms</strong></div>)}
            </div>
          </section>
        </section>
      )}
    </>
  );
}
