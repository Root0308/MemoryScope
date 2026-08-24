import type { HealthResponse } from "../types/health";
import { apiBaseUrl } from "./client";


export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(apiBaseUrl + "/api/v1/health", { signal });

  if (!response.ok) {
    throw new Error("Health request failed with status " + response.status);
  }

  return (await response.json()) as HealthResponse;
}
