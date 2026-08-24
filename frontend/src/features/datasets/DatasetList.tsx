import type { DatasetSummary } from "../../types/datasets";

type Props = {
  datasets: DatasetSummary[]; loading: boolean; error: string | null;
  selectedId: string | null; deletingId: string | null;
  onSelect: (id: string) => void; onDelete: (dataset: DatasetSummary) => void; onRetry: () => void;
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function DatasetList(props: Props) {
  const { datasets, loading, error, selectedId, deletingId, onSelect, onDelete, onRetry } = props;
  return (
    <section className="panel" aria-labelledby="datasets-title">
      <div className="panel-heading">
        <div><p className="section-label">LIBRARY</p><h2 id="datasets-title">Datasets</h2></div>
        <span className="count-badge">{datasets.length}</span>
      </div>
      {loading && <div className="state-box">Loading datasets…</div>}
      {!loading && error && (
        <div className="state-box state-error"><p>{error}</p><button type="button" onClick={onRetry}>Try again</button></div>
      )}
      {!loading && !error && datasets.length === 0 && (
        <div className="state-box"><strong>No datasets yet</strong><p>Import a schema 0.1 JSON file to preview its memories.</p></div>
      )}
      {!loading && !error && datasets.length > 0 && (
        <div className="dataset-list">
          {datasets.map((dataset) => (
            <article className={`dataset-card${selectedId === dataset.id ? " is-selected" : ""}`} key={dataset.id}>
              <button className="dataset-select" type="button" onClick={() => onSelect(dataset.id)}>
                <span className="dataset-name">{dataset.name}</span>
                <span className="dataset-date">Imported {formatDate(dataset.imported_at)}</span>
                <span className="stats-row">
                  <span><strong>{dataset.conversation_count}</strong> conversations</span>
                  <span><strong>{dataset.memory_count}</strong> memories</span>
                  <span><strong>{dataset.evaluation_case_count}</strong> eval cases</span>
                </span>
              </button>
              <button
                className="delete-button" type="button" disabled={deletingId === dataset.id}
                onClick={() => onDelete(dataset)} aria-label={`Delete ${dataset.name}`}
              >{deletingId === dataset.id ? "Deleting…" : "Delete"}</button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
