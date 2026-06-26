import { useMemo } from "react"

import { createSandboxClient } from "@/api/client"
import { useSandboxStore } from "@/store/sandbox-store"

export function useSandboxClient() {
  const baseUrl = useSandboxStore((s) => s.baseUrl)
  const authToken = useSandboxStore((s) => s.authToken)

  return useMemo(
    () => createSandboxClient(baseUrl, authToken || undefined),
    [baseUrl, authToken],
  )
}
