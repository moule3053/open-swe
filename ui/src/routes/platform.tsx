import { createFileRoute } from "@tanstack/react-router"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Activity,
  ArrowRight,
  Bot,
  Boxes,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  Code2,
  DatabaseZap,
  ExternalLink,
  GitBranch,
  KeyRound,
  LoaderCircle,
  Menu,
  MessageSquareText,
  MoreHorizontal,
  Plus,
  RotateCw,
  Save,
  Send,
  ServerCog,
  Settings2,
  ShieldCheck,
  TerminalSquare,
  Trash2,
  X,
  XCircle,
} from "lucide-react"
import { useEffect, useState } from "react"
import type { FormEvent } from "react"

import type { McpServer, PlatformEvent, PlatformTask } from "@/lib/platform-api"
import {
  platformApi,
  streamTaskEvents,
} from "@/lib/platform-api"
import "@/styles/platform.css"

export const Route = createFileRoute("/platform")({ component: Platform })

type Section = "tasks" | "mcp" | "settings"

function Platform() {
  const [section, setSection] = useState<Section>("tasks")
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [mobileNav, setMobileNav] = useState(false)
  const tasks = useQuery({ queryKey: ["platform", "tasks"], queryFn: platformApi.listTasks })

  useEffect(() => {
    if (!selectedTaskId && tasks.data?.items[0]) setSelectedTaskId(tasks.data.items[0].task_id)
  }, [selectedTaskId, tasks.data])

  return (
    <div className="platform-shell">
      <aside className={`platform-sidebar ${mobileNav ? "is-open" : ""}`}>
        <div className="platform-brand">
          <div className="platform-mark"><Code2 size={17} /></div>
          <span>Open SWE</span><small>platform</small>
          <button className="platform-mobile-close" onClick={() => setMobileNav(false)}><X /></button>
        </div>
        <nav className="platform-nav">
          <NavButton icon={<Activity />} label="Tasks" active={section === "tasks"} onClick={() => setSection("tasks")} />
          <NavButton icon={<DatabaseZap />} label="MCP servers" active={section === "mcp"} onClick={() => setSection("mcp")} />
          <NavButton icon={<Settings2 />} label="Runtime settings" active={section === "settings"} onClick={() => setSection("settings")} />
        </nav>
        <div className="platform-sidebar-foot">
          <div className="platform-health"><span /> Control plane online</div>
          <p>Task orchestration, approvals, and runtime policy in one place.</p>
        </div>
      </aside>

      <main className="platform-main">
        <header className="platform-topbar">
          <button className="platform-menu" onClick={() => setMobileNav(true)}><Menu /></button>
          <div>
            <span className="platform-eyebrow">Workspace / default</span>
            <h1>{section === "tasks" ? "Agent runs" : section === "mcp" ? "MCP registry" : "Runtime settings"}</h1>
          </div>
          <div className="platform-top-actions">
            {section === "tasks" && <button className="platform-primary" onClick={() => setCreateOpen(true)}><Plus /> New task</button>}
          </div>
        </header>

        {section === "tasks" && (
          <TasksView
            tasks={tasks.data?.items || []}
            loading={tasks.isLoading}
            selectedId={selectedTaskId}
            onSelect={setSelectedTaskId}
            onCreate={() => setCreateOpen(true)}
          />
        )}
        {section === "mcp" && <McpView />}
        {section === "settings" && <SettingsView />}
      </main>
      {createOpen && <CreateTaskModal onClose={() => setCreateOpen(false)} onCreated={(id) => { setSelectedTaskId(id); setCreateOpen(false); setSection("tasks") }} />}
    </div>
  )
}

function NavButton({ icon, label, active, onClick }: { icon: React.ReactNode; label: string; active: boolean; onClick: () => void }) {
  return <button className={active ? "active" : ""} onClick={onClick}>{icon}<span>{label}</span>{active && <ChevronRight className="nav-chevron" />}</button>
}

