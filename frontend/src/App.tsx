import { useCallback, useEffect, useState } from "react";

import { fetchHealth } from "./api/health";
import { DatasetPage } from "./features/datasets/DatasetPage";
import type { HealthResponse } from "./types/health";


type HealthState =
  | { kind: "loading" }
  | { kind: "online"; data: HealthResponse }
  | { kind: "offline"; message: string };


function App() {
  const [health, setHealth] = useState<HealthState>({ kind: "loading" });

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
      <DatasetPage />
      <footer><span>v0.1 · M2 JSON import & SQLite</span><span>No conversation data leaves this machine.</span></footer>
    </main>
  );
}

export default App;
