import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import type { CreateSessionRequest } from "@/api/types"
import { useSandboxClient } from "@/hooks/use-sandbox-client"
import { useSandboxStore } from "@/store/sandbox-store"

export function useServiceHealth() {
  const client = useSandboxClient()
  return useQuery({
    queryKey: ["sandbox", "health"],
    queryFn: () => client.health(),
    refetchInterval: 10_000,
    retry: 1,
  })
}

export function useServiceReady() {
  const client = useSandboxClient()
  return useQuery({
    queryKey: ["sandbox", "ready"],
    queryFn: () => client.ready(),
    refetchInterval: 10_000,
    retry: 1,
  })
}

export function useBackends() {
  const client = useSandboxClient()
  return useQuery({
    queryKey: ["sandbox", "backends"],
    queryFn: () => client.backends(),
    refetchInterval: 30_000,
  })
}

export function useSessions() {
  const client = useSandboxClient()
  const workspaceId = useSandboxStore((s) => s.workspaceId)
  return useQuery({
    queryKey: ["sandbox", "sessions", workspaceId],
    queryFn: () => client.listSessions({ workspace_id: workspaceId }),
    refetchInterval: 5_000,
  })
}

export function useSession(sessionId: string | null) {
  const client = useSandboxClient()
  return useQuery({
    queryKey: ["sandbox", "session", sessionId],
    queryFn: () => client.getSession(sessionId!),
    enabled: Boolean(sessionId),
    refetchInterval: 5_000,
  })
}

export function useSessionFiles(sessionId: string | null) {
  const client = useSandboxClient()
  return useQuery({
    queryKey: ["sandbox", "files", sessionId],
    queryFn: () => client.listFiles(sessionId!),
    enabled: Boolean(sessionId),
  })
}

export function useSessionArtifacts(sessionId: string | null) {
  const client = useSandboxClient()
  return useQuery({
    queryKey: ["sandbox", "artifacts", sessionId],
    queryFn: () => client.listArtifacts(sessionId!),
    enabled: Boolean(sessionId),
  })
}

export function useCreateSession() {
  const client = useSandboxClient()
  const queryClient = useQueryClient()
  const setActiveSessionId = useSandboxStore((s) => s.setActiveSessionId)

  return useMutation({
    mutationFn: (body: CreateSessionRequest) => client.createSession(body),
    onSuccess: (session) => {
      setActiveSessionId(session.id)
      void queryClient.invalidateQueries({ queryKey: ["sandbox", "sessions"] })
    },
  })
}

export function useStopSession() {
  const client = useSandboxClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (sessionId: string) => client.stopSession(sessionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sandbox", "sessions"] })
    },
  })
}

export function useDeleteSession() {
  const client = useSandboxClient()
  const queryClient = useQueryClient()
  const activeSessionId = useSandboxStore((s) => s.activeSessionId)
  const setActiveSessionId = useSandboxStore((s) => s.setActiveSessionId)

  return useMutation({
    mutationFn: (sessionId: string) => client.deleteSession(sessionId),
    onSuccess: (_, sessionId) => {
      if (activeSessionId === sessionId) setActiveSessionId(null)
      void queryClient.invalidateQueries({ queryKey: ["sandbox", "sessions"] })
    },
  })
}

export function useExecCommand() {
  const client = useSandboxClient()
  return useMutation({
    mutationFn: ({
      sessionId,
      command,
      cwd,
      timeoutSeconds,
    }: {
      sessionId: string
      command: string
      cwd?: string
      timeoutSeconds?: number
    }) =>
      client.exec(sessionId, {
        command,
        cwd,
        timeout_seconds: timeoutSeconds,
      }),
  })
}

export function useWriteFile() {
  const client = useSandboxClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      sessionId,
      path,
      content,
    }: {
      sessionId: string
      path: string
      content: string
    }) => {
      const encoded = btoa(unescape(encodeURIComponent(content)))
      return client.writeFile(sessionId, path, encoded)
    },
    onSuccess: (_, { sessionId }) => {
      void queryClient.invalidateQueries({ queryKey: ["sandbox", "files", sessionId] })
    },
  })
}

export function useSyncArtifacts() {
  const client = useSandboxClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      sessionId,
      paths,
      destinationPrefix,
    }: {
      sessionId: string
      paths: string[]
      destinationPrefix: string
    }) => client.syncArtifacts(sessionId, { paths, destination_prefix: destinationPrefix }),
    onSuccess: (_, { sessionId }) => {
      void queryClient.invalidateQueries({ queryKey: ["sandbox", "artifacts", sessionId] })
    },
  })
}

export function useSnapshots() {
  const client = useSandboxClient()
  const workspaceId = useSandboxStore((s) => s.workspaceId)
  return useQuery({
    queryKey: ["sandbox", "snapshots", workspaceId],
    queryFn: () => client.listSnapshots(workspaceId),
    refetchInterval: 10_000,
  })
}

export function useCreateSnapshot() {
  const client = useSandboxClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      sessionId,
      name,
      stopSession,
      includeWorkspace,
    }: {
      sessionId: string
      name?: string
      stopSession?: boolean
      includeWorkspace?: boolean
    }) =>
      client.createSnapshot(sessionId, {
        name,
        stop_session: stopSession,
        include_workspace: includeWorkspace,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sandbox", "snapshots"] })
      void queryClient.invalidateQueries({ queryKey: ["sandbox", "sessions"] })
    },
  })
}

export function useDeleteSnapshot() {
  const client = useSandboxClient()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (snapshotId: string) => client.deleteSnapshot(snapshotId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sandbox", "snapshots"] })
    },
  })
}

export function useRestoreSnapshot() {
  const client = useSandboxClient()
  const queryClient = useQueryClient()
  const setActiveSessionId = useSandboxStore((s) => s.setActiveSessionId)
  const workspaceId = useSandboxStore((s) => s.workspaceId)
  const memoryMb = useSandboxStore((s) => s.memoryMb)
  const network = useSandboxStore((s) => s.network)

  return useMutation({
    mutationFn: (snapshotId: string) =>
      client.createSession({
        workspace_id: workspaceId,
        run_id: `run_${Date.now()}`,
        backend: "microsandbox",
        snapshot_id: snapshotId,
        limits: {
          memory_mb: memoryMb,
          network,
          cpu: 1,
          disk_mb: 2048,
          timeout_seconds: 300,
        },
        metadata: { purpose: "snapshot_restore" },
      }),
    onSuccess: (session) => {
      setActiveSessionId(session.id)
      void queryClient.invalidateQueries({ queryKey: ["sandbox", "sessions"] })
    },
  })
}
