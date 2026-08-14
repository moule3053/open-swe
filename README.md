<div align="center">
  <a href="https://github.com/langchain-ai/open-swe">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="assets/dark.svg">
      <source media="(prefers-color-scheme: light)" srcset="assets/light.svg">
      <img alt="Open SWE Logo" src="assets/dark.svg" width="35%">
    </picture>
  </a>
</div>

<div align="center">
  <h3>Open-source framework for building your org's internal coding agent.</h3>
</div>

<div align="center">
  <a href="https://opensource.org/licenses/MIT" target="_blank"><img src="https://img.shields.io/github/license/langchain-ai/open-swe" alt="License"></a>
  <a href="https://github.com/langchain-ai/open-swe/stargazers" target="_blank"><img src="https://img.shields.io/github/stars/langchain-ai/open-swe" alt="GitHub Stars"></a>
  <a href="https://github.com/langchain-ai/langgraph" target="_blank"><img src="https://img.shields.io/badge/Built%20on-LangGraph-blue" alt="Built on LangGraph"></a>
  <a href="https://github.com/langchain-ai/deepagents" target="_blank"><img src="https://img.shields.io/badge/Built%20on-Deep%20Agents-blue" alt="Built on Deep Agents"></a>
  <a href="https://x.com/langchain" target="_blank"><img src="https://img.shields.io/twitter/url/https/twitter.com/langchain.svg?style=social&label=Follow%20%40LangChain" alt="Twitter / X"></a>
</div>

<br>

Elite engineering orgs like Stripe, Ramp, and Coinbase are building their own internal coding agents — Slackbots, CLIs, and web apps that meet engineers where they already work. These agents are connected to internal systems with the right context, permissioning, and safety boundaries to operate with minimal human oversight.

