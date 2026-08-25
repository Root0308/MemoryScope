import type {
  BM25SearchResponse,
  DenseSearchResponse,
  DatasetListResponse,
  DatasetSummary,
  MemoryPage,
  SearchMethod,
  SearchResponse,
} from "../types/datasets";
import { apiBaseUrl, apiError } from "./client";

export const MAX_IMPORT_BYTES = 20 * 1024 * 1024;

export async function fetchDatasets(signal?: AbortSignal): Promise<DatasetListResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/datasets`, { signal });
  if (!response.ok) throw await apiError(response);
  return (await response.json()) as DatasetListResponse;
}

export async function fetchDataset(
  datasetId: string,
  signal?: AbortSignal,
): Promise<DatasetSummary> {
  const response = await fetch(`${apiBaseUrl}/api/v1/datasets/${datasetId}`, { signal });
  if (!response.ok) throw await apiError(response);
  return (await response.json()) as DatasetSummary;
}

export async function importDataset(file: File): Promise<DatasetSummary> {
  if (file.size > MAX_IMPORT_BYTES) {
    throw new Error("File is larger than the 20 MB import limit.");
  }
  const response = await fetch(`${apiBaseUrl}/api/v1/datasets/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: file,
  });
  if (!response.ok) throw await apiError(response);
  return (await response.json()) as DatasetSummary;
}

export async function fetchMemories(
  datasetId: string,
  page: number,
  pageSize: number,
  signal?: AbortSignal,
): Promise<MemoryPage> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  const response = await fetch(
    `${apiBaseUrl}/api/v1/datasets/${datasetId}/memories?${query}`,
    { signal },
  );
  if (!response.ok) throw await apiError(response);
  return (await response.json()) as MemoryPage;
}

export async function deleteDataset(datasetId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/v1/datasets/${datasetId}`, {
    method: "DELETE",
  });
  if (!response.ok) throw await apiError(response);
}

export async function searchDatasetBM25(
  datasetId: string,
  query: string,
  topK: number,
  signal?: AbortSignal,
): Promise<BM25SearchResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/datasets/${datasetId}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, methods: ["bm25"], top_k: topK }),
    signal,
  });
  if (!response.ok) throw await apiError(response);
  return (await response.json()) as BM25SearchResponse;
}

export async function searchDataset(
  datasetId: string,
  query: string,
  method: SearchMethod,
  topK: number,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const response = await fetch(`${apiBaseUrl}/api/v1/datasets/${datasetId}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, methods: [method], top_k: topK }),
    signal,
  });
  if (!response.ok) throw await apiError(response);
  return (await response.json()) as BM25SearchResponse | DenseSearchResponse;
}
