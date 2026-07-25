# Multi-service platform

Implementation of [`SERVICE_CONTRACTS.md`](./SERVICE_CONTRACTS.md).

## Services

| Service | Module | Image / Dockerfile | Port | Role |
|---|---|---|---|---|
| **API** | `openswe_platform.api.app:app` | `deploy/Dockerfile.api` | 8080 | Tasks, approvals, MCP CRUD, SSE, **outbox → NATS** |
| **Webhook** | `openswe_platform.webhook.app:app` | `deploy/Dockerfile.webhook` | 8081 | GitHub/Slack ingress → Postgres + outbox |
| **Harness** | `openswe_platform.harness.worker` | `deploy/Dockerfile.harness` | — | **NATS consumer**; lease, LiteLLM, sandboxes, MCP, Postgres checkpoints |
| **UI** | `ui/` | (existing) | — | Point at API base URL |

### Does the harness run separately?

**Yes.** The harness is a pure worker:

1. API/webhook write tasks + outbox rows in Postgres.
2. Outbox publisher (in API and webhook) publishes `task.enqueue` to **NATS JetStream `TASKS`**.
3. Harness **pull-subscribes** to that stream, claims a task (Postgres lease), runs the agent, checkpoints, completes/parks.

You can start/stop/scale harness without restarting API or webhooks. If harness is down, jobs stay in JetStream / `queued` until a worker appears. No KEDA is required locally — use Compose scale:

```bash
docker-compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --scale harness=3
# or: make platform-up  then  scale as above
```

## Dependencies

| Dep | Compose service | Notes |
|---|---|---|
| PostgreSQL | `postgres` | Schema from `migrations/001_init.sql` on first boot |
| NATS JetStream | `nats` | `-js` enabled; monitor on `:8222` |
| LLM providers | env on harness | Direct OpenAI/Anthropic/Fireworks/Google (**default**) |
| LiteLLM | `litellm` (profile `with-litellm`) | **Optional** proxy when `LITELLM_ENABLED=true` |

Sandboxes: `daytona` (default), `agent_sandbox`, `opensandbox` — stubs if credentials missing.

## Docker Compose (recommended local)

Files:

- `deploy/docker-compose.yml` — postgres, nats, api, webhook, harness (+ optional litellm)
- `deploy/Dockerfile.api` / `Dockerfile.webhook` / `Dockerfile.harness`
- `deploy/.env.example` — template (committed)
- `deploy/.env` — local values (gitignored; created from example)

```bash
# First time
cp deploy/.env.example deploy/.env
# Optional: set OPENAI_API_KEY / DAYTONA_API_KEY in deploy/.env

# Build images and start stack
make platform-up
# equivalent:
# docker compose -f deploy/docker-compose.yml --env-file deploy/.env up --build -d

make platform-ps
make platform-logs

# Stop
make platform-down
```

Smoke test:

```bash
curl -s -X POST http://localhost:8080/v1/tasks \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-1' \
  -d '{"title":"Hello","prompt":"DONE: smoke test","agent_type":"coding"}'
```

Watch harness pick up the job (`make platform-logs`). Task status:

```bash
curl -s http://localhost:8080/v1/tasks | jq .
```

### LLM: direct providers (default) vs optional LiteLLM

**Default:** harness calls providers directly. Set at least one key in `deploy/.env`:

```bash
OPENAI_API_KEY=sk-...
# or ANTHROPIC_API_KEY / FIREWORKS_API_KEY / GOOGLE_API_KEY
DEFAULT_MODEL=openai:gpt-4o-mini
LLM_MODE=auto          # or direct
LITELLM_ENABLED=false
```

Model id formats: `openai:gpt-4o-mini`, `anthropic:claude-sonnet-4-20250514`, `fireworks:…`, `google:gemini-2.0-flash`.

**Optional LiteLLM proxy:**

```bash
# deploy/.env
LITELLM_ENABLED=true
LLM_MODE=litellm   # or auto with LITELLM_ENABLED=true
LITELLM_BASE_URL=http://litellm:4000
LITELLM_API_KEY=sk-litellm
OPENAI_API_KEY=...     # upstream keys for the proxy

docker-compose -f deploy/docker-compose.yml --env-file deploy/.env --profile with-litellm up -d
```

## Host processes (deps in Docker only)

```bash
make platform-deps          # postgres + nats
export DATABASE_URL=postgresql+asyncpg://openswe:openswe@localhost:5432/openswe
export NATS_URL=nats://localhost:4222
make platform-api           # terminal 1
make platform-webhook       # terminal 2
make platform-harness       # terminal 3 — can start later; drains backlog
```

## Package layout

```text
openswe_platform/
  common/     # enums, db, models, outbox, tasks, resolution, messaging
  api/        # FastAPI control plane
  webhook/    # FastAPI public ingress
  harness/    # worker, agents registry, sandboxes, litellm, mcp
migrations/
deploy/
  Dockerfile.api
  Dockerfile.webhook
  Dockerfile.harness
  docker-compose.yml
  .env.example
  litellm_config.yaml
  k8s/          # cluster deploy + KEDA (not used by compose)
```

## Kubernetes

KEDA and multi-replica Deployments live under `deploy/k8s/` (not used by Compose):

```bash
kubectl apply -k deploy/k8s/
```

## Legacy monolith

The existing `agent/` LangGraph app (`make dev`) remains available during the strangler migration. New multi-service traffic uses `openswe_platform.*`.