Open SWE is the open-source version of this pattern. Built on [LangGraph](https://langchain-ai.github.io/langgraph/) and [Deep Agents](https://github.com/langchain-ai/deepagents), it gives you the same architecture those companies built internally: cloud sandboxes, Slack and Linear invocation, subagent orchestration, and automatic PR creation — ready to customize for your own codebase and workflows.

> [!NOTE]
> 💬 Read the **announcement blog post [here](https://blog.langchain.com/open-swe-an-open-source-framework-for-internal-coding-agents/)**

---

## Architecture

Open SWE makes the same core architectural decisions as the best internal coding agents. Here's how it maps to the patterns described in [this overview](https://x.com/kishan_dahya/status/2028971339974099317) of Stripe's Minions, Ramp's Inspect, and Coinbase's Cloudbot:

### 1. Agent Harness — Composed on Deep Agents

Rather than forking an existing agent or building from scratch, Open SWE **composes** on the [Deep Agents](https://github.com/langchain-ai/deepagents) framework — similar to how Ramp built on top of OpenCode. This gives you an upgrade path (pull in upstream improvements) while letting you customize the orchestration, tools, and middleware for your org.

```python
create_deep_agent(
    model="openai:gpt-5.6-sol",
    system_prompt=construct_system_prompt(...),
    tools=[http_request, fetch_url, linear_comment, slack_thread_reply],
    backend=sandbox_backend,
    middleware=[ToolErrorMiddleware(), check_message_queue_before_model, ...],
)
```

### 2. Sandbox — Isolated Cloud Environments

Every task runs in its own **isolated cloud sandbox** — a remote Linux environment with full shell access. The repo is cloned in, the agent gets full permissions, and the blast radius of any mistake is fully contained. No production access, no confirmation prompts.

Open SWE supports multiple sandbox providers out of the box — [Modal](https://modal.com/), [Daytona](https://www.daytona.io/), [Runloop](https://www.runloop.ai/), [E2B](https://e2b.dev/), and [LangSmith](https://smith.langchain.com/) — and you can plug in your own. See the [Customization Guide](docs/CUSTOMIZATION.md#1-sandbox) for details.

This fork also supports the Kubernetes SIGs [Agent Sandbox](https://github.com/kubernetes-sigs/agent-sandbox) API. On GKE, each task can run in an Agent Sandbox Pod isolated by [Kata Containers](https://katacontainers.io/), while the Open SWE control plane remains entirely in your cluster.

This follows the principle all three companies converge on: **isolate first, then give full permissions inside the boundary.**

- Each thread gets a persistent sandbox (reused across follow-up messages)
- Sandboxes auto-recreate if they become unreachable
- Multiple tasks run in parallel — each in its own sandbox, no queuing

### 3. Tools — Curated, Not Accumulated

Stripe's key insight: *tool curation matters more than tool quantity.* Open SWE follows this principle with a small, focused toolset:

| Tool | Purpose |
|---|---|
| `execute` | Shell commands in the sandbox |
| `fetch_url` | Fetch web pages as markdown |
| `http_request` | API calls (GET, POST, etc.) |
| `linear_comment` | Post updates to Linear tickets |
| `linear_search_issues` | Search Linear issues by free text |
| `slack_add_reaction` | React to Slack messages |
| `slack_thread_reply` | Reply in Slack threads |

GitHub operations in the upstream LangSmith mode use `GH_TOKEN=dummy gh` through the LangSmith proxy. In standalone Kubernetes mode, the harness mints a short-lived GitHub App installation token and configures repository authentication inside the sandbox. The built-in Deep Agents tools include `read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep`, `write_todos`, and `task` (subagent spawning).

**Optional observability tools (server-side):** Admins can connect Datadog and LangSmith from team settings (Admin → Observability credentials). When connected, the agent gains Datadog tools (via Datadog's hosted MCP server, default `toolsets=core`) and read-only LangSmith tools (`langsmith_get_trace`, `langsmith_list_runs`). These run in the LangGraph server process using credentials encrypted at rest — the sandbox never holds Datadog or LangSmith keys. They are loaded **only for runs triggered by an authorized user** (admins, plus any emails in `OBSERVABILITY_AUTHORIZED_EMAILS`), so a prompt-injected run from an untrusted contributor cannot reach team observability data. Use scoped, read-oriented keys regardless: observability data (logs, traces) is attacker-influenced content that can carry prompt injection, and the agent has network egress — the same residual-risk class as `web_search` / `fetch_url`.

**Optional Corridor guardrails (server-side MCP):** Set `CORRIDOR_API_TOKEN` (or `CORRIDOR_MCP_TOKEN` / `CORRIDOR_TOKEN`) to load Corridor's hosted MCP server for each agent run. Open SWE exposes only Corridor's `analyzePlan` tool. `CORRIDOR_MCP_URL` defaults to `https://app.corridor.dev/api/mcp`; if set explicitly, Open SWE only accepts the same HTTPS host and `/api/mcp` path. Tokens are sent via `Authorization: Bearer ...` from the LangGraph server process and are never placed in the sandbox. A legacy `?token=...` URL is accepted and normalized into the header form.

### 4. Context Engineering — AGENTS.md + Source Context

Open SWE gathers context from two sources:

- **`AGENTS.md`** — If the repo contains an `AGENTS.md` file at the root, it's read from the sandbox and injected into the system prompt. This is your repo-level equivalent of Stripe's rule files: encoding conventions, testing requirements, and architectural decisions that every agent run should follow.
- **Source context** — The full Linear issue (title, description, comments) or Slack thread history is assembled and passed to the agent, so it starts with rich context rather than discovering everything through tool calls.

### 5. Orchestration — Subagents + Middleware

Open SWE's orchestration has two layers:

**Subagents:** The Deep Agents framework natively supports spawning child agents via the `task` tool. The main agent can fan out independent subtasks to isolated subagents — each with its own middleware stack, todo list, and file operations. This is similar to Ramp's child sessions for parallel work.

**Middleware:** Deterministic middleware hooks run around the agent loop:

- **`check_message_queue_before_model`** — Injects follow-up messages (Linear comments or Slack messages that arrive mid-run) before the next model call. You can message the agent while it's working and it'll pick up your input at its next step.
- **`notify_step_limit_reached`** — After-agent hook that posts a Slack reply when the agent hits the model-call limit, so users get a clear signal instead of silence.
- **`ToolErrorMiddleware`** — Catches and handles tool errors gracefully.

### 6. Invocation — Slack, Linear, and GitHub

All three companies in the article converge on **Slack as the primary invocation surface**. Open SWE does the same:

- **Slack** — Mention the bot in any thread. Supports `repo:owner/name` syntax to specify which repo to work on. The agent replies in-thread with status updates and PR links.
- **Linear** — Comment `@openswe` on any issue. The agent reads the full issue context, reacts with 👀 to acknowledge, and posts results back as comments.
- **GitHub** — Tag `@openswe` in PR comments on agent-created PRs to have it address review feedback and push fixes to the same branch.

Each invocation creates a deterministic thread ID, so follow-up messages on the same issue or thread route to the same running agent.

### 7. Validation — Prompt-Driven

The agent is instructed to run linters, formatters, and tests before committing, and is responsible end-to-end for committing, pushing, opening/updating the draft PR, and replying in the source channel.
This is an area where you can extend Open SWE for your org: add deterministic CI checks, visual verification, or review gates as additional middleware. See the [Customization Guide](docs/CUSTOMIZATION.md#6-middleware) for how.

---

## Comparison

| Decision | Open SWE | Stripe (Minions) | Ramp (Inspect) | Coinbase (Cloudbot) |
|---|---|---|---|---|
| **Harness** | Composed (Deep Agents/LangGraph) | Forked (Goose) | Composed (OpenCode) | Built from scratch |
| **Sandbox** | Pluggable (Modal, Daytona, Runloop, etc.) | AWS EC2 devboxes (pre-warmed) | Modal containers (pre-warmed) | In-house |
| **Tools** | ~15, curated | ~500, curated per-agent | OpenCode SDK + extensions | MCPs + custom Skills |
| **Context** | AGENTS.md + issue/thread | Rule files + pre-hydration | OpenCode built-in | Linear-first + MCPs |
| **Orchestration** | Subagents + middleware | Blueprints (deterministic + agentic) | Sessions + child sessions | Three modes |
| **Invocation** | Slack, Linear, GitHub | Slack + embedded buttons | Slack + web + Chrome extension | Slack-native |
| **Validation** | Prompt-driven | 3-layer (local + CI + 1 retry) | Visual DOM verification | Agent councils + auto-merge |

---

## Features

- **Trigger from Linear, Slack, or GitHub** — mention `@openswe` in a comment to kick off a task
- **Instant acknowledgement** — reacts with 👀 the moment it picks up your message
- **Message it while it's running** — send follow-up messages mid-task and it'll pick them up before its next step
- **Run multiple tasks in parallel** — each task runs in its own isolated cloud sandbox
- **GitHub OAuth built-in** — authenticates with your GitHub account automatically
- **Opens PRs automatically** — commits changes and opens a draft PR when done, linked back to your ticket
- **Subagent support** — the agent can spawn child agents for parallel subtasks
- **Web dashboard** — a companion app (in `ui/`) for GitHub login, per-user model/profile settings, team defaults, enabled-repo and review-style management, user mappings, and an Agents chat UI

---

## Standalone GKE deployment: Kata, Agent Sandbox, LiteLLM, and KEDA

This fork can run Open SWE's API, webhook receiver, dashboard, worker harness, PostgreSQL, NATS JetStream, LiteLLM gateway, and code sandboxes on Kubernetes. It does **not** require a LangSmith deployment, a commercial sandbox account, or any Open SWE license key. The checked-in configuration uses the open-source editions of Agent Sandbox, Kata Containers, KEDA, NATS, PostgreSQL, and LiteLLM.

You still pay for GKE and model usage, and you must supply normal authentication credentials: a GitHub App plus an API key for each model provider you enable. Those are service credentials, not license keys. LiteLLM enterprise-only metering is disabled.

The following path creates a GKE Standard cluster with Intel N2 Ubuntu nodes, nested virtualization, Kata's `kata-qemu` runtime, the open-source Agent Sandbox controller, and KEDA scaling of harness workers from NATS JetStream lag.

> [!IMPORTANT]
> Google also offers a managed GKE Agent Sandbox add-on. On Standard clusters its admission policy currently requires gVisor. This guide uses the open-source Agent Sandbox controller because the requested runtime is Kata. See Google's [managed Agent Sandbox guide](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/how-install-agent-sandbox) if you prefer gVisor instead. Kata on GKE is user-managed and is not covered by Google Cloud support.

### 1. Install the command-line prerequisites

Install and authenticate:

- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install), including `gke-gcloud-auth-plugin`
- `kubectl`, [Helm 3](https://helm.sh/docs/intro/install/), and [Kustomize](https://kubectl.docs.kubernetes.io/installation/kustomize/)
- `git`, `curl`, and `openssl`

Use a Google Cloud project with billing enabled, then clone this fork and set deployment values:

```bash
export PROJECT_ID="your-gcp-project"
export REGION="us-central1"
export ZONE="us-central1-a"
export CLUSTER_NAME="openswe"
export AR_REPOSITORY="openswe"
export PLATFORM_NAMESPACE="alephat"
export SANDBOX_NAMESPACE="alephat-sandboxes"
export PLATFORM_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPOSITORY}/openswe-platform:latest"
export UI_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPOSITORY}/openswe-ui:latest"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  container.googleapis.com
```

If you use Gemini through Vertex AI instead of a Gemini API key, also enable `aiplatform.googleapis.com` and configure Workload Identity for LiteLLM. The simpler Google AI Studio API-key path is shown below.

### 2. Create the GKE cluster and install Kata Containers

Agent Sandbox maintains an [official Kata-on-GKE example](https://github.com/kubernetes-sigs/agent-sandbox/tree/main/examples/kata-gke-sandbox). Its setup script creates a zonal Standard cluster with Dataplane V2, IP aliases, nested virtualization, Ubuntu containerd, and an Intel N2 machine type; it then installs Kata and registers `RuntimeClass/kata-qemu`.

```bash
git clone --depth 1 https://github.com/kubernetes-sigs/agent-sandbox.git /tmp/agent-sandbox

(
  cd /tmp/agent-sandbox/examples/kata-gke-sandbox
  ./setup.sh \
    --cluster-name "$CLUSTER_NAME" \
    --zone "$ZONE" \
    --num-nodes 2 \
    --machine-type n2-standard-4 \
    --image-type UBUNTU_CONTAINERD
)
```

If you created the cluster separately with `--enable-nested-virtualization`, rerun the same script with `--reuse-cluster`. Do not use E2, N2D, Arm, or Container-Optimized OS nodes for this Kata path. Choose a zone where N2 machines and nested virtualization are available.

Verify cluster access and Kata:

```bash
gcloud container clusters get-credentials "$CLUSTER_NAME" --zone "$ZONE"
kubectl get nodes -o wide
kubectl get runtimeclass kata-qemu
kubectl -n kube-system rollout status daemonset/kata-deploy --timeout=10m
```

The upstream example currently pins Kata `3.2.0`. Review and pin a newer tested release deliberately before upgrading; changing the runtime on a live sandbox node pool should be treated as an infrastructure upgrade.

### 3. Install Agent Sandbox and the Kata sandbox template

This fork calls the `v1beta1` Agent Sandbox APIs. Release `v0.5.5` serves `v1beta1` and includes the extensions controller used by `SandboxTemplate`:

```bash
export AGENT_SANDBOX_VERSION="v0.5.5"

kubectl apply -f \
  "https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${AGENT_SANDBOX_VERSION}/sandbox-with-extensions.yaml"

kubectl wait --for=condition=Established crd/sandboxes.agents.x-k8s.io --timeout=2m
kubectl wait --for=condition=Established \
  crd/sandboxtemplates.extensions.agents.x-k8s.io --timeout=2m
kubectl apply -f deploy/k8s/agent-sandbox-template.yaml

kubectl get runtimeclass kata-qemu
kubectl -n "$SANDBOX_NAMESPACE" get sandboxtemplate python-runtime-template
```

The checked-in template uses `runtimeClassName: kata-qemu`, the Agent Sandbox Python toolbox on port `8888`, a non-root user, no service-account token, dropped capabilities, and resource limits. The harness creates a direct `Sandbox` from this template for every task; a warm pool is not required by this provider.

### 4. Install KEDA

KEDA scales the harness deployment from zero to fifty workers based on the pending message count for the durable `harness-workers` consumer on the `TASKS` JetStream stream. One harness Pod processes one task at a time.

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm upgrade --install keda kedacore/keda \
  --namespace keda \
  --create-namespace \
  --version 2.20.0

kubectl -n keda rollout status deployment/keda-operator --timeout=5m
kubectl get crd scaledobjects.keda.sh
```

The NATS JetStream scaler is included in KEDA; no separate scaler installation is required. The `ScaledObject` is applied after Open SWE starts once, so the API has created the streams and the initial harness has created its durable consumer.

### 5. Deploy standalone LiteLLM with OpenAI, Anthropic, and Gemini routes

Create the platform namespace and LiteLLM secrets. Omit a provider key only after removing its corresponding model entry from `deploy/k8s/litellm-values.yaml`.

```bash
kubectl create namespace "$PLATFORM_NAMESPACE" \
  --dry-run=client -o yaml | kubectl apply -f -

read -rsp "OpenAI API key: " OPENAI_API_KEY; echo
read -rsp "Anthropic API key: " ANTHROPIC_API_KEY; echo
read -rsp "Gemini API key: " GEMINI_API_KEY; echo

export LITELLM_MASTER_KEY="sk-$(openssl rand -hex 24)"
export LITELLM_DB_PASSWORD="$(openssl rand -hex 24)"

kubectl -n "$PLATFORM_NAMESPACE" create secret generic litellm-secrets \
  --from-literal=masterkey="$LITELLM_MASTER_KEY"
kubectl -n "$PLATFORM_NAMESPACE" create secret generic litellm-provider-keys \
  --from-literal=OPENAI_API_KEY="$OPENAI_API_KEY" \
  --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  --from-literal=GEMINI_API_KEY="$GEMINI_API_KEY"
kubectl -n "$PLATFORM_NAMESPACE" create secret generic litellm-postgres \
  --from-literal=postgres-password="$LITELLM_DB_PASSWORD" \
  --from-literal=password="$LITELLM_DB_PASSWORD"

helm upgrade --install alephat-platform \
  oci://ghcr.io/berriai/litellm-helm \
  --namespace "$PLATFORM_NAMESPACE" \
  --version 1.90.2 \
  --values deploy/k8s/litellm-values.yaml

kubectl -n "$PLATFORM_NAMESPACE" rollout status \
  deployment/alephat-platform-litellm --timeout=10m
```

The values file creates logical aliases that match the dashboard model IDs and routes them to OpenAI, Anthropic, and Gemini. Provider model names change over time and differ by account; update each `litellm_params.model` to a model enabled for your account. `DEFAULT_MODEL` in `deploy/k8s/configmap.yaml` must match one of the `model_name` aliases. See the official [LiteLLM provider examples](https://docs.litellm.ai/) and [Kubernetes production guide](https://docs.litellm.ai/docs/proxy/deploy).

This getting-started deployment gives LiteLLM its own bundled PostgreSQL instance. Open SWE uses a different PostgreSQL StatefulSet in the next step. For production, use separate Cloud SQL databases and Redis if you run multiple LiteLLM replicas; do not share schemas or credentials between LiteLLM and Open SWE.

Test the gateway from inside the cluster with any configured alias:

```bash
export MODEL_ALIAS="gemini-5.6-flash"

kubectl -n "$PLATFORM_NAMESPACE" run litellm-smoke \
  --rm -i --restart=Never --image=curlimages/curl -- \
  curl -fsS http://alephat-platform-litellm:4000/v1/chat/completions \
    -H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"${MODEL_ALIAS}\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with: litellm-ok\"}]}"
```

### 6. Create the GitHub App and Kubernetes secrets

Create and install a GitHub App by following [the GitHub App permissions guide](docs/INSTALLATION.md#3-create-a-github-app). For the port-forwarded dashboard, configure:

- Homepage URL: `http://127.0.0.1:18080`
- Callback URL: `http://127.0.0.1:18080/dashboard/api/auth/callback`
- Repository permissions: Contents, pull requests, issues, checks, and workflows as described in the linked guide
- Webhook secret: a random value from `openssl rand -hex 32`

Collect the App ID, client ID, client secret, generated private-key `.pem` file, and installation ID. Install the app on every repository that Open SWE may clone or modify.

```bash
export GITHUB_APP_ID="123456"
export GITHUB_APP_CLIENT_ID="Iv1.example"
export GITHUB_APP_CLIENT_SECRET="replace-me"
export GITHUB_APP_INSTALLATION_ID="12345678"
export GITHUB_APP_PRIVATE_KEY_FILE="/absolute/path/to/github-app.private-key.pem"
export GITHUB_WEBHOOK_SECRET="$(openssl rand -hex 32)"
export OPENSWE_DB_PASSWORD="$(openssl rand -hex 24)"
export PLATFORM_API_TOKEN="$(openssl rand -hex 32)"
export PLATFORM_JWT_SECRET="$(openssl rand -hex 32)"
export DASHBOARD_JWT_SECRET="$(openssl rand -hex 32)"
export TOKEN_ENCRYPTION_KEY="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n')"

kubectl -n "$PLATFORM_NAMESPACE" create secret generic openswe-postgres \
  --from-literal=password="$OPENSWE_DB_PASSWORD"
kubectl -n "$PLATFORM_NAMESPACE" create secret generic openswe-secrets \
  --from-literal=PLATFORM_API_TOKEN="$PLATFORM_API_TOKEN" \
  --from-literal=PLATFORM_JWT_SECRET="$PLATFORM_JWT_SECRET" \
  --from-literal=GITHUB_WEBHOOK_SECRET="$GITHUB_WEBHOOK_SECRET"
kubectl -n "$PLATFORM_NAMESPACE" create secret generic openswe-oauth \
  --from-literal=GITHUB_APP_ID="$GITHUB_APP_ID" \
  --from-literal=GITHUB_APP_CLIENT_ID="$GITHUB_APP_CLIENT_ID" \
  --from-literal=GITHUB_APP_CLIENT_SECRET="$GITHUB_APP_CLIENT_SECRET" \
  --from-literal=GITHUB_APP_INSTALLATION_ID="$GITHUB_APP_INSTALLATION_ID" \
  --from-file=GITHUB_APP_PRIVATE_KEY="$GITHUB_APP_PRIVATE_KEY_FILE" \
  --from-literal=DASHBOARD_JWT_SECRET="$DASHBOARD_JWT_SECRET" \
  --from-literal=TOKEN_ENCRYPTION_KEY="$TOKEN_ENCRYPTION_KEY"
```

For production, create these secrets with Secret Manager plus External Secrets or the Secrets Store CSI driver instead of putting values in shell history. Never commit rendered Secrets, private keys, or API keys.

### 7. Build and push the Open SWE images

Create an Artifact Registry Docker repository and submit both builds to Cloud Build:

```bash
gcloud artifacts repositories describe "$AR_REPOSITORY" \
  --location "$REGION" >/dev/null 2>&1 || \
gcloud artifacts repositories create "$AR_REPOSITORY" \
  --repository-format docker \
  --location "$REGION"

gcloud builds submit . \
  --config cloudbuild.platform.yaml \
  --substitutions="_PLATFORM_IMAGE=${PLATFORM_IMAGE}"
gcloud builds submit . \
  --config cloudbuild.ui.yaml \
  --substitutions="_UI_IMAGE=${UI_IMAGE}"
```

Point Kustomize at those images without editing every Deployment:

```bash
(
  cd deploy/k8s
  kustomize edit set image \
    "us-central1-docker.pkg.dev/neurolonicweb/neurolonic-web-app/openswe-platform=${PLATFORM_IMAGE}" \
    "us-central1-docker.pkg.dev/neurolonicweb/neurolonic-web-app/openswe-ui=${UI_IMAGE}"
)
```

If you use a different LiteLLM release or logical model name, update `deploy/k8s/litellm-values.yaml` and `deploy/k8s/configmap.yaml` before applying the manifests.

### 8. Deploy Open SWE and enable KEDA scaling

The RBAC and NetworkPolicy manifests are separate because they target `alephat-sandboxes`, while the Kustomize base applies its namespace transformer to the `alephat` platform resources.

```bash
kubectl apply -f deploy/k8s/agent-sandbox-rbac.yaml
kubectl apply -f deploy/k8s/agent-sandbox-networkpolicy.yaml
kubectl apply -k deploy/k8s

kubectl -n "$PLATFORM_NAMESPACE" wait \
  --for=condition=complete job/openswe-migrate --timeout=5m
kubectl -n "$PLATFORM_NAMESPACE" rollout status deployment/openswe-api --timeout=10m
kubectl -n "$PLATFORM_NAMESPACE" rollout status deployment/openswe-webhook --timeout=10m
kubectl -n "$PLATFORM_NAMESPACE" rollout status deployment/openswe-ui --timeout=10m
kubectl -n "$PLATFORM_NAMESPACE" rollout status deployment/openswe-harness --timeout=10m

kubectl apply -f deploy/k8s/harness-keda.yaml
kubectl -n "$PLATFORM_NAMESPACE" get scaledobject openswe-harness
kubectl -n "$PLATFORM_NAMESPACE" get hpa
```

The platform base intentionally does not include `harness-keda.yaml`: installing the base must remain possible before KEDA's CRDs exist. Once the `ScaledObject` is active, the harness can scale to zero while idle and scale out as tasks accumulate.

Check all components:

```bash
kubectl -n "$PLATFORM_NAMESPACE" get pods,svc
kubectl -n "$SANDBOX_NAMESPACE" get sandboxtemplate
kubectl -n keda get pods
kubectl -n "$PLATFORM_NAMESPACE" logs deployment/openswe-harness --tail=100
```

### 9. Open the UI and run an end-to-end coding task

Start the port forward and keep it running:

```bash
kubectl -n "$PLATFORM_NAMESPACE" port-forward service/openswe-ui 18080:80
```

Open [http://127.0.0.1:18080](http://127.0.0.1:18080), sign in with GitHub, select a repository installed for the GitHub App, and submit a small task such as:

```text
Add a short "Testing notes" section to README.md, inspect the diff, and report the changed files.
```

In another terminal, watch KEDA activate the harness and Agent Sandbox create a Kata-backed sandbox:

```bash
kubectl -n "$PLATFORM_NAMESPACE" get deployment openswe-harness -w
kubectl -n "$SANDBOX_NAMESPACE" get sandbox,pod -w
```

While the task is running, prove that its Pod uses Kata and that commands execute there:

```bash
export SANDBOX_POD="$(kubectl -n "$SANDBOX_NAMESPACE" get pod \
  -l app.kubernetes.io/name=alephat-python-sandbox \
  -o jsonpath='{.items[0].metadata.name}')"

kubectl -n "$SANDBOX_NAMESPACE" get pod "$SANDBOX_POD" \
  -o jsonpath='{.spec.runtimeClassName}{"\n"}'
kubectl -n "$SANDBOX_NAMESPACE" exec "$SANDBOX_POD" -- uname -r
kubectl -n "$SANDBOX_NAMESPACE" exec "$SANDBOX_POD" -- git diff --stat
```

The first command must print `kata-qemu`. A successful task should show model events in the UI, command/tool events from the sandbox, and a final response. After the cooldown period, KEDA should return the harness to zero replicas if no tasks remain.

### 10. Production hardening and cleanup

The checked-in manifests are a reproducible standalone starting point, not an HA production topology:

- `deploy/k8s/postgresql.yaml` gives Open SWE a dedicated PostgreSQL StatefulSet but currently uses `emptyDir`; replace it with a PVC or Cloud SQL before storing production data.
- The LiteLLM chart's standalone PostgreSQL is also a getting-started option. Use a separate managed database, backups, and Redis for multi-replica LiteLLM.
- Add HTTPS Ingress, DNS, and managed certificates. Then update `DASHBOARD_BASE_URL`, `DASHBOARD_API_BASE_URL`, CORS origins, and the GitHub callback/webhook URLs to the public HTTPS origin.
- Restrict GitHub App repository access, configure NetworkPolicies and egress controls, set ResourceQuotas in the sandbox namespace, and enable GKE node autoscaling for the Kata pool.
- Pin container, Helm chart, Agent Sandbox, and Kata versions and test upgrades in a non-production cluster.

Delete the cluster when it is no longer needed:

```bash
gcloud container clusters delete "$CLUSTER_NAME" --zone "$ZONE" --quiet
```

References: [GKE Agent Sandbox](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/machine-learning/agent-sandbox), [Agent Sandbox releases](https://github.com/kubernetes-sigs/agent-sandbox/releases), [Kata installation](https://github.com/kata-containers/kata-containers/blob/main/docs/installation.md), [KEDA installation](https://keda.sh/docs/2.20/deploy/), and [KEDA NATS JetStream scaler](https://keda.sh/docs/2.20/scalers/nats-jetstream/).

---

## Getting Started

- **[Installation Guide](docs/INSTALLATION.md)** — local dev (backend + dashboard), GitHub App creation, LangSmith, Linear/Slack/GitHub triggers, and production deployment
- **[Customization Guide](docs/CUSTOMIZATION.md)** — swap the sandbox, model, tools, triggers, system prompt, and middleware for your org

## License

MIT
