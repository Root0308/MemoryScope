import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { evaluateDataset } from "../../api/datasets";
import type {
  DatasetSummary,
  EvaluationCaseResult,
  EvaluationMethodReport,
  EvaluationResponse,
  SearchMethod,
} from "../../types/datasets";


type Props = {
  dataset: DatasetSummary | null;
  datasetError: string | null;
  datasetId: string;
};

type EvaluationState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; response: EvaluationResponse }
  | { kind: "error"; message: string };

const METHOD_META: Array<{
  key: SearchMethod;
  label: string;
  latencyNote: string;
}> = [
  { key: "bm25", label: "BM25", latencyNote: "lexical ranking only" },
  { key: "dense", label: "Dense", latencyNote: "query encoding + cosine ranking" },
  { key: "hybrid", label: "Hybrid", latencyNote: "RRF fusion only" },
];

function formatMetric(value: number) {
  return value.toFixed(4);
}

function formatLatency(value: number) {
  return `${value.toFixed(3)} ms`;
}

function IdList({ ids, emptyLabel = "None" }: { ids: string[]; emptyLabel?: string }) {
  if (ids.length === 0) return <span className="evaluation-empty-value">{emptyLabel}</span>;
  return <div className="evaluation-id-list">{ids.map((id) => <code key={id}>{id}</code>)}</div>;
}

function MetricCard({
  label,
  report,
  k,
}: {
  label: string;
  report: EvaluationMethodReport;
  k: number;
}) {
  const methodMeta = METHOD_META.find((method) => method.key === report.method);
  return (
    <article className={`evaluation-method-card evaluation-${report.method}`}>
      <header><h3>{label}</h3><span>{methodMeta?.latencyNote}</span></header>
      <div className="evaluation-card-metrics">
        <div><span>Recall@{k}</span><strong>{formatMetric(report.aggregate.recall_at_k)}</strong></div>
        <div><span>MRR@{k}</span><strong>{formatMetric(report.aggregate.mrr_at_k)}</strong></div>
        <div><span>Average latency</span><strong>{formatLatency(report.aggregate.average_latency_ms)}</strong></div>
        <div><span>P50 latency</span><strong>{formatLatency(report.aggregate.p50_latency_ms)}</strong></div>
      </div>
    </article>
  );
}

function CaseMethodRow({
  label,
  result,
  k,
}: {
  label: string;
  result: EvaluationCaseResult;
  k: number;
}) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td><IdList ids={result.retrieved_message_ids} /></td>
      <td><IdList ids={result.retrieved_relevant_message_ids} emptyLabel="No relevant hit" /></td>
      <td>{formatMetric(result.recall_at_k)}</td>
      <td>{formatMetric(result.reciprocal_rank)}</td>
      <td>{result.first_relevant_rank === null ? "—" : `#${result.first_relevant_rank}`}</td>
      <td>{formatLatency(result.latency_ms)}</td>
      <td className="evaluation-k-label">top {k}</td>
    </tr>
  );
}

