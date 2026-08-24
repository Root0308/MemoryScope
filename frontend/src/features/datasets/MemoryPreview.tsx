import type { DatasetSummary, MemoryPage } from "../../types/datasets";

type Props = {
  dataset: DatasetSummary | null; page: MemoryPage | null; loading: boolean;
  error: string | null; onPageChange: (page: number) => void;
};

export function MemoryPreview({ dataset, page, loading, error, onPageChange }: Props) {
  return (
    <section className="panel preview-panel" aria-labelledby="memories-title">
      <div className="panel-heading">
        <div><p className="section-label">PREVIEW</p><h2 id="memories-title">{dataset ? dataset.name : "Memories"}</h2></div>
        {page && <span className="count-badge">{page.total}</span>}
      </div>
      {!dataset && <div className="state-box">Select a dataset to inspect one message per memory.</div>}
      {dataset && loading && <div className="state-box">Loading memories…</div>}
      {dataset && !loading && error && <div className="state-box state-error">{error}</div>}
      {dataset && !loading && !error && page?.items.length === 0 && <div className="state-box">This dataset has no memories.</div>}
      {dataset && !loading && !error && page && page.items.length > 0 && (
        <>
          <div className="memory-list">
            {page.items.map((memory) => (
              <article className="memory-card" key={memory.id}>
                <div className="memory-meta">
                  <span className={`role role-${memory.role}`}>{memory.role}</span>
                  <code>{memory.id}</code><span>{memory.conversation_id}</span>
                </div>
                <p>{memory.content}</p>
                {(memory.timestamp || memory.metadata) && (
                  <div className="memory-details">
                    {memory.timestamp && <time>{new Date(memory.timestamp).toLocaleString()}</time>}
                    {memory.metadata && <code>{JSON.stringify(memory.metadata)}</code>}
                  </div>
                )}
              </article>
            ))}
          </div>
          <nav className="pagination" aria-label="Memory pages">
            <button type="button" disabled={page.page <= 1} onClick={() => onPageChange(page.page - 1)}>Previous</button>
            <span>Page {page.page} of {Math.max(page.total_pages, 1)}</span>
            <button type="button" disabled={page.page >= page.total_pages} onClick={() => onPageChange(page.page + 1)}>Next</button>
          </nav>
        </>
      )}
    </section>
  );
}
