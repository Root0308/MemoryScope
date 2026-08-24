import { useCallback, useEffect, useState } from "react";

import { fetchHealth } from "./api/health";
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
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">LOCAL AGENT MEMORY WORKSPACE</p>
        <h1 id="page-title">MemoryScope</h1>
        <p className="lede">
          Inspect, compare, and evaluate how agents retrieve conversation
          memory.
        </p>

        <div className={"status-card status-" + health.kind}>
          <div>
            <p className="status-kicker">API HEALTH</p>
            <div className="status-line">
              <span className="status-dot" aria-hidden="true" />
              <strong>{statusLabel}</strong>
            </div>
          </div>

          {health.kind === "online" && (
            <dl>
              <div>
                <dt>Service</dt>
                <dd>{health.data.service}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{health.data.version}</dd>
              </div>
              <div>
                <dt>Storage</dt>
                <dd>
                  {health.data.database.engine} ·{" "}
                  {health.data.database.status}
                </dd>
              </div>
            </dl>
          )}

          {health.kind === "offline" && (
            <div className="offline-detail">
              <p>{health.message}</p>
              <button type="button" onClick={() => void checkHealth()}>
                Try again
              </button>
            </div>
          )}
        </div>

        <footer>
          <span>v0.1 · M1 foundation</span>
          <span>No conversation data leaves this machine.</span>
        </footer>
      </section>
    </main>
  );
}

export default App;
