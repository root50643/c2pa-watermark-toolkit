import type {
  BinaryResult,
  Capabilities,
  Customer,
  IdentifyResult,
  JobAccepted,
  JobStatus
} from "./types";

export const API_KEY_SESSION_KEY = "raiw_api_key";
export const JOBS_SESSION_KEY = "raiw_jobs";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly requestId: string | null,
    public readonly details: unknown = null
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function authHeaders(apiKey?: string | null): HeadersInit {
  return apiKey ? { "X-API-Key": apiKey } : {};
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  const headerRequestId = response.headers.get("X-Request-ID");
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string; details?: unknown; request_id?: string };
    };
    return new ApiError(
      body.error?.message ?? response.statusText ?? "Request failed",
      response.status,
      body.error?.code ?? "request_failed",
      body.error?.request_id ?? headerRequestId,
      body.error?.details
    );
  } catch {
    return new ApiError(response.statusText || "Request failed", response.status, "request_failed", headerRequestId);
  }
}

async function jsonRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) throw await errorFromResponse(response);
  return (await response.json()) as T;
}

export function getCapabilities() {
  return jsonRequest<Capabilities>("/api/v1/capabilities");
}

export function getReady() {
  return jsonRequest<{ status: string; archive: boolean; database: boolean }>("/readyz");
}

export function authenticate(apiKey?: string | null) {
  return jsonRequest<Customer>("/api/v1/me", { headers: authHeaders(apiKey) });
}

function createForm(file: File, fields: Record<string, string | number | boolean | null | undefined> = {}) {
  const form = new FormData();
  form.append("file", file, file.name);
  for (const [key, value] of Object.entries(fields)) {
    if (value !== null && value !== undefined && value !== "") form.append(key, String(value));
  }
  return form;
}

export async function identify(file: File, apiKey?: string | null): Promise<IdentifyResult> {
  return jsonRequest<IdentifyResult>("/api/v1/identify", {
    method: "POST",
    headers: authHeaders(apiKey),
    body: createForm(file)
  });
}

function responseFilename(response: Response) {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) return decodeURIComponent(encoded);
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? "processed-image";
}

export async function processBinary(
  path: "/api/v1/remove/visible" | "/api/v1/remove/erase" | "/api/v1/remove/metadata",
  file: File,
  apiKey: string | null | undefined,
  fields: Record<string, string | number | boolean | null | undefined>
): Promise<BinaryResult> {
  const response = await fetch(path, {
    method: "POST",
    headers: authHeaders(apiKey),
    body: createForm(file, fields)
  });
  if (!response.ok) throw await errorFromResponse(response);
  return {
    blob: await response.blob(),
    filename: responseFilename(response),
    requestId: response.headers.get("X-Request-ID"),
    archiveId: response.headers.get("X-Archive-ID"),
    removedMarks: response.headers.get("X-Removed-Marks")
  };
}

export async function submitGpuJob(
  task: "invisible" | "all",
  file: File,
  apiKey: string | null | undefined,
  fields: Record<string, string | number | boolean | null | undefined>
) {
  return jsonRequest<JobAccepted>(`/api/v1/jobs/${task}`, {
    method: "POST",
    headers: authHeaders(apiKey),
    body: createForm(file, fields)
  });
}

export function getJob(jobId: string, apiKey?: string | null) {
  return jsonRequest<JobStatus>(`/api/v1/jobs/${encodeURIComponent(jobId)}`, {
    headers: authHeaders(apiKey)
  });
}

export async function downloadJobResult(jobId: string, apiKey?: string | null): Promise<BinaryResult> {
  const response = await fetch(`/api/v1/jobs/${encodeURIComponent(jobId)}/result`, {
    headers: authHeaders(apiKey)
  });
  if (!response.ok) throw await errorFromResponse(response);
  return {
    blob: await response.blob(),
    filename: responseFilename(response),
    requestId: response.headers.get("X-Request-ID"),
    archiveId: null,
    removedMarks: null
  };
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
