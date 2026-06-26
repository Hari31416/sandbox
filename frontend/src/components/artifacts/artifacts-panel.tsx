import { useState } from "react"
import { Archive, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useSessionArtifacts, useSyncArtifacts } from "@/hooks/use-sandbox-queries"
import { useSandboxStore } from "@/store/sandbox-store"

export function ArtifactsPanel() {
  const activeSessionId = useSandboxStore((s) => s.activeSessionId)
  const runId = useSandboxStore((s) => s.runId)
  const artifacts = useSessionArtifacts(activeSessionId)
  const syncArtifacts = useSyncArtifacts()

  const [paths, setPaths] = useState("/workspace")
  const [destinationPrefix, setDestinationPrefix] = useState(`runs/${runId}/artifacts`)

  const handleSync = () => {
    if (!activeSessionId) return
    syncArtifacts.mutate({
      sessionId: activeSessionId,
      paths: paths.split(",").map((p) => p.trim()).filter(Boolean),
      destinationPrefix,
    })
  }

  if (!activeSessionId) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          Select a session to export artifacts.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Sync artifacts</CardTitle>
          <CardDescription>POST /v1/sessions/…/artifacts/sync</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <Label>Source paths (comma-separated)</Label>
            <Input value={paths} onChange={(e) => setPaths(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Destination prefix</Label>
            <Input
              value={destinationPrefix}
              onChange={(e) => setDestinationPrefix(e.target.value)}
            />
          </div>
          <Button onClick={handleSync} disabled={syncArtifacts.isPending}>
            {syncArtifacts.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Archive className="size-3.5" />
            )}
            Export artifacts
          </Button>
          {syncArtifacts.isSuccess && (
            <p className="text-xs text-emerald-500">
              Exported {syncArtifacts.data?.length ?? 0} artifact(s).
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Exported artifacts</CardTitle>
          <CardDescription>{artifacts.data?.length ?? 0} records</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {(artifacts.data ?? []).map((artifact) => (
            <div key={artifact.id} className="border border-border/60 p-3 text-[11px]">
              <p className="font-mono text-foreground">{artifact.source_path}</p>
              <p className="mt-1 truncate text-muted-foreground">{artifact.artifact_uri}</p>
              <p className="mt-1 text-muted-foreground">
                {artifact.size_bytes} B · {artifact.sha256.slice(0, 12)}…
              </p>
            </div>
          ))}
          {!artifacts.isLoading && (artifacts.data?.length ?? 0) === 0 && (
            <p className="py-6 text-center text-muted-foreground">No artifacts exported yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
