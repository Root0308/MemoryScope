export const configuredBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export const apiBaseUrl = configuredBaseUrl.replace(/\/$/, "");

type ErrorPayload = {
  detail?: string | {
    message?: string;
    errors?: Array<{
      loc?: Array<string | number>;
      msg?: string;
      path?: string;
      message?: string;
    }>;
  };
};

export async function apiError(response: Response): Promise<Error> {
  let message = `Request failed with status ${response.status}`;
  try {
    const payload = (await response.json()) as ErrorPayload;
    if (typeof payload.detail === "string") {
      message = payload.detail;
    } else if (payload.detail?.message) {
      const firstIssue = payload.detail.errors?.[0];
      const location = firstIssue?.path ?? firstIssue?.loc?.join(" → ");
      const issueMessage = firstIssue?.message ?? firstIssue?.msg;
      message = payload.detail.message;
      if (issueMessage) {
        message += `: ${location ? `${location}: ` : ""}${issueMessage}`;
      }
    }
  } catch {
    // Keep the status-based fallback for non-JSON error responses.
  }
  return new Error(message);
}
