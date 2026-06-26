import type {
  ArtifactInfo,
  BackendsResponse,
  CreateSessionRequest,
  CreateSnapshotRequest,
  ExecResult,
  FileInfo,
  FileListEntry,
  HealthResponse,
  ReadyResponse,
  Session,
  Snapshot,
} from "./types"

export class SandboxApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "SandboxApiError"
    this.status = status
  }
}

function buildHeaders(authToken?: string): HeadersInit {
  const headers: HeadersInit = { "Content-Type": "application/json" }
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`
  }
  return headers
}

async function request<T>(
  baseUrl: string,
  path: string,
  init: RequestInit = {},
  authToken?: string,
): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      ...buildHeaders(authToken),
      ...init.headers,
    },
  })

  if (!response.ok) {
    let message = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // ignore parse errors
    }
    throw new SandboxApiError(message, response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function createSandboxClient(baseUrl: string, authToken?: string) {
  const auth = authToken

  return {
    health: () => request<HealthResponse>(baseUrl, "/healthz", {}, auth),
    ready: () => request<ReadyResponse>(baseUrl, "/readyz", {}, auth),
    backends: () => request<BackendsResponse>(baseUrl, "/v1/backends", {}, auth),

    listSessions: (params?: { workspace_id?: string; status?: string }) => {
      const query = new URLSearchParams()
      if (params?.workspace_id) query.set("workspace_id", params.workspace_id)
      if (params?.status) query.set("status", params.status)
      const suffix = query.toString() ? `?${query}` : ""
      return request<Session[]>(baseUrl, `/v1/sessions${suffix}`, {}, auth)
    },

    getSession: (sessionId: string) =>
      request<Session>(baseUrl, `/v1/sessions/${sessionId}`, {}, auth),

    createSession: (body: CreateSessionRequest) =>
      request<Session>(baseUrl, "/v1/sessions", {
        method: "POST",
        body: JSON.stringify(body),
      }, auth),

    heartbeat: (sessionId: string, extendSeconds?: number) =>
      request<Session>(baseUrl, `/v1/sessions/${sessionId}/heartbeat`, {
        method: "POST",
        body: JSON.stringify({ extend_seconds: extendSeconds }),
      }, auth),

    stopSession: (sessionId: string) =>
      request<Session>(baseUrl, `/v1/sessions/${sessionId}/stop`, {
        method: "POST",
      }, auth),

    deleteSession: (sessionId: string) =>
      request<void>(baseUrl, `/v1/sessions/${sessionId}`, { method: "DELETE" }, auth),

    exec: (
      sessionId: string,
      body: { command: string; cwd?: string; timeout_seconds?: number; env?: Record<string, string> },
    ) =>
      request<ExecResult>(baseUrl, `/v1/sessions/${sessionId}/execs`, {
        method: "POST",
        body: JSON.stringify(body),
      }, auth),

    getExecStdout: async (sessionId: string, execId: string) => {
      const response = await fetch(`${baseUrl}/v1/sessions/${sessionId}/execs/${execId}/stdout`, {
        headers: auth ? { Authorization: `Bearer ${auth}` } : undefined,
      })
      if (!response.ok) throw new SandboxApiError(response.statusText, response.status)
      return response.text()
    },

    getExecStderr: async (sessionId: string, execId: string) => {
      const response = await fetch(`${baseUrl}/v1/sessions/${sessionId}/execs/${execId}/stderr`, {
        headers: auth ? { Authorization: `Bearer ${auth}` } : undefined,
      })
      if (!response.ok) throw new SandboxApiError(response.statusText, response.status)
      return response.text()
    },

    writeFile: (sessionId: string, path: string, contentBase64: string) =>
      request<FileInfo>(baseUrl, `/v1/sessions/${sessionId}/files`, {
        method: "PUT",
        body: JSON.stringify({ path, content_base64: contentBase64, mode: "0644" }),
      }, auth),

    readFile: async (sessionId: string, path: string) => {
      const response = await fetch(
        `${baseUrl}/v1/sessions/${sessionId}/files?${new URLSearchParams({ path })}`,
        { headers: auth ? { Authorization: `Bearer ${auth}` } : undefined },
      )
      if (!response.ok) throw new SandboxApiError(response.statusText, response.status)
      return response.text()
    },

    listFiles: (sessionId: string, path = "") =>
      request<FileListEntry[]>(
        baseUrl,
        `/v1/sessions/${sessionId}/files/list?${new URLSearchParams({ path })}`,
        {},
        auth,
      ),

    deleteFile: (sessionId: string, path: string) =>
      request<void>(
        baseUrl,
        `/v1/sessions/${sessionId}/files?${new URLSearchParams({ path })}`,
        { method: "DELETE" },
        auth,
      ),

    syncArtifacts: (
      sessionId: string,
      body: { paths: string[]; destination_prefix: string },
    ) =>
      request<ArtifactInfo[]>(baseUrl, `/v1/sessions/${sessionId}/artifacts/sync`, {
        method: "POST",
        body: JSON.stringify({
          ...body,
          include_globs: ["**/*"],
          exclude_globs: [".venv/**", "__pycache__/**"],
        }),
      }, auth),

    listArtifacts: (sessionId: string) =>
      request<ArtifactInfo[]>(baseUrl, `/v1/sessions/${sessionId}/artifacts`, {}, auth),

    runGc: () =>
      request<{ sessions_removed: number; exec_logs_removed: number }>(
        baseUrl,
        "/v1/gc",
        { method: "POST" },
        auth,
      ),

    createSnapshot: (sessionId: string, body?: CreateSnapshotRequest) =>
      request<Snapshot>(baseUrl, `/v1/sessions/${sessionId}/snapshots`, {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      }, auth),

    listSnapshots: (workspaceId: string) =>
      request<Snapshot[]>(
        baseUrl,
        `/v1/snapshots?${new URLSearchParams({ workspace_id: workspaceId })}`,
        {},
        auth,
      ),

    getSnapshot: (snapshotId: string) =>
      request<Snapshot>(baseUrl, `/v1/snapshots/${snapshotId}`, {}, auth),

    deleteSnapshot: (snapshotId: string) =>
      request<void>(baseUrl, `/v1/snapshots/${snapshotId}`, { method: "DELETE" }, auth),
  }
}

export type SandboxClient = ReturnType<typeof createSandboxClient>