export function EvaluationPanel({ dataset, datasetError, datasetId }: Props) {
  const [k, setK] = useState("10");
  const [state, setState] = useState<EvaluationState>({ kind: "idle" });
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedK = Number(k);
    if (!Number.isInteger(parsedK) || parsedK < 1 || parsedK > 50) {
      setState({ kind: "error", message: "k must be an integer from 1 to 50." });
      return;
    }
    if (!dataset || dataset.evaluation_case_count === 0) return;

    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setState({ kind: "loading" });
    try {
      const response = await evaluateDataset(datasetId, parsedK, controller.signal);
      setState({ kind: "success", response });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setState({
        kind: "error",
        message: error instanceof Error ? error.message : "Evaluation failed.",
      });
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }

  const response = state.kind === "success" ? state.response : null;
  const metricChartData = response === null ? [] : METHOD_META.map(({ key, label }) => ({
    method: label,
    Recall: response[key].aggregate.recall_at_k,
    MRR: response[key].aggregate.mrr_at_k,
  }));
  const latencyChartData = response === null ? [] : METHOD_META.map(({ key, label }) => ({
    method: label,
    Average: response[key].aggregate.average_latency_ms,
    P50: response[key].aggregate.p50_latency_ms,
  }));
  const denseCases = new Map(response?.dense.cases.map((item) => [item.eval_case_id, item]));
  const hybridCases = new Map(response?.hybrid.cases.map((item) => [item.eval_case_id, item]));
  const noHitPairs = response === null ? 0 : METHOD_META.reduce(
    (count, method) => count + response[method.key].cases.filter(
      (item) => item.retrieved_relevant_message_ids.length === 0,
    ).length,
    0,
  );

  return (
    <>
      <section className="panel evaluation-hero" aria-labelledby="evaluation-title">
        <div>
          <p className="section-label">LABELLED RETRIEVAL EVALUATION</p>
          <h2 id="evaluation-title">{dataset?.name ?? "Dataset evaluation"}</h2>
          {dataset && (
            <p className="search-subtitle">
              {dataset.evaluation_case_count} evaluation cases · {dataset.memory_count} memories
            </p>
          )}
          {datasetError && <div className="feedback feedback-error" role="alert">{datasetError}</div>}
        </div>
        <div className="evaluation-hero-note">
          <strong>Human labels define relevance</strong>
          <span>Recall and MRR use imported relevant_memory_ids, returned by the API as relevant_message_ids. They are not automated facts or a statistical significance claim.</span>
        </div>
      </section>

      {dataset && dataset.evaluation_case_count === 0 ? (
        <div className="state-box evaluation-empty-state" role="status">
          <strong>No evaluation cases in this dataset</strong>
          <p>Add evaluation_cases with relevant_memory_ids to the import JSON, then import it as a new dataset.</p>
        </div>
      ) : (
        <>
          <aside className="dense-notice" aria-label="Evaluation model preparation information">
            <strong>Shared local preparation is measured separately</strong>
            <span>Each labelled query encodes one Dense vector. BM25 and Dense rankings are reused for Hybrid RRF.</span>
            <span>First use may initialize/download the fixed model and build missing SQLite vectors; that work is not repeated in method latency bars.</span>
          </aside>

          <section className="panel evaluation-form-panel" aria-label="Evaluation controls">
            <form onSubmit={(event) => void handleSubmit(event)}>
              <label htmlFor="evaluation-k">Evaluation cutoff k</label>
              <div className="evaluation-controls">
                <input
                  id="evaluation-k"
                  type="number"
                  min="1"
                  max="50"
                  step="1"
                  value={k}
                  onChange={(event) => setK(event.target.value)}
                  disabled={!dataset || state.kind === "loading"}
                />
                <button type="submit" disabled={!dataset || state.kind === "loading"}>
                  {state.kind === "loading" ? "Evaluating…" : "Run BM25, Dense & Hybrid evaluation"}
                </button>
              </div>
            </form>
          </section>

          {state.kind === "idle" && (
            <div className="state-box search-state">
              Choose k and run all imported evaluation cases locally.
            </div>
          )}
          {state.kind === "loading" && (
            <div className="state-box dense-progress search-state" role="status">
              <strong>Running labelled retrieval evaluation…</strong>
              <span>Initializing the fixed local model; first use may take longer.</span>
              <span>Checking or building shared SQLite memory vectors.</span>
              <span>Encoding each query once and reusing branch ranks for Hybrid.</span>
            </div>
          )}
          {state.kind === "error" && (
            <div className="state-box state-error search-state" role="alert">
              <strong>Evaluation could not complete.</strong><p>{state.message}</p>
            </div>
          )}
        </>
      )}

      {response !== null && (
        <section className="evaluation-results" aria-labelledby="evaluation-results-title">
          <div className="results-heading">
            <div><p className="section-label">EVALUATION</p><h2 id="evaluation-results-title">Recall@{response.k}, MRR@{response.k} and latency</h2></div>
            <div className="timing-summary"><strong>{formatLatency(response.total_ms)}</strong><span>{response.case_count} labelled cases · {response.model.memory_embeddings_built ? "vectors built" : "SQLite vectors reused"}</span></div>
          </div>

          <div className="compare-model-status evaluation-model-status">
            <div><span>Model</span><strong>{response.model.name}</strong></div>
            <div><span>Revision</span><strong>{response.model.model_revision}</strong></div>
            <div><span>Configuration</span><strong>{response.model.dimension}d · {response.model.normalized ? "normalized" : "not normalized"}</strong></div>
            <div><span>Embedding version</span><strong>{response.model.embedding_version}</strong></div>
            <div className="compare-signature"><span>Embedding signature</span><code>{response.model.embedding_signature}</code></div>
            <div><span>Memory vectors</span><strong>{response.model.memory_embeddings_built ? "built" : "reused"}</strong></div>
          </div>

          <div className="hybrid-scale-note evaluation-definition-note">
            <strong>Macro averages over human-labelled cases</strong>
            <span>Recall@k averages each case’s relevant hits / relevant labels. MRR@k averages the reciprocal rank of the first relevant hit.</span>
            <span>Displayed values are rounded for readability only; API numbers retain their underlying precision. Small local datasets do not establish general retrieval quality.</span>
          </div>

          {noHitPairs > 0 && (
            <div className="compare-no-match" role="status">
              {noHitPairs} method/case pair{noHitPairs === 1 ? "" : "s"} had no relevant result in top {response.k}; Recall and reciprocal rank are 0 for those pairs.
            </div>
          )}

          <div className="evaluation-method-grid">
            {METHOD_META.map(({ key, label }) => (
              <MetricCard key={key} label={label} report={response[key]} k={response.k} />
            ))}
          </div>

          <section className="panel evaluation-chart-panel" aria-labelledby="quality-chart-title">
            <div className="panel-heading"><div><p className="section-label">QUALITY METRICS</p><h2 id="quality-chart-title">Method comparison</h2></div><span className="limit-note">0–1 · higher is better</span></div>
            <div className="evaluation-chart" role="img" aria-label={`Bar chart comparing Recall at ${response.k} and MRR at ${response.k} for BM25, Dense, and Hybrid`}>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={metricChartData} margin={{ top: 12, right: 12, bottom: 10, left: 4 }}>
                  <CartesianGrid stroke="#1d3b42" vertical={false} />
                  <XAxis dataKey="method" tick={{ fill: "#89a1a8", fontSize: 12 }} />
                  <YAxis domain={[0, 1]} tick={{ fill: "#738b92", fontSize: 11 }} width={48} />
                  <Tooltip formatter={(value) => Number(value).toFixed(4)} contentStyle={{ background: "#0a1d22", border: "1px solid #29464e", borderRadius: 8 }} />
                  <Legend />
                  <Bar dataKey="Recall" fill="#61d4bd" radius={[5, 5, 0, 0]} />
                  <Bar dataKey="MRR" fill="#7fb6ea" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="panel evaluation-chart-panel" aria-labelledby="latency-chart-title">
            <div className="panel-heading"><div><p className="section-label">LATENCY</p><h2 id="latency-chart-title">Method-specific compute</h2></div><span className="limit-note">milliseconds</span></div>
            <div className="compare-shared-grid">
              <div className="compare-shared-timing"><span>Shared preparation</span><strong>{formatLatency(response.preparation_ms)}</strong><small>model, vectors and per-query data preparation; excluded from method bars</small></div>
              <div className="compare-shared-timing"><span>Total evaluation</span><strong>{formatLatency(response.total_ms)}</strong><small>all {response.case_count} cases plus preparation and response assembly</small></div>
            </div>
            <div className="evaluation-chart" role="img" aria-label="Bar chart comparing average and P50 method latency in milliseconds">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={latencyChartData} margin={{ top: 12, right: 12, bottom: 10, left: 4 }}>
                  <CartesianGrid stroke="#1d3b42" vertical={false} />
                  <XAxis dataKey="method" tick={{ fill: "#89a1a8", fontSize: 12 }} />
                  <YAxis tick={{ fill: "#738b92", fontSize: 11 }} unit=" ms" width={66} />
                  <Tooltip formatter={(value) => `${Number(value).toFixed(3)} ms`} contentStyle={{ background: "#0a1d22", border: "1px solid #29464e", borderRadius: 8 }} />
                  <Legend />
                  <Bar dataKey="Average" fill="#e1c96e" radius={[5, 5, 0, 0]} />
                  <Bar dataKey="P50" fill="#b98be6" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="evaluation-latency-note">BM25 is lexical ranking only; Dense is query encoding plus exact cosine ranking; Hybrid is RRF fusion only.</p>
          </section>

          <section className="panel evaluation-case-panel" aria-labelledby="case-details-title">
            <div className="panel-heading"><div><p className="section-label">CASE DETAILS</p><h2 id="case-details-title">Per-query evidence</h2></div><span className="count-badge">{response.case_count}</span></div>
            <div className="evaluation-case-list">
              {response.bm25.cases.map((bm25Case, index) => {
                const denseCase = denseCases.get(bm25Case.eval_case_id);
                const hybridCase = hybridCases.get(bm25Case.eval_case_id);
                if (!denseCase || !hybridCase) return null;
                return (
                  <details className="evaluation-case" key={bm25Case.eval_case_id} open={index === 0}>
                    <summary><span><code>{bm25Case.eval_case_id}</code>{bm25Case.query}</span><strong>{bm25Case.relevant_message_ids.length} relevant</strong></summary>
                    <div className="evaluation-case-body">
                      <div className="evaluation-labels"><span>Human-labelled relevant IDs</span><IdList ids={bm25Case.relevant_message_ids} /></div>
                      <div className="evaluation-case-table-wrap">
                        <table className="evaluation-case-table">
                          <thead><tr><th>Method</th><th>Retrieved IDs</th><th>Relevant hits</th><th>Recall</th><th>RR</th><th>First rank</th><th>Latency</th><th>Cutoff</th></tr></thead>
                          <tbody>
                            <CaseMethodRow label="BM25" result={bm25Case} k={response.k} />
                            <CaseMethodRow label="Dense" result={denseCase} k={response.k} />
                            <CaseMethodRow label="Hybrid" result={hybridCase} k={response.k} />
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </details>
                );
              })}
            </div>
          </section>
        </section>
      )}
    </>
  );
}
