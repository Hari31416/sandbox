import { Activity, Box, Cpu, Moon, Sun, Terminal } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { useBackends, useServiceHealth, useServiceReady } from "@/hooks/use-sandbox-queries"
import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"

export function HeaderBar() {
  const health = useServiceHealth()
  const ready = useServiceReady()
  const backends = useBackends()
  const { theme, setTheme } = useTheme()

  const isHealthy = health.isSuccess
  const isReady = ready.isSuccess
  const availableBackends =
    backends.data?.backends.filter((b) => b.available).map((b) => b.name) ?? []

  return (
    <header className="border-b border-border/70 bg-card/40 px-4 py-3 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center border border-primary/30 bg-primary/10 text-primary">
            <Box className="size-4" />
          </div>
          <div>
            <h1 className="font-heading text-sm font-semibold tracking-tight">Sandbox Console</h1>
            <p className="text-[11px] text-muted-foreground">Nexus compute-plane playground</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={isHealthy ? "success" : "danger"}>
            <Activity className="mr-1 size-3" />
            {isHealthy ? "live" : "offline"}
          </Badge>
          <Badge variant={isReady ? "success" : "warning"}>
            <Cpu className="mr-1 size-3" />
            {isReady ? `ready · ${ready.data?.backend}` : "not ready"}
          </Badge>
          {availableBackends.length > 0 && (
            <Badge variant="muted">
              <Terminal className="mr-1 size-3" />
              {availableBackends.join(", ")}
            </Badge>
          )}
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
          </Button>
        </div>
      </div>
    </header>
  )
}
