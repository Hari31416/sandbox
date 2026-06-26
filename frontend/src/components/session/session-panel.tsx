import { useState } from "react"
import { Camera, Loader2, Plus, Trash2 } from "lucide-react"

import type { Session } from "@/api/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  useBackends,
  useCreateSession,
  useCreateSnapshot,
  useDeleteSession,
  useSessions,
  useSnapshots,
  useStopSession,
} from "@/hooks/use-sandbox-queries"
import { cn } from "@/lib/utils"
import { useSandboxStore } from "@/store/sandbox-store"

function statusVariant(status: Session["status"]) {
  switch (status) {
    case "active":
      return "success" as const
    case "stopped":
    case "expired":
      return "muted" as const
    default:
      return "warning" as const
  }
}

export function SessionPanel() {
  const workspaceId = useSandboxStore((s) => s.workspaceId)
  const runId = useSandboxStore((s) => s.runId)
  const image = useSandboxStore((s) => s.image)
  const backend = useSandboxStore((s) => s.backend)
  const network = useSandboxStore((s) => s.network)
  const memoryMb = useSandboxStore((s) => s.memoryMb)
  const activeSessionId = useSandboxStore((s) => s.activeSessionId)
  const setWorkspaceId = useSandboxStore((s) => s.setWorkspaceId)
  const setRunId = useSandboxStore((s) => s.setRunId)
  const setImage = useSandboxStore((s) => s.setImage)
  const setBackend = useSandboxStore((s) => s.setBackend)
  const setNetwork = useSandboxStore((s) => s.setNetwork)
  const setMemoryMb = useSandboxStore((s) => s.setMemoryMb)
  const setActiveSessionId = useSandboxStore((s) => s.setActiveSessionId)

  const sessions = useSessions()
  const snapshots = useSnapshots()
  const backends = useBackends()
  const createSession = useCreateSession()
  const createSnapshot = useCreateSnapshot()
  const stopSession = useStopSession()
  const deleteSession = useDeleteSession()

  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string>("")

  const supportsSnapshots = backends.data?.backends.some(
    (b) => b.name === "microsandbox" && b.supports_snapshots,
  )

  const handleCreate = () => {
    createSession.mutate({
      workspace_id: workspaceId,
      run_id: runId || `run_${Date.now()}`,
      image: selectedSnapshotId ? undefined : image,
      backend: selectedSnapshotId ? "microsandbox" : backend,
      snapshot_id: selectedSnapshotId || undefined,
      limits: {
        memory_mb: memoryMb,
        network,
        cpu: 1,
        disk_mb: 2048,
        timeout_seconds: 300,
      },
      metadata: { purpose: selectedSnapshotId ? "snapshot_restore" : "sandbox_console" },
    })
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>New session</CardTitle>
          <CardDescription>Spin up an isolated workspace</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Workspace ID</Label>
              <Input value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Run ID</Label>
              <Input value={runId} onChange={(e) => setRunId(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Image</Label>
              <Input
                value={image}
                onChange={(e) => setImage(e.target.value)}
                disabled={Boolean(selectedSnapshotId)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Memory (MB)</Label>
              <Input
                type="number"
                value={memoryMb}
                onChange={(e) => setMemoryMb(Number(e.target.value) || 512)}
              />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Backend</Label>
              <select
                className="flex h-8 w-full border border-input bg-background/80 px-2.5 text-xs outline-none"
                value={backend}
                onChange={(e) => setBackend(e.target.value as typeof backend)}
              >
                <option value="local">local (dev)</option>
                <option value="microsandbox">microsandbox (microVM)</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label>Network</Label>
              <select
                className="flex h-8 w-full border border-input bg-background/80 px-2.5 text-xs outline-none"
                value={network}
                onChange={(e) => setNetwork(e.target.value as typeof network)}
              >
                <option value="disabled">disabled</option>
                <option value="public">public</option>
                <option value="allowlist">allowlist</option>
              </select>
            </div>
          </div>
          {supportsSnapshots && (snapshots.data?.length ?? 0) > 0 && (
            <div className="space-y-1.5">
              <Label>Restore from snapshot (optional)</Label>
              <select
                className="flex h-8 w-full border border-input bg-background/80 px-2.5 text-xs outline-none"
                value={selectedSnapshotId}
                onChange={(e) => setSelectedSnapshotId(e.target.value)}
              >
                <option value="">None — use image above</option>
                {(snapshots.data ?? []).map((snap) => (
                  <option key={snap.id} value={snap.id}>
                    {snap.name} ({snap.image_ref})
                  </option>
                ))}
              </select>
            </div>
          )}
          <Button className="w-full" onClick={handleCreate} disabled={createSession.isPending}>
            {createSession.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Plus className="size-3.5" />
            )}
            Create session
          </Button>
          {createSession.isError && (
            <p className="text-xs text-destructive">{createSession.error.message}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sessions</CardTitle>
          <CardDescription>
            {sessions.isLoading ? "Loading…" : `${sessions.data?.length ?? 0} in workspace`}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {(sessions.data ?? []).map((session) => (
            <div
              key={session.id}
              className={cn(
                "border p-3 transition-colors",
                activeSessionId === session.id
                  ? "border-primary/50 bg-primary/5"
                  : "border-border/70 hover:bg-muted/30",
              )}
            >
              <button
                type="button"
                className="w-full text-left"
                onClick={() => setActiveSessionId(session.id)}
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-[11px]">{session.id}</span>
                  <Badge variant={statusVariant(session.status)}>{session.status}</Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {session.backend} · {session.image}
                </p>
              </button>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="xs"
                  disabled={stopSession.isPending || session.status !== "active"}
                  onClick={() => stopSession.mutate(session.id)}
                >
                  Stop
                </Button>
                {supportsSnapshots &&
                  session.backend === "microsandbox" &&
                  (session.status === "stopped" || session.status === "expired") && (
                    <Button
                      variant="outline"
                      size="xs"
                      disabled={createSnapshot.isPending}
                      onClick={() =>
                        createSnapshot.mutate({
                          sessionId: session.id,
                          stopSession: false,
                        })
                      }
                    >
                      {createSnapshot.isPending ? (
                        <Loader2 className="size-3 animate-spin" />
                      ) : (
                        <Camera className="size-3" />
                      )}
                      Save snapshot
                    </Button>
                  )}
                {supportsSnapshots &&
                  session.backend === "microsandbox" &&
                  session.status === "active" && (
                    <Button
                      variant="outline"
                      size="xs"
                      disabled={createSnapshot.isPending}
                      onClick={() =>
                        createSnapshot.mutate({
                          sessionId: session.id,
                          stopSession: true,
                        })
                      }
                    >
                      {createSnapshot.isPending ? (
                        <Loader2 className="size-3 animate-spin" />
                      ) : (
                        <Camera className="size-3" />
                      )}
                      Stop & snapshot
                    </Button>
                  )}
                <Button
                  variant="destructive"
                  size="xs"
                  disabled={deleteSession.isPending}
                  onClick={() => deleteSession.mutate(session.id)}
                >
                  <Trash2 className="size-3" />
                  Delete
                </Button>
              </div>
            </div>
          ))}
          {!sessions.isLoading && (sessions.data?.length ?? 0) === 0 && (
            <p className="py-6 text-center text-xs text-muted-foreground">
              No sessions yet. Create one to start testing.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
