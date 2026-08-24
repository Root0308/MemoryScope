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