function TasksView({ tasks, loading, selectedId, onSelect, onCreate }: { tasks: Array<PlatformTask>; loading: boolean; selectedId: string | null; onSelect: (id: string) => void; onCreate: () => void }) {
  const selected = tasks.find((task) => task.task_id === selectedId) || null
  return (
    <div className="platform-workspace">
      <section className="task-list-pane">
        <div className="pane-heading"><div><h2>Tasks</h2><p>{tasks.length} total runs</p></div><button className="icon-button" aria-label="Refresh tasks" onClick={() => location.reload()}><RotateCw /></button></div>
        <div className="task-list">
          {loading && <Empty icon={<LoaderCircle className="spin" />} title="Loading tasks" copy="Reading the control plane…" />}
          {!loading && !tasks.length && <Empty icon={<Bot />} title="No tasks yet" copy="Start an agent run and watch its events arrive here." action={<button className="platform-primary small" onClick={onCreate}><Plus /> New task</button>} />}
          {tasks.map((task) => <TaskRow key={task.task_id} task={task} active={task.task_id === selectedId} onClick={() => onSelect(task.task_id)} />)}
        </div>
      </section>
      <section className="task-detail-pane">
        {selected ? <TaskDetail taskId={selected.task_id} fallback={selected} /> : <Empty icon={<TerminalSquare />} title="Select a task" copy="Run details, events, and approvals will appear here." />}
      </section>
    </div>
  )
}

function TaskRow({ task, active, onClick }: { task: PlatformTask; active: boolean; onClick: () => void }) {
  return (
    <button className={`task-row ${active ? "active" : ""}`} onClick={onClick}>
      <div className="task-row-top"><StatusDot status={task.status} /><strong>{task.title || task.prompt || "Untitled task"}</strong><ChevronRight /></div>
      <div className="task-row-meta"><span><GitBranch /> {task.repo || "No repository"}</span><time>{relativeTime(task.updated_at)}</time></div>
      <div className="task-row-foot"><span className="mini-pill">{task.model}</span><span className="mini-pill">{task.sandbox_provider}</span></div>
    </button>
  )
}

function TaskDetail({ taskId, fallback }: { taskId: string; fallback: PlatformTask }) {
  const client = useQueryClient()
  const [events, setEvents] = useState<Array<PlatformEvent>>([])
  const [guidance, setGuidance] = useState("")
  const taskQuery = useQuery({ queryKey: ["platform", "task", taskId], queryFn: () => platformApi.getTask(taskId), initialData: fallback, refetchInterval: 5000 })
  const approvals = useQuery({ queryKey: ["platform", "approvals", taskId], queryFn: () => platformApi.approvals(taskId), refetchInterval: 3000 })
  const initialEvents = useQuery({ queryKey: ["platform", "events", taskId], queryFn: () => platformApi.events(taskId) })

  useEffect(() => { setEvents(initialEvents.data?.items || []) }, [initialEvents.data])
  useEffect(() => {
    const controller = new AbortController()
    void streamTaskEvents(taskId, controller.signal, (event) => setEvents((current) => current.some((item) => item.seq === event.seq) ? current : [...current, event]), () => { void client.invalidateQueries({ queryKey: ["platform", "task", taskId] }); void client.invalidateQueries({ queryKey: ["platform", "tasks"] }) }).catch(() => {})
    return () => controller.abort()
  }, [client, taskId])

  const message = useMutation({ mutationFn: () => platformApi.message(taskId, guidance), onSuccess: () => setGuidance("") })
  const cancel = useMutation({ mutationFn: () => platformApi.cancel(taskId), onSuccess: () => { void client.invalidateQueries({ queryKey: ["platform"] }) } })
  const task = taskQuery.data
  const pending = approvals.data?.items || []
  return (
    <div className="task-detail">
      <div className="detail-head">
        <div><div className="detail-kicker"><StatusBadge status={task.status} /><span>#{task.task_id.slice(0, 8)}</span></div><h2>{task.title || "Untitled task"}</h2><p>{task.prompt || "No prompt was supplied."}</p></div>
        <button className="icon-button"><MoreHorizontal /></button>
      </div>
      <div className="detail-facts">
        <Fact icon={<Bot />} label="Agent" value={task.agent_type} />
        <Fact icon={<Boxes />} label="Sandbox" value={task.sandbox_provider} />
        <Fact icon={<ServerCog />} label="Model" value={task.model} />
        <Fact icon={<GitBranch />} label="Repository" value={task.repo || "Not attached"} />
      </div>
      {pending.map((approval) => <ApprovalCard key={approval.approval_id} approval={approval} taskId={taskId} />)}
      <div className="timeline-head"><div><h3>Live activity</h3><p>Durable events from this task</p></div><span className="live-pill"><span /> LIVE</span></div>
      <div className="event-timeline">
        {!events.length && <Empty icon={<Clock3 />} title="Waiting for activity" copy="Events appear as soon as a worker claims the task." />}
        {[...events].reverse().map((event) => <EventRow key={event.event_id} event={event} />)}
      </div>
      {!finalStatus(task.status) && (
        <form className="guidance-box" onSubmit={(event) => { event.preventDefault(); if (guidance.trim()) message.mutate() }}>
          <MessageSquareText />
          <input value={guidance} onChange={(event) => setGuidance(event.target.value)} placeholder="Send guidance to the running agent…" />
          <button type="submit" disabled={!guidance.trim() || message.isPending}><Send /></button>
        </form>
      )}
      {!finalStatus(task.status) && <button className="text-danger" onClick={() => cancel.mutate()} disabled={cancel.isPending}><XCircle /> Cancel task</button>}
    </div>
  )
}

