import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

import { ArtifactsPanel } from "@/components/artifacts/artifacts-panel"
import { ConnectionPanel } from "@/components/connection/connection-panel"
import { ExecPanel } from "@/components/exec/exec-panel"
import { FilesPanel } from "@/components/files/files-panel"
import { HeaderBar } from "@/components/layout/header-bar"
import { SessionPanel } from "@/components/session/session-panel"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useSession } from "@/hooks/use-sandbox-queries"
import { useSandboxStore } from "@/store/sandbox-store"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2_000,
      retry: 1,
    },
  },
})

function WorkspaceMain() {
  const activeSessionId = useSandboxStore((s) => s.activeSessionId)
  const session = useSession(activeSessionId)

  return (
    <main className="mx-auto grid max-w-[1600px] gap-4 p-4 lg:grid-cols-[320px_1fr]">
      <aside className="space-y-4">
        <ConnectionPanel />
        <SessionPanel />
      </aside>

      <section className="min-w-0 space-y-4">
        {activeSessionId && session.data && (
          <div className="border border-border/70 bg-card/30 px-4 py-3 text-[11px] text-muted-foreground backdrop-blur-sm">
            <span className="text-foreground">Active session</span>
            <span className="mx-2 text-border">|</span>
            <span className="font-mono">{session.data.id}</span>
            <span className="mx-2 text-border">|</span>
            <span>{session.data.backend}</span>
            <span className="mx-2 text-border">|</span>
            <span>expires {new Date(session.data.expires_at).toLocaleString()}</span>
          </div>
        )}

        <Tabs defaultValue="exec">
          <TabsList>
            <TabsTrigger value="exec">Execute</TabsTrigger>
            <TabsTrigger value="files">Files</TabsTrigger>
            <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
          </TabsList>
          <TabsContent value="exec">
            <ExecPanel />
          </TabsContent>
          <TabsContent value="files">
            <FilesPanel />
          </TabsContent>
          <TabsContent value="artifacts">
            <ArtifactsPanel />
          </TabsContent>
        </Tabs>
      </section>
    </main>
  )
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="sandbox-console relative min-h-svh">
        <div className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(ellipse_at_top_left,rgba(16,185,129,0.08),transparent_50%),radial-gradient(ellipse_at_bottom_right,rgba(59,130,246,0.06),transparent_45%)]" />
        <div className="pointer-events-none fixed inset-0 -z-10 opacity-[0.35] [background-image:linear-gradient(rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] [background-size:32px_32px]" />
        <HeaderBar />
        <WorkspaceMain />
      </div>
    </QueryClientProvider>
  )
}

export default App
