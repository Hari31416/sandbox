export type BackendName = "local" | "microsandbox"
export type SessionStatus = "creating" | "active" | "stopping" | "stopped" | "expired"
export type ExecStatus = "running" | "completed" | "failed" | "timed_out"
export type NetworkMode = "disabled" | "public" | "allowlist"

export interface SessionLimits {
  cpu: number
  memory_mb: number
  disk_mb: number
  timeout_seconds: number
  network: NetworkMode
  allowed_hosts: string[]
}

export interface Session {
  id: string
  workspace_id: string
  run_id: string | null
  image: string
  status: SessionStatus
  backend: BackendName
  root_path: string
  limits: SessionLimits
  metadata: Record<string, unknown>
  created_at: string
  expires_at: string
  last_heartbeat_at: string | null
  stopped_at: string | null
}

export interface CreateSessionRequest {
  workspace_id: string
  run_id?: string | null
  image?: string | null
  backend?: BackendName | null
  snapshot_id?: string | null
  limits?: Partial<SessionLimits>
  metadata?: Record<string, unknown>
}

export interface Snapshot {
  id: string
  workspace_id: string
  source_session_id: string | null
  name: string
  digest: string
  image_ref: string
  size_bytes: number
  metadata: Record<string, unknown>
  created_at: string
}

export interface CreateSnapshotRequest {
  name?: string | null
  metadata?: Record<string, unknown>
  stop_session?: boolean
}

export interface ExecResult {
  id: string
  session_id: string
  command: string
  cwd: string
  status: ExecStatus
  exit_code: number | null
  started_at: string
  finished_at: string | null
  timeout_seconds: number
}

export interface FileInfo {
  path: string
  size_bytes: number
  sha256: string
  updated_at: string
}

export interface FileListEntry {
  path: string
  is_dir: boolean
  size_bytes: number
  updated_at: string
}

export interface ArtifactInfo {
  id: string
  session_id: string
  source_path: string
  artifact_uri: string
  size_bytes: number
  sha256: string
  created_at: string
}

export interface BackendCapabilities {
  name: BackendName
  available: boolean
  supports_network_policy: boolean
  supports_streaming: boolean
  supports_snapshots: boolean
}

export interface BackendsResponse {
  backends: BackendCapabilities[]
  default_backend: BackendName
}

export interface HealthResponse {
  status: string
}

export interface ReadyResponse {
  status: string
  backend: BackendName
  sqlite_ok: boolean
}

export interface ApiError {
  detail?: string
}