function ApprovalCard({ approval, taskId }: { approval: { approval_id: string; kind: string; payload: Record<string, unknown> }; taskId: string }) {
  const client = useQueryClient()
  const decide = useMutation({ mutationFn: (decision: "approved" | "rejected") => platformApi.decide(approval.approval_id, decision), onSuccess: () => { void client.invalidateQueries({ queryKey: ["platform", "approvals", taskId] }); void client.invalidateQueries({ queryKey: ["platform", "tasks"] }) } })
  return <div className="approval-card"><div className="approval-icon"><ShieldCheck /></div><div><span>Approval required</span><h3>{approval.kind.replaceAll("_", " ")}</h3><p>{String(approval.payload.plan || approval.payload.question || "The agent is waiting for your decision.")}</p><div><button className="platform-primary small" onClick={() => decide.mutate("approved")}><Check /> Approve</button><button className="platform-secondary small" onClick={() => decide.mutate("rejected")}><X /> Reject</button></div></div></div>
}

function EventRow({ event }: { event: PlatformEvent }) {
  const [open, setOpen] = useState(false)
  const tone = event.event_type.includes("failed") || event.event_type.includes("error") ? "danger" : event.event_type.includes("succeeded") || event.event_type.includes("finished") ? "success" : "neutral"
  return <button className="event-row" onClick={() => setOpen(!open)}><span className={`event-icon ${tone}`}>{tone === "danger" ? <X /> : tone === "success" ? <Check /> : <CircleDot />}</span><div><strong>{event.event_type.replaceAll("_", " ")}</strong><time>{new Date(event.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>{open && <pre>{JSON.stringify(event.payload, null, 2)}</pre>}</div><ChevronRight className={open ? "rotated" : ""} /></button>
}

function McpView() {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ["platform", "mcp"], queryFn: platformApi.mcpServers })
  return <div className="platform-page"><div className="page-intro"><div><span className="platform-eyebrow">Tool connections</span><h2>Model Context Protocol</h2><p>Connect remote tools once, scope them to a user or organization, and attach them to agent tasks.</p></div><button className="platform-primary" onClick={() => setOpen(true)}><Plus /> Add server</button></div><div className="registry-card"><div className="registry-head"><span>Name</span><span>Transport</span><span>Tools</span><span>Health</span><span /></div>{query.isLoading && <Empty icon={<LoaderCircle className="spin" />} title="Loading servers" copy="" />}{query.data?.items.map((server) => <McpRow key={server.mcp_server_id} server={server} onChanged={() => void client.invalidateQueries({ queryKey: ["platform", "mcp"] })} />)}{!query.isLoading && !query.data?.items.length && <Empty icon={<DatabaseZap />} title="No MCP servers" copy="Connect an SSE or streamable HTTP MCP endpoint." />}</div>{open && <CreateMcpModal onClose={() => setOpen(false)} onCreated={() => { setOpen(false); void client.invalidateQueries({ queryKey: ["platform", "mcp"] }) }} />}</div>
}

function McpRow({ server, onChanged }: { server: McpServer; onChanged: () => void }) {
  const [result, setResult] = useState<string | null>(null)
  const test = useMutation({ mutationFn: () => platformApi.testMcp(server.mcp_server_id), onSuccess: (data) => { setResult(data.ok ? `${data.tools.length} tools discovered` : data.detail); onChanged() } })
  const remove = useMutation({ mutationFn: () => platformApi.deleteMcp(server.mcp_server_id), onSuccess: onChanged })
  return <div className="registry-row"><div className="server-name"><div><DatabaseZap /></div><span><strong>{server.name}</strong><small>{server.scope} scope {server.has_auth && "· secured"}</small></span></div><code>{server.transport.replaceAll("_", " ")}</code><span>{server.last_tools.length ? `${server.last_tools.length} loaded` : "—"}</span><span className={`health-label ${server.last_test_ok === false ? "bad" : ""}`}><span /> {server.last_test_ok === false ? "Check failed" : result || (server.last_test_ok ? "Connected" : "Not tested")}</span><div className="row-actions"><button className="icon-button" aria-label={`Test ${server.name}`} onClick={() => test.mutate()}><RotateCw className={test.isPending ? "spin" : ""} /></button><button className="icon-button danger" aria-label={`Delete ${server.name}`} onClick={() => remove.mutate()}><Trash2 /></button></div></div>
}

