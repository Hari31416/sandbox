import { RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useSandboxStore } from "@/store/sandbox-store"

export function ConnectionPanel() {
  const baseUrl = useSandboxStore((s) => s.baseUrl)
  const authToken = useSandboxStore((s) => s.authToken)
  const setBaseUrl = useSandboxStore((s) => s.setBaseUrl)
  const setAuthToken = useSandboxStore((s) => s.setAuthToken)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Connection</CardTitle>
        <CardDescription>Defaults to Vite proxy at /api → :8787</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="base-url">API base URL</Label>
          <Input
            id="base-url"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="/api"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="auth-token">Bearer token (optional)</Label>
          <Input
            id="auth-token"
            type="password"
            value={authToken}
            onChange={(e) => setAuthToken(e.target.value)}
            placeholder="SANDBOX_AUTH_TOKEN"
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={() => window.location.reload()}
        >
          <RefreshCw className="size-3.5" />
          Reconnect
        </Button>
      </CardContent>
    </Card>
  )
}
