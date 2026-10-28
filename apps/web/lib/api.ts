import type {
  AlertList,
  Dashboard,
  DeadlineList,
  DigestDetail,
  DigestList,
  DiscoveryList,
  JobList,
  OpportunityDetail,
  OpportunityList,
  SourceDetail,
  SourceHealth,
  SourceRunList,
  SourceSummary,
  SystemStatus,
  UserProfile,
} from "./types";

const API_URL = process.env.INTERNAL_API_URL ?? "http://127.0.0.1:8000";
const API_TOKEN = process.env.INTERNAL_API_TOKEN ?? "dev-owner-token";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

type QueryValue = string | number | boolean | undefined | null;

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = new URL(`/v1${path}`, API_URL);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

async function request(path: string, init: RequestInit): Promise<Response> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${API_TOKEN}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let code = "http_error";
    let message = `API request failed with ${response.status}`;
    try {
      const payload = (await response.json()) as { code?: string; message?: string };
      code = payload.code ?? code;
      message = payload.message ?? message;
    } catch {
      // Keep the status-based fallback.
    }
    throw new ApiError(response.status, code, message);
  }
  return response;
}

export async function apiGet<T>(
  path: string,
  query?: Record<string, QueryValue>,
): Promise<T> {
  const response = await request(buildUrl(path, query), { method: "GET" });
  return (await response.json()) as T;
}

export async function apiSend<T>(
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body?: unknown,
): Promise<T> {
  const response = await request(buildUrl(path), {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return (await response.json()) as T;
}

export async function apiDownload(
  path: string,
  query?: Record<string, QueryValue>,
): Promise<Response> {
  return request(buildUrl(path, query), { method: "GET" });
}

export const api = {
  dashboard: () => apiGet<Dashboard>("/dashboard"),
  opportunities: (query: Record<string, QueryValue>) =>
    apiGet<OpportunityList>("/opportunities", query),
  opportunity: (id: string) => apiGet<OpportunityDetail>(`/opportunities/${id}`),
  brief: (id: string) => apiGet<{ markdown: string }>(`/opportunities/${id}/brief`),
  deadlines: (horizonDays: number) =>
    apiGet<DeadlineList>("/deadlines", { horizon_days: horizonDays }),
  digests: (kind?: string) => apiGet<DigestList>("/digests", { kind }),
  digest: (id: string) => apiGet<DigestDetail>(`/digests/${id}`),
  sources: () => apiGet<{ items: SourceSummary[] }>("/sources"),
  source: (id: string) => apiGet<SourceDetail>(`/sources/${id}`),
  sourceRuns: (id: string) => apiGet<SourceRunList>(`/sources/${id}/runs`),
  profile: () => apiGet<UserProfile>("/profile"),
  discovery: (status?: string) =>
    apiGet<DiscoveryList>("/discovery/candidates", { status }),
  alerts: () => apiGet<AlertList>("/alerts"),
  jobs: () => apiGet<JobList>("/admin/jobs"),
  sourceHealth: () => apiGet<SourceHealth>("/health/sources"),
  systemStatus: () => apiGet<SystemStatus>("/system/status"),
};