function SettingsView() {
  const client = useQueryClient()
  const settings = useQuery({ queryKey: ["platform", "settings"], queryFn: platformApi.settings })
  const models = useQuery({ queryKey: ["platform", "models"], queryFn: platformApi.models })
  const sandboxes = useQuery({ queryKey: ["platform", "sandboxes"], queryFn: platformApi.sandboxes })
  const [model, setModel] = useState("")
  const [sandbox, setSandbox] = useState("")
  const [token, setToken] = useState("")
  useEffect(() => { if (settings.data) { setModel(settings.data.preferred_model || ""); setSandbox(settings.data.preferred_sandbox_provider || "") }; setToken(localStorage.getItem("openswe-platform-token") || "") }, [settings.data])
  const save = useMutation({ mutationFn: async () => { if (token) localStorage.setItem("openswe-platform-token", token); else localStorage.removeItem("openswe-platform-token"); await platformApi.saveSettings({ preferred_model: model || null, preferred_sandbox_provider: sandbox || null }) }, onSuccess: () => void client.invalidateQueries({ queryKey: ["platform", "settings"] }) })
  return <div className="platform-page settings-page"><div className="page-intro"><div><span className="platform-eyebrow">Personal defaults</span><h2>Runtime settings</h2><p>Choose what new tasks inherit when no explicit runtime option is supplied.</p></div></div><div className="settings-grid"><section className="settings-card"><div className="settings-card-title"><Bot /><div><h3>Agent runtime</h3><p>Defaults for model and isolated execution.</p></div></div><label>Preferred model<select value={model} onChange={(event) => setModel(event.target.value)}><option value="">Organization default</option>{models.data?.items.map((item) => <option key={item.id}>{item.id}</option>)}</select></label><label>Preferred sandbox<select value={sandbox} onChange={(event) => setSandbox(event.target.value)}><option value="">Organization default</option>{sandboxes.data?.items.filter((item) => item.enabled).map((item) => <option key={item.id}>{item.id}</option>)}</select></label></section><section className="settings-card"><div className="settings-card-title"><KeyRound /><div><h3>API authentication</h3><p>Stored only in this browser and sent as a bearer token.</p></div></div><label>Platform token<input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Optional in local development" /></label><div className="security-note"><ShieldCheck /><span>Secrets are never returned by the MCP API after creation.</span></div></section></div><button className="platform-primary save-button" onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? <LoaderCircle className="spin" /> : save.isSuccess ? <CheckCircle2 /> : <Save />} {save.isSuccess ? "Saved" : "Save settings"}</button></div>
}

