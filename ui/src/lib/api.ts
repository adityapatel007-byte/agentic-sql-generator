import { API_BASE } from "./config";

export type ConnectionKind = "sqlite" | "postgres";

export type ConnectionInfo = {
  connection_id: string;
  kind: ConnectionKind;
  label: string | null;
};

export type ConnectionListResponse = {
  connections: ConnectionInfo[];
};

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) return JSON.stringify(body.detail);
    return JSON.stringify(body);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function listConnections(): Promise<ConnectionListResponse> {
  return request<ConnectionListResponse>("/connections");
}

export async function deleteConnection(id: string): Promise<void> {
  await request<void>(`/connections/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function registerSqlite(
  file: File,
  label?: string,
): Promise<ConnectionInfo> {
  const form = new FormData();
  form.append("file", file);
  if (label) form.append("label", label);
  return request<ConnectionInfo>("/connections/sqlite", {
    method: "POST",
    body: form,
  });
}

export async function registerPostgres(body: {
  conninfo: string;
  label?: string | null;
  include_schemas?: string[];
}): Promise<ConnectionInfo> {
  return request<ConnectionInfo>("/connections/postgres", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

export { ApiError };
