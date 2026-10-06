# Deployment Guide

This folder contains everything needed to containerize ADK Assistant and
run it locally with rootless Podman, or deploy it to OpenShift — either as a
plain (unauthenticated) app or behind an OpenShift OAuth-proxy sidecar so only
authenticated cluster users can reach it.

```
deployment/
├── Containerfile                           UBI9 Python 3.12 image (Google ADK + FastAPI)
├── pvc.yaml                                3 PVCs: agent / input / output
├── secret-api-keys.yaml                    Anthropic / OpenAI / OpenRouter keys
├── deployment.yaml                         Basic (no-auth) Deployment
├── service.yaml                            Basic Service
├── route.yaml                              Basic Route (edge TLS)
├── oauth-serviceaccount.yaml                OAuth ServiceAccount
├── oauth-secret-proxy.yaml                 oauth-proxy cookie session secret
├── oauth-deployment.yaml                   App + oauth-proxy sidecar Deployment
├── oauth-service.yaml                      OAuth Service (auto TLS, port 4443)
├── oauth-route.yaml                        OAuth Route (reencrypt TLS)
├── adk-assistant-template.yaml        Catalog template — basic variant
├── adk-assistant-oauth-template.yaml   Catalog template — OAuth variant
├── gateway-*.yaml (6 files)                 Shared multi-instance gateway (see §6, deploy once)
├── adk-assistant-gateway-template.yaml Catalog template — named instance behind the gateway
└── README.md                               This file
```

---

## 1. Build and push the image

The `Containerfile` lives in `deployment/`, but it `COPY`s files (`pyproject.toml`,
`adk_core.py`, `web_app.py`, `templates/`, `sample-jobs/`, ...) that live at the
project root — so the build **context** must still be the project root. Point `-f`
at the Containerfile's path while keeping `.` (the project root) as the context:

```bash
cd /root/adk-assistant
podman build -t quay.io/kenghua_yeo/adk-assistant:v1 -f deployment/Containerfile .
podman login quay.io
podman push quay.io/kenghua_yeo/adk-assistant:v1
```

---

## 2. Run locally with rootless Podman

Uses named Podman volumes (not bind mounts) so file ownership inside the
container (UID 1001) never has to match your host user.

```bash
# One-time: create the named volumes
podman volume create adk-agent
podman volume create adk-input
podman volume create adk-output

# Run the container
podman run -d --name adk-assistant \
  -p 8081:8081 \
  -v adk-agent:/app/agent \
  -v adk-input:/app/input \
  -v adk-output:/app/output \
  -e API_PROVIDER=openai-compatible \
  -e MODEL=llama3.2 \
  -e OPENAI_BASE_URL=http://host.containers.internal:11434/v1 \
  -e ALLOW_SHELL=true \
  quay.io/kenghua_yeo/adk-assistant:v1
```

