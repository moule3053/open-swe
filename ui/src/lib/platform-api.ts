export type PlatformTask = {
  task_id: string
  thread_id: string
  title: string | null
  prompt: string | null
  repo: string | null
  base_ref: string | null
  agent_type: string
  status: string
  model: string
  sandbox_provider: string
  mcp_server_ids: Array<string>
  park_reason: string | null
  active_run_id: string | null
  created_at: string
  updated_at: string
}

export type PlatformEvent = {
  event_id: string
  seq: number
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

export type PlatformApproval = {
  approval_id: string
  kind: string
  status: string
  payload: Record<string, unknown>
  created_at: string
}

export type McpServer = {
  mcp_server_id: string
  scope: "user" | "org"
  name: string
  transport: "sse" | "streamable_http" | "stdio"
  url: string | null
  command: string | null
  enabled: boolean
  required: boolean
  has_auth: boolean
  last_test_ok: boolean | null
  last_tools: Array<string>
}

export type CatalogItem = { id: string; enabled?: boolean; default?: boolean }

const apiBase = (import.meta.env.VITE_PLATFORM_API_BASE_URL || "").replace(/\/$/, "")

function headers(extra?: HeadersInit): Headers {
  const result = new Headers(extra)
  result.set("Content-Type", "application/json")
  const token =
    typeof window === "undefined"
      ? null
      : localStorage.getItem("openswe-platform-token")
  if (token) result.set("Authorization", `Bearer ${token}`)
  return result
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: headers(init?.headers),
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: string; title?: string }
      | null
    throw new Error(body?.detail || body?.title || `Request failed (${response.status})`)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function command(method: string, body?: unknown): RequestInit {
  return {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: { "Idempotency-Key": crypto.randomUUID() },
  }
}

export const platformApi = {
  listTasks: () => request<{ items: Array<PlatformTask> }>("/v1/tasks"),
  getTask: (id: string) => request<PlatformTask>(`/v1/tasks/${id}`),
  createTask: (body: Record<string, unknown>) =>
    request<PlatformTask>("/v1/tasks", command("POST", body)),
  events: (id: string) =>
    request<{ items: Array<PlatformEvent> }>(`/v1/tasks/${id}/events?limit=500`),
  approvals: (id: string) =>
    request<{ items: Array<PlatformApproval> }>(`/v1/tasks/${id}/approvals/pending`),
  message: (id: string, content: string) =>
    request(`/v1/tasks/${id}/messages`, command("POST", { content })),
  cancel: (id: string) =>
    request(`/v1/tasks/${id}/cancel`, command("POST", { reason: "user_requested" })),
  decide: (id: string, decision: "approved" | "rejected", comment?: string) =>
    request(`/v1/approvals/${id}/decision`, command("POST", { decision, comment })),
  models: () => request<{ items: Array<CatalogItem> }>("/v1/models"),
  sandboxes: () =>
    request<{ items: Array<CatalogItem>; default: string }>("/v1/sandbox-providers"),
  settings: () =>
    request<{
      preferred_model: string | null
      preferred_sandbox_provider: string | null
      default_mcp_server_ids: Array<string>
    }>("/v1/me/settings"),
  saveSettings: (body: Record<string, unknown>) =>
    request("/v1/me/settings", { method: "PATCH", body: JSON.stringify(body) }),
  mcpServers: () => request<{ items: Array<McpServer> }>("/v1/mcp-servers"),
  createMcp: (body: Record<string, unknown>) =>
    request<McpServer>("/v1/mcp-servers", { method: "POST", body: JSON.stringify(body) }),
  testMcp: (id: string) =>
    request<{ ok: boolean; tools: Array<string>; detail: string }>(
      `/v1/mcp-servers/${id}/test`,
      { method: "POST" }
    ),
  deleteMcp: (id: string) =>
    request<void>(`/v1/mcp-servers/${id}`, { method: "DELETE" }),
}

export async function streamTaskEvents(
  taskId: string,
  signal: AbortSignal,
  onEvent: (event: PlatformEvent) => void,
  onStatus: (status: string) => void
): Promise<void> {
  let lastEventId = 0
  let terminal = false
  for (;;) {
    if (signal.aborted) return
    try {
      const streamHeaders = headers()
      if (lastEventId) streamHeaders.set("Last-Event-ID", String(lastEventId))
      const response = await fetch(
        `${apiBase}/v1/tasks/${taskId}/events/stream`,
        { headers: streamHeaders, signal }
      )
      if (!response.ok || !response.body)
        throw new Error("Event stream unavailable")
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
      let buffer = ""
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += value
        const frames = buffer.split("\n\n")
        buffer = frames.pop() || ""
        for (const frame of frames) {
          const type = frame.match(/^event: (.+)$/m)?.[1]
          const raw = frame.match(/^data: (.+)$/m)?.[1]
          if (!raw) continue
          const data = JSON.parse(raw) as PlatformEvent | { status: string }
          if (type === "run_event") {
            const event = data as PlatformEvent
            lastEventId = Math.max(lastEventId, event.seq)
            onEvent(event)
          }
          if (type === "task_status") {
            const status = (data as { status: string }).status
            onStatus(status)
            terminal = ["succeeded", "failed", "cancelled"].includes(status)
          }
        }
      }
      if (terminal) return
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return
      if (!(error instanceof TypeError)) throw error
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
}
