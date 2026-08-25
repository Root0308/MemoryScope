import { useCallback, useEffect, useState } from "react";

import { fetchHealth } from "./api/health";
import { DatasetPage } from "./features/datasets/DatasetPage";
import { SearchPage } from "./features/search/SearchPage";
import type { HealthResponse } from "./types/health";


type HealthState =
  | { kind: "loading" }
  | { kind: "online"; data: HealthResponse }
  | { kind: "offline"; message: string };

function searchDatasetIdFromPath(): string | null {
  const match = window.location.pathname.match(/^\/datasets\/([^/]+)\/search\/?$/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}


function App() {
  const [health, setHealth] = useState<HealthState>({ kind: "loading" });
  const [searchDatasetId, setSearchDatasetId] = useState<string | null>(searchDatasetIdFromPath);

  const checkHealth = useCallback(async (signal?: AbortSignal) => {
    setHealth({ kind: "loading" });

    try {
      const data = await fetchHealth(signal);
      setHealth({ kind: "online", data });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }

      const message =
        error instanceof Error ? error.message : "Unable to reach the backend";
      setHealth({ kind: "offline", message });
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void checkHealth(controller.signal);

    return () => controller.abort();
  }, [checkHealth]);

  useEffect(() => {
    const handlePopState = () => setSearchDatasetId(searchDatasetIdFromPath());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  function openSearch(datasetId: string) {
    window.history.pushState({}, "", `/datasets/${encodeURIComponent(datasetId)}/search`);
    setSearchDatasetId(datasetId);
  }

  function closeSearch() {
    window.history.pushState({}, "", "/");
    setSearchDatasetId(null);
  }

  const statusLabel =
    health.kind === "loading"
      ? "Checking"
      : health.kind === "online"
        ? "Backend online"
        : "Backend unavailable";

  return (
    <main className="shell">
      <header className="topbar" aria-labelledby="page-title">
        <div>
        <p className="eyebrow">LOCAL AGENT MEMORY WORKSPACE</p>
        <h1 id="page-title">MemoryScope</h1>
        <p className="lede">
          Import strict conversation JSON and inspect one message per memory.
        </p>
        </div>
        <div className={"health-pill status-" + health.kind}>
          <div className="status-line"><span className="status-dot" aria-hidden="true" /><strong>{statusLabel}</strong></div>
          {health.kind === "online" && <span>{health.data.service} · v{health.data.version} · {health.data.database.engine}</span>}
          {health.kind === "offline" && <button type="button" onClick={() => void checkHealth()}>Retry</button>}
        </div>
      </header>
      {health.kind === "offline" && <div className="global-error" role="alert">{health.message}</div>}
      {searchDatasetId ? (
        <SearchPage datasetId={searchDatasetId} onBack={closeSearch} />
      ) : (
        <DatasetPage onSearch={openSearch} />
      )}
      <footer><span>v0.1 · M5 BM25 + Dense + explainable Hybrid RRF</span><span>No conversation data leaves this machine.</span></footer>
    </main>
  );
}

export default App;