Open [http://localhost:8081](http://localhost:8081). To use a hosted provider
instead, add e.g. `-e API_PROVIDER=anthropic -e ANTHROPIC_API_KEY=sk-...` (or
`openai` / `openrouter` with their matching `*_API_KEY`).
For Gemini use `-e API_PROVIDER=gemini -e MODEL=gemini-2.5-flash -e GOOGLE_API_KEY=...`.
For Vertex AI use `-e API_PROVIDER=vertex -e GOOGLE_CLOUD_PROJECT=<project>` and make Application
Default Credentials available in the container, e.g.
`-v $HOME/.config/gcloud:/opt/app-root/src/.config/gcloud:ro,Z` (or `-e GOOGLE_APPLICATION_CREDENTIALS=...`
pointing at a mounted service-account file).

Useful commands:

```bash
podman logs -f adk-assistant      # tail logs
podman stop adk-assistant         # stop
podman start adk-assistant        # restart (volumes persist)
podman rm -f adk-assistant        # remove the container (volumes persist)

# Inspect or reset a volume's contents
podman volume inspect adk-agent
podman volume rm adk-agent adk-input adk-output   # wipe all data
```

To run with [Podman Compose](https://github.com/containers/podman-compose) or
generate a systemd quadlet instead, `podman generate systemd` can convert the
running container above into a `.container`/`.service` unit.

---

## 3. Deploy to OpenShift — basic (no authentication)

Anyone who can reach the Route can use the app. Good for a sandboxed/demo
project namespace.

```bash
oc new-project adk-assistant   # or: oc project <existing-project>

# Edit the placeholder values first:
#   deployment/secret-api-keys.yaml  -> your API key(s)
#   deployment/deployment.yaml       -> image / env vars if you customized them

oc apply -f deployment/pvc.yaml
oc apply -f deployment/secret-api-keys.yaml
oc apply -f deployment/deployment.yaml
oc apply -f deployment/service.yaml
oc apply -f deployment/route.yaml

oc get route adk-assistant   # prints the public URL
```

---

## 4. Deploy to OpenShift — OAuth-protected

Puts an `oauth-proxy` sidecar in front of the app so only users who can log
in to the cluster (and, optionally, who hold a specific RBAC permission) can
reach it. This is the standard OpenShift "protect an app with OAuth" pattern.

```bash
oc new-project adk-assistant   # or: oc project <existing-project>

# Edit the placeholder values first:
#   deployment/secret-api-keys.yaml   -> your API key(s)
#   deployment/oauth-secret-proxy.yaml -> generate with: openssl rand -base64 32

oc apply -f deployment/pvc.yaml
oc apply -f deployment/secret-api-keys.yaml
oc apply -f deployment/oauth-secret-proxy.yaml
oc apply -f deployment/oauth-serviceaccount.yaml
oc apply -f deployment/oauth-deployment.yaml
oc apply -f deployment/oauth-service.yaml
oc apply -f deployment/oauth-route.yaml

# Required one-time step so the oauth-proxy can validate tokens against the
# cluster's OAuth server (needs cluster-admin or equivalent delegated rights):
oc adm policy add-cluster-role-to-user system:auth-delegator \
  -z adk-assistant -n adk-assistant

oc get route adk-assistant-oauth   # prints the public URL
```

By default any authenticated cluster user can log in. To restrict access to
users who hold a specific permission (e.g. `get pods` in this project),
uncomment the `--openshift-sar=...` line in `oauth-deployment.yaml`'s
`oauth-proxy` container args and re-apply.

Service accounts in OpenShift/Kubernetes are namespace-scoped resources:
- Multiple applications in the same project can use the same service account by reference in
  the deployment's field `serviceAccountName`.
- If multiple projects need the same permissions, create identically-named service accounts in
  each and grant them the same roles.

---

## 5. Deploy via the OpenShift catalog ("click to deploy")

Load one or both templates into the catalog of a project (or `openshift` for
cluster-wide visibility to all projects), then deploy from the web console.

```bash
# Make templates available in just this project:
oc apply -f deployment/adk-assistant-template.yaml
oc apply -f deployment/adk-assistant-oauth-template.yaml

# Or cluster-wide, in the shared "openshift" namespace (needs cluster-admin):
oc apply -n openshift -f deployment/adk-assistant-template.yaml
oc apply -n openshift -f deployment/adk-assistant-oauth-template.yaml
```

Then in the OpenShift web console: **+Add → All services / From Catalog**,
search for "ADK Assistant", pick the basic or OAuth tile, fill in the
form (image, provider, model, API key(s), storage sizes), and click
**Create**. Both templates create their own Secret for API keys and PVCs
from the form inputs — you don't need to `oc apply` `secret-api-keys.yaml`
or `pvc.yaml` separately when deploying this way. The OAuth template also
auto-generates the proxy's session secret for you.

If you used the OAuth template, you still need the one-time cluster-admin
step from section 4:

```bash
oc adm policy add-cluster-role-to-user system:auth-delegator \
  -z <APP_NAME> -n <project>
```

---

## 6. Multiple named instances behind one shared URL

Want several assistant instances — e.g. one per workshop attendee — all reachable
under **one** shared Route/hostname, as `https://<gateway-host>/<assistant-name>/`,
each with its own isolated agent/input/output storage? Use the gateway + named-instance
template instead of sections 3–5 above.

**How it works:** one shared gateway (`oauth-proxy` + a small `nginx` sidecar) is deployed
**once** per project. It terminates OAuth login, then nginx resolves `/<assistant-name>/...`
to that instance's own Service **dynamically, by DNS, at request time** (not from a static
config) and strips the `/<assistant-name>` prefix before forwarding — so the app itself
needs no changes and never knows it's behind a path prefix. Because resolution is dynamic,
deploying a new named instance requires **zero changes to the gateway** — it's found
automatically as soon as its Service exists.

```bash
oc new-project adk-assistant   # or: oc project <existing-project>

# One-time: deploy the shared gateway
# Edit deployment/gateway-secret-proxy.yaml first: generate with openssl rand -base64 32
oc apply -f deployment/gateway-serviceaccount.yaml
oc apply -f deployment/gateway-secret-proxy.yaml
oc apply -f deployment/gateway-configmap.yaml
oc apply -f deployment/gateway-deployment.yaml
oc apply -f deployment/gateway-service.yaml
oc apply -f deployment/gateway-route.yaml

# Required one-time step, same as section 4:
oc adm policy add-cluster-role-to-user system:auth-delegator \
  -z adk-gateway -n adk-assistant

oc get route adk-gateway   # the one shared URL for every instance
```

Then deploy as many named instances as you like via the catalog template — each one only
needs `ASSISTANT_NAME` plus the usual provider/model/storage parameters:

```bash
oc apply -f deployment/adk-assistant-gateway-template.yaml
# or cluster-wide: oc apply -n openshift -f deployment/adk-assistant-gateway-template.yaml
```

In the web console: **+Add → From Catalog**, search "ADK Assistant (gateway)",
set `ASSISTANT_NAME` (e.g. `workshop-alice`), fill in the rest, **Create**. It's then reachable
at `https://<gateway-host>/workshop-alice/` — no Route of its own, no extra gateway step.
Deploy another with a different `ASSISTANT_NAME` and it's immediately reachable the same way.

**Notes / limitations:**
- `ASSISTANT_NAME` must be a valid DNS label (lowercase alphanumeric + hyphens, starting with
  a letter) — it becomes both the Kubernetes resource name prefix and the URL path segment.
- The gateway only resolves instances in **its own namespace/project**.
- `gateway-deployment.yaml`'s `NGINX_RESOLVER` env var defaults to OpenShift's in-cluster DNS
  (`dns-default.openshift-dns.svc.cluster.local`); on vanilla Kubernetes, change it to
  `kube-dns.kube-system.svc.cluster.local`.
- A request to `/<assistant-name>` with no trailing slash gets a `301` redirect to
  `/<assistant-name>/` first (so the app's relative links resolve correctly).

---

## Environment variable reference

| Variable             | Default             | Notes                                                        |
|----------------------|----------------------|---------------------------------------------------------------|
| `AGENT_DIR`          | `/app/agent`         | Baked into the image; override only for custom layouts.       |
| `INPUT_DIR`          | `/app/input`          | "                                                               |
| `OUTPUT_DIR`         | `/app/output`         | "                                                               |
| `JOBS_DIR`           | `/app/sample-jobs`    | Bundled, read-only Job Pack library.                          |
| `API_PROVIDER`       | `openai-compatible`  | One of `openai-compatible`, `gemini`, `vertex`, `anthropic`, `openai`, `openrouter`.|
| `MODEL`              | `llama3.2`            | Model name/ID for the selected provider.                      |
| `MAX_TURNS`          | `50`                  | Hard cap on model calls per run (loop guard).                 |
| `MAX_OUTPUT_TOKENS`  | `16384`               | Per-response output token cap.                                |
| `ALLOW_SHELL`        | `true` (image) / `false` (OpenShift manifests) | Whether the agent's shell tool is enabled. |
| `SHELL_TIMEOUT`      | `60`                  | Seconds before a shell tool call is killed.                   |
| `SHELL_GUARD`        | `on`                  | `off` disables the destructive-command deny-list.             |
| `ALLOW_PRIVATE_FETCH`| `false`               | `true` lets `web_fetch` reach private/loopback/link-local addresses (SSRF guard is on by default). |
| `ALLOW_MCP_STDIO`    | follows `ALLOW_SHELL` | Allow stdio MCP servers from `agent/mcp.json` (they spawn local processes). Remote HTTP/SSE servers are always allowed. |
| `LLM_TIMEOUT` / `LLM_RETRIES` | `120` / `1`  | Per-request timeout (s) and retries for LiteLLM providers.    |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | —            | Enables OpenTelemetry export (image must be built with the `otel` extra). |
| `PORT`               | `8081`                | Flask listen port.                                             |
| `HOST`               | `0.0.0.0` (basic) / `127.0.0.1` (OAuth) | OAuth variant binds the app to localhost only. |
| `GOOGLE_API_KEY`     | —                     | Required only if `API_PROVIDER=gemini` (`GEMINI_API_KEY` also accepted). |
| `GOOGLE_CLOUD_PROJECT` | —                   | Required only if `API_PROVIDER=vertex`; needs Application Default Credentials in the pod. |
| `GOOGLE_CLOUD_LOCATION` | `us-central1`      | Vertex AI region.                                             |
| `ANTHROPIC_API_KEY`  | —                     | Required only if `API_PROVIDER=anthropic`.                    |
| `OPENAI_API_KEY`     | —                     | Required only if `API_PROVIDER=openai`.                       |
| `OPENAI_COMPATIBLE_API_KEY` | —              | Optional bearer token for the `openai-compatible` endpoint (separate from `OPENAI_API_KEY`). |
| `OPENROUTER_API_KEY` | —                     | Required only if `API_PROVIDER=openrouter`.                   |
| `OPENAI_BASE_URL`    | —                     | Used by `openai-compatible` (e.g. local Ollama/vLLM); no key needed for this provider. |

## Persistent volume reference

| PVC                                 | Mount         | Default size | Purpose                                   |
|--------------------------------------|---------------|--------------|--------------------------------------------|
| `adk-assistant-agent-pvc`       | `/app/agent`  | 1Gi          | `instruction.md`, skills, agent-authored files. |
| `adk-assistant-input-pvc`       | `/app/input`  | 5Gi          | Files for the agent to process.           |
| `adk-assistant-output-pvc`      | `/app/output` | 5Gi          | Files the agent writes out (read-only via the UI). |

`sample-jobs/` is baked into the image (not a volume) and is never written
to. `.job_history.json` lives at `/app/.job_history.json` on the container's
ephemeral root filesystem — it is **not** backed by a PVC, so job history
resets whenever the pod restarts or is rescheduled.

## Updating the image

```bash
cd /root/adk-assistant
podman build -t quay.io/kenghua_yeo/adk-assistant:v2 -f deployment/Containerfile .
podman push quay.io/kenghua_yeo/adk-assistant:v2

# OpenShift — basic variant
oc set image deployment/adk-assistant \
  adk-assistant=quay.io/kenghua_yeo/adk-assistant:v2

# OpenShift — OAuth variant
oc set image deployment/adk-assistant-oauth \
  adk-assistant=quay.io/kenghua_yeo/adk-assistant:v2

# Podman
podman pull quay.io/kenghua_yeo/adk-assistant:v2
podman rm -f adk-assistant
podman run -d --name adk-assistant ... quay.io/kenghua_yeo/adk-assistant:v2
```
