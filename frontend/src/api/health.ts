import type { HealthResponse } from "../types/health";


const configuredBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const apiBaseUrl = configuredBaseUrl.replace(/\/$/, "");


export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(apiBaseUrl + "/api/v1/health", { signal });

  if (!response.ok) {
    throw new Error("Health request failed with status " + response.status);
  }

  return (await response.json()) as HealthResponse;
}
