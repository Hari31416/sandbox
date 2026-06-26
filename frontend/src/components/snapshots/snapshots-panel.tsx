import { Camera, Loader2, RotateCcw, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  useBackends,
  useDeleteSnapshot,
  useRestoreSnapshot,
  useSnapshots,
} from "@/hooks/use-sandbox-queries"

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function SnapshotsPanel() {
  const backends = useBackends()
  const snapshots = useSnapshots()
  const restoreSnapshot = useRestoreSnapshot()
  const deleteSnapshot = useDeleteSnapshot()

  const supportsSnapshots = backends.data?.backends.some(
    (b) => b.name === "microsandbox" && b.supports_snapshots,
  )

  if (backends.isLoading) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          Loading backend capabilities…
        </CardContent>
      </Card>
    )
  }

  if (!supportsSnapshots) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          Snapshots require the microsandbox backend to be installed and available.
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Camera className="size-4" />
          Workspace snapshots
        </CardTitle>
        <CardDescription>
          {snapshots.isLoading
            ? "Loading…"
            : `${snapshots.data?.length ?? 0} saved VM disk state(s)`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {(snapshots.data ?? []).map((snapshot) => (
          <div key={snapshot.id} className="border border-border/60 p-3 text-[11px]">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium text-foreground">{snapshot.name}</p>
                <p className="mt-1 text-muted-foreground">{snapshot.image_ref}</p>
                <p className="mt-1 font-mono text-muted-foreground">
                  {snapshot.digest.slice(0, 16)}…
                </p>
                <p className="mt-1 text-muted-foreground">
                  {formatBytes(snapshot.size_bytes)} ·{" "}
                  {new Date(snapshot.created_at).toLocaleString()}
                </p>
                {snapshot.source_session_id && (
                  <p className="mt-1 truncate font-mono text-muted-foreground">
                    from {snapshot.source_session_id}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 gap-1">
                <Button
                  variant="outline"
                  size="xs"
                  disabled={restoreSnapshot.isPending}
                  onClick={() => restoreSnapshot.mutate(snapshot.id)}
                >
                  {restoreSnapshot.isPending ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <RotateCcw className="size-3" />
                  )}
                  Restore
                </Button>
                <Button
                  variant="destructive"
                  size="xs"
                  disabled={deleteSnapshot.isPending}
                  onClick={() => {
                    if (window.confirm(`Delete snapshot "${snapshot.name}"?`)) {
                      deleteSnapshot.mutate(snapshot.id)
                    }
                  }}
                >
                  <Trash2 className="size-3" />
                </Button>
              </div>
            </div>
          </div>
        ))}
        {!snapshots.isLoading && (snapshots.data?.length ?? 0) === 0 && (
          <p className="py-6 text-center text-muted-foreground">
            No snapshots yet. Save one from a stopped microsandbox session.
          </p>
        )}
        {restoreSnapshot.isError && (
          <p className="text-xs text-destructive">{restoreSnapshot.error.message}</p>
        )}
      </CardContent>
    </Card>
  )
}
