import { useCallback, useEffect, useMemo, useState } from "react";
import { deleteDataset, fetchDatasets, fetchMemories } from "../../api/datasets";
import type { DatasetSummary, MemoryPage } from "../../types/datasets";
import { DatasetImportPanel } from "./DatasetImportPanel";
import { DatasetList } from "./DatasetList";
import { MemoryPreview } from "./MemoryPreview";

const PAGE_SIZE = 10;

export function DatasetPage() {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [memoryPage, setMemoryPage] = useState<MemoryPage | null>(null);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memoryError, setMemoryError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.id === selectedId) ?? null,
    [datasets, selectedId],
  );

  const loadDatasets = useCallback(async (signal?: AbortSignal) => {
    setListLoading(true); setListError(null);
    try {
      const result = await fetchDatasets(signal);
      setDatasets(result.items);
      setSelectedId((current) => current && result.items.some((item) => item.id === current) ? current : result.items[0]?.id ?? null);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setListError(error instanceof Error ? error.message : "Could not load datasets.");
    } finally {
      if (!signal?.aborted) setListLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadDatasets(controller.signal);
    return () => controller.abort();
  }, [loadDatasets]);

  useEffect(() => {
    if (!selectedId) { setMemoryPage(null); setMemoryError(null); return; }
    const controller = new AbortController();
    setMemoryLoading(true); setMemoryError(null);
    void fetchMemories(selectedId, currentPage, PAGE_SIZE, controller.signal)
      .then(setMemoryPage)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setMemoryError(error instanceof Error ? error.message : "Could not load memories.");
      })
      .finally(() => { if (!controller.signal.aborted) setMemoryLoading(false); });
    return () => controller.abort();
  }, [selectedId, currentPage]);

  function selectDataset(id: string) { setSelectedId(id); setCurrentPage(1); }
  function handleImported(dataset: DatasetSummary) {
    setDatasets((current) => [dataset, ...current.filter((item) => item.id !== dataset.id)]);
    setSelectedId(dataset.id); setCurrentPage(1); setListError(null);
  }

  async function handleDelete(dataset: DatasetSummary) {
    if (!window.confirm(`Delete “${dataset.name}” and all of its memories and evaluation cases? This cannot be undone.`)) return;
    setDeletingId(dataset.id); setListError(null);
    try {
      await deleteDataset(dataset.id);
      const remaining = datasets.filter((item) => item.id !== dataset.id);
      setDatasets(remaining);
      if (selectedId === dataset.id) { setSelectedId(remaining[0]?.id ?? null); setCurrentPage(1); }
    } catch (error) {
      setListError(error instanceof Error ? error.message : "Delete failed.");
    } finally { setDeletingId(null); }
  }

  return (
    <div className="workspace-grid">
      <DatasetImportPanel onImported={handleImported} />
      <DatasetList
        datasets={datasets} loading={listLoading} error={listError} selectedId={selectedId}
        deletingId={deletingId} onSelect={selectDataset} onDelete={(dataset) => void handleDelete(dataset)}
        onRetry={() => void loadDatasets()}
      />
      <MemoryPreview
        dataset={selectedDataset} page={memoryPage} loading={memoryLoading}
        error={memoryError} onPageChange={setCurrentPage}
      />
    </div>
  );
}
