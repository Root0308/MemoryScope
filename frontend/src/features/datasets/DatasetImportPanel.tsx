import { useRef, useState } from "react";
import { importDataset, MAX_IMPORT_BYTES } from "../../api/datasets";
import type { DatasetSummary } from "../../types/datasets";

type Props = { onImported: (dataset: DatasetSummary) => void };
type ImportState =
  | { kind: "idle" }
  | { kind: "validating"; fileName: string }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

export function DatasetImportPanel({ onImported }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [state, setState] = useState<ImportState>({ kind: "idle" });

  async function handleFile(file: File | undefined) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".json")) {
      setState({ kind: "error", message: "Select a .json file." });
      return;
    }
    setState({ kind: "validating", fileName: file.name });
    try {
      const dataset = await importDataset(file);
      setState({
        kind: "success",
        message: `${dataset.name} passed validation and imported ${dataset.memory_count} memories.`,
      });
      onImported(dataset);
      if (inputRef.current) inputRef.current.value = "";
    } catch (error) {
      setState({ kind: "error", message: error instanceof Error ? error.message : "Import failed." });
    }
  }

  return (
    <section className="panel import-panel" aria-labelledby="import-title">
      <div className="panel-heading">
        <div><p className="section-label">IMPORT</p><h2 id="import-title">Add a conversation dataset</h2></div>
        <span className="limit-note">JSON · max {MAX_IMPORT_BYTES / 1024 / 1024} MB</span>
      </div>
      <div
        className={`drop-zone${dragging ? " is-dragging" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false); }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          void handleFile(event.dataTransfer.files[0]);
        }}
      >
        <input
          ref={inputRef}
          id="dataset-file"
          type="file"
          accept="application/json,.json"
          onChange={(event) => void handleFile(event.target.files?.[0])}
        />
        <p className="drop-title">Drop a MemoryScope JSON file here</p>
        <p>or</p>
        <button type="button" onClick={() => inputRef.current?.click()}>Choose JSON file</button>
        <p className="drop-help">Strict schema 0.1 · up to 5,000 messages</p>
      </div>
      {state.kind !== "idle" && (
        <div className={`feedback feedback-${state.kind}`} role="status">
          {state.kind === "validating" ? `Validating and importing ${state.fileName}…` : state.message}
        </div>
      )}
    </section>
  );
}
