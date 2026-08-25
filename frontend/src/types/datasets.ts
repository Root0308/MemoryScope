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

export type DenseSearchResult = {
  final_rank: number;
  memory_id: string;
  conversation_id: string;
  role: Memory["role"];
  content: string;
  timestamp: string | null;
  metadata: Record<string, unknown> | null;
  dense_cosine: number;
  dense_rank: number;
};

export type DenseSearchResponse = {
  query: string;
  method: "dense";
  top_k: number;
  total_memories: number;
  model: {
    name: string;
    model_revision: string;
    dimension: number;
    normalized: boolean;
    embedding_version: string;
    initialized_this_request: boolean;
    memory_embeddings_built: boolean;
  };
  timing: {
    total_ms: number;
    model_load_ms: number;
    memory_embedding_ms: number;
    query_embedding_ms: number;
    search_ms: number;
  };
  results: DenseSearchResult[];
};

export type SearchMethod = "bm25" | "dense";
export type SearchResponse = BM25SearchResponse | DenseSearchResponse;
