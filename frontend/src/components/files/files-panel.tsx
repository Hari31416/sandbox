import { useState } from "react"
import { FileCode, FolderOpen, Loader2, Upload } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useSandboxClient } from "@/hooks/use-sandbox-client"
import { useSessionFiles, useWriteFile } from "@/hooks/use-sandbox-queries"
import { useSandboxStore } from "@/store/sandbox-store"

const SAMPLE_SCRIPT = `print("hello from sandbox")
with open("output.txt", "w") as f:
    f.write("done\\n")
`

export function FilesPanel() {
  const activeSessionId = useSandboxStore((s) => s.activeSessionId)
  const client = useSandboxClient()
  const files = useSessionFiles(activeSessionId)
  const writeFile = useWriteFile()

  const [filePath, setFilePath] = useState("/workspace/main.py")
  const [fileContent, setFileContent] = useState(SAMPLE_SCRIPT)
  const [readPath, setReadPath] = useState("/workspace/main.py")
  const [readContent, setReadContent] = useState("")

  const handleWrite = () => {
    if (!activeSessionId) return
    writeFile.mutate({
      sessionId: activeSessionId,
      path: filePath,
      content: fileContent,
    })
  }

  const handleRead = async () => {
    if (!activeSessionId) return
    try {
      const content = await client.readFile(activeSessionId, readPath)
      setReadContent(content)
    } catch (error) {
      setReadContent(error instanceof Error ? error.message : "Read failed")
    }
  }

  if (!activeSessionId) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          Select a session to manage files.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Write file</CardTitle>
            <CardDescription>PUT /v1/sessions/…/files</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label>Path</Label>
              <Input value={filePath} onChange={(e) => setFilePath(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Content</Label>
              <Textarea
                value={fileContent}
                onChange={(e) => setFileContent(e.target.value)}
                rows={10}
              />
            </div>
            <Button onClick={handleWrite} disabled={writeFile.isPending}>
              {writeFile.isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Upload className="size-3.5" />
              )}
              Write to sandbox
            </Button>
            {writeFile.isSuccess && (
              <p className="text-xs text-emerald-500">File written successfully.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Read file</CardTitle>
            <CardDescription>GET /v1/sessions/…/files</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label>Path</Label>
              <Input value={readPath} onChange={(e) => setReadPath(e.target.value)} />
            </div>
            <Button variant="outline" onClick={handleRead}>
              <FileCode className="size-3.5" />
              Read file
            </Button>
            <pre className="max-h-64 overflow-auto border border-border/70 bg-[#0b0f14] p-3 font-mono text-[11px] text-slate-200">
              {readContent || "—"}
            </pre>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Workspace files</CardTitle>
            <CardDescription>
              <FolderOpen className="mr-1 inline size-3" />
              {files.data?.length ?? 0} entries
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => files.refetch()}>
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          <div className="max-h-64 overflow-auto border border-border/60">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Path</th>
                  <th className="px-3 py-2 font-medium">Size</th>
                  <th className="px-3 py-2 font-medium">Type</th>
                </tr>
              </thead>
              <tbody>
                {(files.data ?? []).map((file) => (
                  <tr key={file.path} className="border-t border-border/40 hover:bg-muted/20">
                    <td className="px-3 py-2 font-mono">{file.path}</td>
                    <td className="px-3 py-2 text-muted-foreground">{file.size_bytes} B</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {file.is_dir ? "dir" : "file"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!files.isLoading && (files.data?.length ?? 0) === 0 && (
              <p className="p-6 text-center text-muted-foreground">No files in workspace yet.</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