function CreateTaskModal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const client = useQueryClient()
  const models = useQuery({ queryKey: ["platform", "models"], queryFn: platformApi.models })
  const sandboxes = useQuery({ queryKey: ["platform", "sandboxes"], queryFn: platformApi.sandboxes })
  const mcp = useQuery({ queryKey: ["platform", "mcp"], queryFn: platformApi.mcpServers })
  const [title, setTitle] = useState("")
  const [prompt, setPrompt] = useState("")
  const [repo, setRepo] = useState("")
  const [model, setModel] = useState("")
  const [sandbox, setSandbox] = useState("")
  const [selectedMcp, setSelectedMcp] = useState<Array<string>>([])
  const create = useMutation({ mutationFn: () => platformApi.createTask({ title: title || undefined, prompt, repo: repo || undefined, model: model || undefined, sandbox_provider: sandbox || undefined, mcp_mode: selectedMcp.length ? "append" : "inherit", mcp_server_ids: selectedMcp }), onSuccess: (task) => { void client.invalidateQueries({ queryKey: ["platform", "tasks"] }); onCreated(task.task_id) } })
  const submit = (event: FormEvent) => { event.preventDefault(); if (prompt.trim()) create.mutate() }
  return <Modal title="Launch a new agent" subtitle="The task is queued durably and can resume after worker restarts." onClose={onClose}><form className="modal-form" onSubmit={submit}><label>Task title <span>optional</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Improve checkout reliability" /></label><label>What should the agent do?<textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={5} placeholder="Describe the outcome, constraints, and how to verify it…" autoFocus /></label><div className="form-grid"><label>Repository<input value={repo} onChange={(event) => setRepo(event.target.value)} placeholder="owner/repository" /></label><label>Base branch<input defaultValue="main" readOnly /></label><label>Model<select value={model} onChange={(event) => setModel(event.target.value)}><option value="">Default</option>{models.data?.items.map((item) => <option key={item.id}>{item.id}</option>)}</select></label><label>Sandbox<select value={sandbox} onChange={(event) => setSandbox(event.target.value)}><option value="">Default</option>{sandboxes.data?.items.filter((item) => item.enabled).map((item) => <option key={item.id}>{item.id}</option>)}</select></label></div>{!!mcp.data?.items.length && <fieldset><legend>MCP tools</legend><div className="choice-list">{mcp.data.items.filter((server) => server.enabled).map((server) => <label key={server.mcp_server_id}><input type="checkbox" checked={selectedMcp.includes(server.mcp_server_id)} onChange={() => setSelectedMcp((current) => current.includes(server.mcp_server_id) ? current.filter((id) => id !== server.mcp_server_id) : [...current, server.mcp_server_id])} /><span><DatabaseZap />{server.name}</span></label>)}</div></fieldset>}{create.error && <p className="form-error">{create.error.message}</p>}<div className="modal-actions"><button type="button" className="platform-secondary" onClick={onClose}>Cancel</button><button className="platform-primary" disabled={!prompt.trim() || create.isPending}>{create.isPending ? <LoaderCircle className="spin" /> : <ArrowRight />} Queue task</button></div></form></Modal>
}

function CreateMcpModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("")
  const [url, setUrl] = useState("")
  const [transport, setTransport] = useState("streamable_http")
  const [token, setToken] = useState("")
  const create = useMutation({ mutationFn: () => platformApi.createMcp({ name, url, transport, scope: "user", auth: token ? { token } : undefined }), onSuccess: onCreated })
  return <Modal title="Connect an MCP server" subtitle="Credentials are encrypted before storage and remain write-only." onClose={onClose}><form className="modal-form" onSubmit={(event) => { event.preventDefault(); create.mutate() }}><label>Display name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Internal docs" autoFocus /></label><label>Transport<select value={transport} onChange={(event) => setTransport(event.target.value)}><option value="streamable_http">Streamable HTTP</option><option value="sse">Server-sent events</option></select></label><label>Endpoint URL<input type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://mcp.example.com/mcp" /></label><label>Bearer token <span>optional</span><input type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Stored encrypted" /></label>{create.error && <p className="form-error">{create.error.message}</p>}<div className="modal-actions"><button type="button" className="platform-secondary" onClick={onClose}>Cancel</button><button className="platform-primary" disabled={!name || !url || create.isPending}>{create.isPending ? <LoaderCircle className="spin" /> : <ExternalLink />} Connect server</button></div></form></Modal>
}

function Modal({ title, subtitle, onClose, children }: { title: string; subtitle: string; onClose: () => void; children: React.ReactNode }) { return <div className="modal-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose() }}><div className="platform-modal" role="dialog" aria-modal="true"><div className="modal-head"><div><h2>{title}</h2><p>{subtitle}</p></div><button className="icon-button" onClick={onClose}><X /></button></div>{children}</div></div> }
function Empty({ icon, title, copy, action }: { icon: React.ReactNode; title: string; copy: string; action?: React.ReactNode }) { return <div className="platform-empty"><div>{icon}</div><h3>{title}</h3><p>{copy}</p>{action}</div> }
function Fact({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) { return <div className="detail-fact"><span>{icon}</span><div><small>{label}</small><strong>{value}</strong></div></div> }
function StatusDot({ status }: { status: string }) { return <span className={`status-dot status-${status}`} /> }
function StatusBadge({ status }: { status: string }) { return <span className={`status-badge status-${status}`}><StatusDot status={status} />{status}</span> }
function finalStatus(status: string) { return ["succeeded", "failed", "cancelled"].includes(status) }
function relativeTime(value: string) { const seconds = Math.floor((Date.now() - new Date(value).getTime()) / 1000); if (seconds < 60) return "now"; if (seconds < 3600) return `${Math.floor(seconds / 60)}m`; if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`; return `${Math.floor(seconds / 86400)}d` }
