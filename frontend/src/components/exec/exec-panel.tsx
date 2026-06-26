import { useState } from "react"
import { Loader2, Play, RefreshCw } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useSandboxClient } from "@/hooks/use-sandbox-client"
import { useExecCommand } from "@/hooks/use-sandbox-queries"
import { useSandboxStore } from "@/store/sandbox-store"
import { cn } from "@/lib/utils"

const PRESETS = [
  { label: "Hello Python", command: "python -c \"print('hello from sandbox')\"" },
  { label: "List workspace", command: "ls -la" },
  { label: "Python version", command: "python --version" },
  { label: "Run main.py", command: "python main.py" },
]

export function ExecPanel() {
  const activeSessionId = useSandboxStore((s) => s.activeSessionId)
  const client = useSandboxClient()
  const execCommand = useExecCommand()

  const [command, setCommand] = useState("python -c \"print('hello from sandbox')\"")
  const [cwd, setCwd] = useState("/workspace")
  const [timeout, setTimeout] = useState(60)
  const [stdout, setStdout] = useState("")
  const [stderr, setStderr] = useState("")
  const [lastResult, setLastResult] = useState<{
    exitCode: number | null
    status: string
    execId: string
  } | null>(null)

  const run = async () => {
    if (!activeSessionId) return
    setStdout("")
    setStderr("")
    try {
      const result = await execCommand.mutateAsync({
        sessionId: activeSessionId,
        command,
        cwd,
        timeoutSeconds: timeout,
      })
      const [out, err] = await Promise.all([
        client.getExecStdout(activeSessionId, result.id),
        client.getExecStderr(activeSessionId, result.id),
      ])
      setStdout(out)
      setStderr(err)
      setLastResult({
        exitCode: result.exit_code,
        status: result.status,
        execId: result.id,
      })
    } catch (error) {
      setStderr(error instanceof Error ? error.message : "Execution failed")
    }
  }

  if (!activeSessionId) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          Select or create a session to run commands.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Execute</CardTitle>
          <CardDescription className="font-mono">{activeSessionId}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((preset) => (
              <Button
                key={preset.label}
                variant="outline"
                size="xs"
                onClick={() => setCommand(preset.command)}
              >
                {preset.label}
              </Button>
            ))}
          </div>
          <div className="space-y-1.5">
            <Label>Command</Label>
            <Textarea value={command} onChange={(e) => setCommand(e.target.value)} rows={3} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Working directory</Label>
              <Input value={cwd} onChange={(e) => setCwd(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Timeout (seconds)</Label>
              <Input
                type="number"
                value={timeout}
                onChange={(e) => setTimeout(Number(e.target.value) || 30)}
              />
            </div>
          </div>
          <Button onClick={run} disabled={execCommand.isPending} className="w-full sm:w-auto">
            {execCommand.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Play className="size-3.5" />
            )}
            Run command
          </Button>
          {lastResult && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant={lastResult.exitCode === 0 ? "success" : "danger"}>
                exit {lastResult.exitCode ?? "?"}
              </Badge>
              <Badge variant="muted">{lastResult.status}</Badge>
              <span className="font-mono text-muted-foreground">{lastResult.execId}</span>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <TerminalOutput title="stdout" content={stdout} accent="emerald" />
        <TerminalOutput title="stderr" content={stderr} accent="amber" />
      </div>
    </div>
  )
}

function TerminalOutput({
  title,
  content,
  accent,
}: {
  title: string
  content: string
  accent: "emerald" | "amber"
}) {
  const accentClass = accent === "emerald" ? "text-emerald-400" : "text-amber-400"

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between py-2">
        <CardTitle className={cn("text-xs uppercase", accentClass)}>{title}</CardTitle>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={() => navigator.clipboard.writeText(content)}
          disabled={!content}
        >
          <RefreshCw className="size-3" />
        </Button>
      </CardHeader>
      <CardContent className="p-0">
        <pre className="max-h-80 overflow-auto bg-[#0b0f14] p-4 font-mono text-[11px] leading-relaxed text-slate-200">
          {content || <span className="text-slate-500">—</span>}
        </pre>
      </CardContent>
    </Card>
  )
}
