export type DatasetSummary = {
  id: string;
  schema_version: string;
  name: string;
  imported_at: string;
  conversation_count: number;
  memory_count: number;
  evaluation_case_count: number;
};

export type DatasetListResponse = {
  items: DatasetSummary[];
  total: number;
};

export type Memory = {
  id: string;
  conversation_id: string;
  position: number;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  timestamp: string | null;
  metadata: Record<string, unknown> | null;
};

export type MemoryPage = {
  items: Memory[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type BM25SearchResult = {
  final_rank: number;
  memory_id: string;
  conversation_id: string;
  role: Memory["role"];
  content: string;
  timestamp: string | null;
  metadata: Record<string, unknown> | null;
  bm25_raw: number;
  bm25_rank: number;
};

export type BM25SearchResponse = {
  query: string;
  method: "bm25";
  top_k: number;
  total_memories: number;
  timing: {
    total_ms: number;
    index_ms: number;
    search_ms: number;
    cache_hit: boolean;
  };
  results: BM25SearchResult[];
};
