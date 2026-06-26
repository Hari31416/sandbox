import { create } from "zustand"
import { persist } from "zustand/middleware"

import type { BackendName, NetworkMode } from "@/api/types"

interface SandboxStore {
  baseUrl: string
  authToken: string
  workspaceId: string
  runId: string
  image: string
  backend: BackendName
  network: NetworkMode
  memoryMb: number
  activeSessionId: string | null
  setBaseUrl: (baseUrl: string) => void
  setAuthToken: (authToken: string) => void
  setWorkspaceId: (workspaceId: string) => void
  setRunId: (runId: string) => void
  setImage: (image: string) => void
  setBackend: (backend: BackendName) => void
  setNetwork: (network: NetworkMode) => void
  setMemoryMb: (memoryMb: number) => void
  setActiveSessionId: (sessionId: string | null) => void
}

export const useSandboxStore = create<SandboxStore>()(
  persist(
    (set) => ({
      baseUrl: "/api",
      authToken: "",
      workspaceId: "ws_demo",
      runId: `run_${Date.now()}`,
      image: "python:3.12",
      backend: "local",
      network: "disabled",
      memoryMb: 1024,
      activeSessionId: null,
      setBaseUrl: (baseUrl) => set({ baseUrl }),
      setAuthToken: (authToken) => set({ authToken }),
      setWorkspaceId: (workspaceId) => set({ workspaceId }),
      setRunId: (runId) => set({ runId }),
      setImage: (image) => set({ image }),
      setBackend: (backend) => set({ backend }),
      setNetwork: (network) => set({ network }),
      setMemoryMb: (memoryMb) => set({ memoryMb }),
      setActiveSessionId: (activeSessionId) => set({ activeSessionId }),
    }),
    {
      name: "nexus-sandbox-console",
      partialize: (state) => ({
        baseUrl: state.baseUrl,
        authToken: state.authToken,
        workspaceId: state.workspaceId,
        image: state.image,
        backend: state.backend,
        network: state.network,
        memoryMb: state.memoryMb,
      }),
    },
  ),
)
