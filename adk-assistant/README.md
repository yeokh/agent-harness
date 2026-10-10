# ADK Assistant

A single FastAPI + **[Google ADK](https://github.com/google/adk-python)** (Agent Development Kit 2.x)
application that runs an AI agent in two modes against the same `agent/` / `input/` / `output/` folders.
It is an experimental tool for trying out agentic processing: give the agent instructions and files, then
watch it work interactively or hand it a job and let it run unattended.

| Mode | What it's for | Driven by |
|------|---------------|-----------|
| **Chat** | Ongoing, multi-turn conversation. You stay in the loop, directing the AI turn by turn. | You, one message at a time |
| **Batch** | One-shot autonomous run. The AI reads `instruction.md` + `input/`, works unattended, and writes results to `output/`. | `instruction.md` alone (no chat input) |

Both modes share the same system prompt (`agent/instruction.md`), the same scoped tool set, the same
guardrails and the same three folders — switch between them from one tab bar without restarting the server.

Supports six providers out of the box: Gemini (API key), Gemini on Vertex AI, Anthropic, OpenAI, OpenRouter,
and locally hosted models via Ollama or vLLM. The default provider is `openai-compatible` (local models) — no
API key required to get started.

## What's different from pydantic-assistant

Same UI, folder model, REST API, Job Packs and deployment variants — rebuilt on ADK, plus:

- **ADK runtime** — `LlmAgent` + `Runner` with an in-memory ADK session for Chat (history lives in the ADK
  session; Reset starts a new one) and a throw-away session per Batch run.
- **Gemini / Vertex AI** natively; Anthropic, OpenAI, OpenRouter and Ollama/vLLM through ADK's LiteLLM wrapper.
- **Skills as an ADK `SkillToolset`** — `agent/*.md` skills are discoverable on demand (`list_skills` /
  `load_skill`) instead of only via the `/skills` chat command (which still works).
- **MCP tools** — declare MCP servers in `agent/mcp.json` (see below).
- **Guardrails** implemented as ADK before/after tool callbacks — destructive shell-command deny-list, SSRF
  protection for `web_fetch`, and a prompt-injection tripwire on untrusted tool results.
- **Observability** — per-tool timing in the Batch log, token usage, best-effort cost estimate, guardrail
  counters in the Batch metrics card, and optional OpenTelemetry export (ADK emits the spans).
- **FastAPI** instead of Flask; chat turns and batch runs execute on the server's event loop (async tools,
  true cancellation) rather than in worker threads.
- Shell and `web_fetch` tools are async; LLM requests have a timeout so an unreachable endpoint fails the run
  instead of hanging it.

## Requirements

- **Python 3.11 or later** (3.12 recommended)
- pip / uv

## Quick Start

```bash
uv venv --python 3.12 .venv && source .venv/bin/activate   # or: python3.12 -m venv .venv
uv pip install -e .                                         # or: pip install -e .

# Defaults to the local "openai-compatible" provider (Ollama/vLLM) — no key needed.
# To use a hosted provider instead, set its key first (or enter it later in the web UI):
export API_PROVIDER=gemini
export GOOGLE_API_KEY="..."

python web_app.py
# Open http://localhost:8081
```

Tests (scripted fake model, no network or keys needed): `uv pip install -e '.[dev]' && pytest`.

## Architecture

```
Browser (index.html)
  |  HTTP + SSE
  v
web_app.py --------- FastAPI REST API: session, files, settings, SSE streams
  |                  for both the Chat turn loop and the Batch run loop
  |  import
  v
adk_core.py -------- ADK core, shared by both modes:
  |                    _build_model()        -> Gemini | LiteLlm instance for the provider
  |                    _make_tools()         -> scoped Python functions
  |                    load_skills()         -> SkillToolset from agent/*.md
  |                    load_mcp_toolsets()   -> McpToolset per server in agent/mcp.json
  |                    build_system_prompt() -> system prompt from instruction.md
  |                    RunMonitor            -> before/after tool callbacks (guardrails + metrics)
  v
google.adk LlmAgent + Runner.run_async()  (StreamingMode.SSE, max_llm_calls = MAX_TURNS)
  |  yields Events: partial text, function calls, function responses, usage
  v
JSON SSE events -> browser (chat bubbles in Chat tab, terminal lines in Batch tab)
```

The AI interacts with the world only through scoped tools (any of which can be disabled individually
via the Tools dialog, in either mode):

| Tool | Access | Description |
|------|--------|-------------|
| `list_agent_files` | Read | List files in `agent/` (`mcp.json` is hidden from the model) |
| `read_agent_file` | Read | Read a file from `agent/` |
| `list_input_files` | Read | List files in `input/` |
| `read_input_file` | Read | Read a file from `input/` (wrapped as untrusted data) |
| `write_output` | Write | Write a file to `output/` |
| `append_output` | Write | Append to a file in `output/` |
| `list_output_files` | Read | List files in `output/` |
| `run_command` | System | Execute a shell command (cwd = `output/`) |
| `web_fetch` | Web | Fetch an HTTP/HTTPS URL |
| `skills` | Extension | ADK `SkillToolset` over `agent/*.md` — `list_skills`, `load_skill`, … |
| `mcp` | Extension | Tools from the MCP servers in `agent/mcp.json` |

## Folder Model

| Folder | Who writes | Contents |
|--------|-----------|----------|
| `agent/` | You (Agent Files panel) | `instruction.md` (system prompt), optional skill `.md` files, optional `mcp.json` |
| `input/` | You (upload, new, or drag-and-drop) | Any documents, data files, or reference material for the AI to read |
| `output/` | The AI agent | Result files produced by Chat or Batch runs, plus `agent.log` for Batch runs |

## Chat Mode

Conversational and incremental — nothing happens until you type a message.

- **On startup (and on every reset)** — the AI introduces itself with a short `[AI]` welcome message
  explaining the Agent/Input/Output folder model and that the same instructions can be run as a Batch job.
  `instruction.md`, if present, is then loaded as a `[You]` message.
- **Sending a message** — the AI responds in a streaming chat bubble; tool calls are shown inline
  (collapsed by default, click to expand). Guardrail notices appear as a toast.
- **`/skills` or `/skill`** — loads all skill `.md` files from `agent/` into the conversation context as
  a `[You]` message. Independently of this command, the model can discover and load skills itself through
  the `skills` toolset (disable it in the Tools dialog to get the old "you control when skills load" behaviour).
- **Stop button** — cancels the current AI turn mid-stream.
- **Reset** — clears the conversation (starts a new ADK session) while keeping the current instruction.

## Batch Mode

Autonomous and unattended — one click runs the agent end-to-end against whatever is currently in
`agent/` and `input/`.

- **Run** — starts a fresh agent run. The agent reads `instruction.md`, lists/reads `input/` as needed,
  and writes everything to `output/`. No chat turns, no user steering mid-run.
- **Live terminal** — tool calls (with duration), tool results, guardrail events and assistant text stream
  into a dark terminal view over SSE, colour-coded by event type.
- **Metrics** — after each run: duration, tool calls, model calls, tokens, estimated cost (hosted providers
  only), guardrail blocks / injection flags and output file count, in a chip and summary card.
- **Stop** — cancels the in-progress run.
- **Job history** — the last 20 batch runs are listed as compact cards, persisted to `.job_history.json`
  at the project root (override with `JOB_HISTORY_FILE`).
- Batch runs do **not** touch the Chat conversation history, and Chat turns do **not** appear in the
  Batch job history.
- **Endless-loop protection** — the system prompt tells the agent this is a one-shot run with a hard
  `MAX_TURNS` budget and to stop as soon as the task looks complete. As a hard backstop, ADK's
  `max_llm_calls` is set to `MAX_TURNS`; the run is then marked `error` with a clear explanation, files
  already written to `output/` are preserved, and the partial counts are recorded in the job history.

### Job Pack Loader

A **Job Pack** is a ready-made `agent/` + `input/` pair bundled under the `JOBS_DIR` library folder
(default `./sample-jobs`), used to quickly stage a Batch run without manually uploading files. A pack is
valid if it contains at least `agent/instruction.md`. **Load** copies the pack's `agent/` and `input/` trees
into the working folders, replacing what is there (after a confirmation prompt), and resets the Chat session.
Review/edit `instruction.md` if needed, then click **Run**. Two top-level reference skills,
`SKILL-sensitive-info.md` and `SKILL-web-browser.md`, sit alongside the packs for manual copying into a
pack's `agent/` folder.

## Skills

Every `.md` file in `agent/` other than `instruction.md` is a skill. YAML frontmatter (`name`,
`description`) is used when present; otherwise the name comes from the filename (`SKILL-foo.md` → `foo`)
and the description from the first line. The model sees the skill list through ADK's `SkillToolset` and
loads a skill's full text only when relevant.

## MCP Servers

Create `agent/mcp.json` (Claude-Desktop-style). `${VAR}` references are expanded from the environment, so
secrets need not live in the file:

```json
{
  "mcpServers": {
    "docs":  {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer ${DOCS_TOKEN}"}},
    "old":   {"url": "https://example.com/sse", "transport": "sse"},
    "files": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/app/input"],
              "tool_filter": ["read_file", "list_directory"]}
  }
}
```

- Remote servers use streamable HTTP by default (`"transport": "sse"` for legacy SSE).
- **stdio servers launch local processes**, so they are only allowed when `ALLOW_MCP_STDIO` is true
  (it follows `ALLOW_SHELL` by default — the OpenShift manifests set `ALLOW_SHELL=false`). The container
  image has no Node.js, so `npx`-based servers need a custom image.
- Tool names are prefixed with the server name (`docs_search`). `tool_filter`, `timeout` and `disabled`
  are optional per-server keys.
- `mcp.json` is hidden from the model's file tools; MCP tool output is treated as untrusted data.

## Guardrails & Observability

Implemented in `RunMonitor` as ADK `before_tool_callback` / `after_tool_callback`, identical in both modes:

| Guardrail | Behaviour | Control |
|-----------|-----------|---------|
| Shell deny-list | `run_command` calls matching destructive patterns (`rm -rf /`, `mkfs`, `dd of=/dev/…`, `curl … \| sh`, shutdown, fork bomb, …) are blocked and the model is told why. A safety net, **not a sandbox**. | `SHELL_GUARD=off` |
| SSRF protection | `web_fetch` refuses hosts resolving to private/loopback/link-local addresses, re-checked on every redirect hop. | `ALLOW_PRIVATE_FETCH=true` |
| Injection tripwire | Results of untrusted tools (`read_input_file`, `web_fetch`, `run_command`, MCP tools) are scanned for injection phrases; matches are logged, counted, and annotated with a `SECURITY NOTICE` the model sees. Never blocks. | — |

Observability: tool durations in the Batch log, token counts from ADK usage metadata, USD cost estimated
with LiteLLM's price table (blank for unknown/local models), and guardrail counters in the metrics card and
job history. For tracing, install the `otel` extra and set the standard `OTEL_EXPORTER_OTLP_ENDPOINT`
(and related `OTEL_*`) variables — ADK's built-in spans for agent, model and tool calls are exported.

## Supported Providers

| Provider | `API_PROVIDER` value | Default model | Credentials |
|----------|---------------------|--------------|-------------|
| Ollama / vLLM / any OpenAI-compatible | `openai-compatible` | `qwen38-27b` | `OPENAI_COMPATIBLE_API_KEY` (optional) |
| Gemini (API key) | `gemini` | `gemini-2.5-flash` | `GOOGLE_API_KEY` |
| Gemini on Vertex AI | `vertex` | `gemini-2.5-flash` | `GOOGLE_CLOUD_PROJECT` + Application Default Credentials |
| Anthropic | `anthropic` | `claude-sonnet-5-5` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai` | `gpt-4o` | `OPENAI_API_KEY` |
| OpenRouter | `openrouter` | `anthropic/claude-sonnet-5-5` | `OPENROUTER_API_KEY` |

The active provider and model can be switched at any time from the header dropdowns without restarting, and
apply to both Chat and Batch runs. Switching provider clears any `MODEL` override. Pick a model that supports
tool/function calling — small local models often do not.

### Using Local Models (Ollama / vLLM)

```bash
export API_PROVIDER=openai-compatible
export OPENAI_BASE_URL=http://localhost:11434/v1   # e.g. Ollama (default: MaaS endpoint)
export MODEL=qwen38-27b

python web_app.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PROVIDER` | `openai-compatible` | Provider — see table above |
| `MODEL` | _(provider default)_ | Model ID as returned by the provider |
| `GOOGLE_API_KEY` | — | Gemini API key (`GEMINI_API_KEY` also accepted) |
| `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` | — / `us-central1` | Vertex AI project / region |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `OPENAI_API_KEY` | — | OpenAI key (`openai` provider only) |
| `OPENAI_COMPATIBLE_API_KEY` | — | Optional bearer token for the `openai-compatible` endpoint — separate from `OPENAI_API_KEY` |
| `OPENROUTER_API_KEY` | — | OpenRouter API key |
| `OPENAI_BASE_URL` | `https://maas-rhdp.apps.maas.redhatworkshops.io/v1` | Base URL for `openai-compatible` provider |
| `MAX_TURNS` | `20` | Maximum model calls per Chat turn or per Batch run |
| `MAX_OUTPUT_TOKENS` | `16384` | Token budget for each model response |
| `LLM_TIMEOUT` / `LLM_RETRIES` | `120` / `1` | Per-request timeout (s) / retries for LiteLLM-backed providers |
| `ALLOW_SHELL` | `true` | Set `false` to block `run_command` entirely |
| `SHELL_TIMEOUT` | `60` | Max seconds a single shell command may run |
| `SHELL_GUARD` | `on` | `off` disables the destructive-command deny-list |
| `ALLOW_PRIVATE_FETCH` | `false` | `true` lets `web_fetch` reach private/loopback addresses |
| `ALLOW_MCP_STDIO` | follows `ALLOW_SHELL` | Allow stdio MCP servers |
| `EXTRA_SYSTEM_PROMPT` | _(empty)_ | Additional system prompt block (also editable in Settings) |
| `SYSTEM_PROMPT_OVERRIDE_ENABLED` / `SYSTEM_PROMPT_OVERRIDE` | `false` / _(empty)_ | Replace the built-in system prompt entirely (also in Settings) |
| `DISABLED_TOOLS` | _(empty)_ | Comma-separated tool names to remove (e.g. `run_command,web_fetch,skills,mcp`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | Enable OpenTelemetry export (needs the `otel` extra) |
| `AGENT_DIR` / `INPUT_DIR` / `OUTPUT_DIR` | `./agent` `./input` `./output` | Folder paths |
| `WORKSPACE_ROOT` | app folder | Root of the read-only Agent Workspace browser |
| `JOBS_DIR` | `./sample-jobs` | Job-pack library used by the Batch tab's Load button |
| `JOB_HISTORY_FILE` | `./.job_history.json` | Batch job history file |
| `PORT` / `HOST` | `8081` / `0.0.0.0` | Web UI bind |

Runtime-adjustable values can also be set from the web UI (Settings ⚙ and Tools 🔧 dialogs) — no restart
required.

## Web UI Features

- **Tab bar** — `Chat`, `Batch`, `File Viewer`, `Agent Workspace`, `App Logs`, `README`.
- **Agent Workspace tab** — read-only browser over the application folder (`WORKSPACE_ROOT`, default the app
  root) and its subfolders, with breadcrumbs and a text preview (1 MB cap, binaries not shown). `.git*` files and
  folders (`.git`, `.gitignore`, `.gitkeep`, …), `.venv`,
  caches and secret-like files (`.env*`, `*.pem`, `*.key`, `credentials.json`, `secrets.*`) are hidden and
  unreadable. In a container the root is `/app`, so it also shows the mounted `agent/`, `input/`, `output/`.
- **Chat tab** — streaming chat bubbles with `[You]` / `[AI]` labels; tool calls inline, collapsed by default.
- **Batch tab** — status badge, **Job Pack** select + **Load**, metrics chip, Run / Stop / Reset, live SSE
  terminal, and a collapsible history of the last 20 runs.
- **File Viewer tab** — click any file in the Agent, Input, or Output panel to view it (read-only), with Copy
  and Download. Agent and Input files also have an **Edit** pop-up; Output files are always read-only.
- **App Logs tab** — live SSE stream of application log lines, colour-coded by level.
- **Agent / Input / Output panels** — New, Upload, per-file delete, Clear all (Input/Output); resizable.
- **Tool Permissions dialog (🔧)** — toggle individual tools, skills and MCP on/off. Applies to both modes.
- **Settings dialog (⚙)** — max turns, max output tokens, shell timeout, allow-shell, and **Add System Prompt**:
  extra operator instructions (max 8000 chars, held in memory, or `EXTRA_SYSTEM_PROMPT`) that are appended to the
  built system prompt for Chat and Batch inside a clearly labelled `ADDITIONAL SYSTEM PROMPT` block, placed after
  the data-security policy so it cannot override it.
  Tick **Overwrite system prompt** to replace the built-in prompt entirely (the box is pre-filled with the default;
  **Reset to default** restores it). `instruction.md` is still appended; the data-security rules are removed unless kept in your text.
- **API Keys dialog (🔑)** — enter keys per provider (and the OpenAI-compatible base URL); held in server memory only, never written to disk or
  returned to the browser.

## REST API

Unchanged from pydantic-assistant. `GET /` serves the UI and `GET /api/readme` this file.

| Method & path | Purpose |
|---------------|---------|
| `GET /api/session` · `POST /api/chat` · `POST /api/chat/cancel` · `POST /api/chat/reset` | Chat (`/api/chat` returns an SSE stream) |
| `POST /api/batch/run` · `POST /api/batch/stop` · `POST /api/batch/reset` | Batch control |
| `GET /api/batch/status` · `GET /api/batch/logs` (SSE) · `GET /api/batch/jobs` | Batch status, log stream, history |
| `GET /api/jobpacks` · `POST /api/jobpacks/load` | Job packs |
| `GET /api/{agent,input,output}` · `DELETE /api/{input,output}` | List / clear a folder |
| `GET\|PUT\|DELETE /api/file/<folder>/<path>` · `POST /api/file/{agent,input}` · `POST /api/upload/{agent,input}` | File read / write / create / upload (agent + input only for writes) |
| `GET /api/workspace?path=` · `GET /api/workspace/file?path=` | Agent Workspace: list a folder / read a file (read-only) |
| `GET /api/app-logs` (SSE) | Application log stream |
| `GET /api/providers` · `GET\|POST /api/provider` · `GET /api/models` · `GET\|POST /api/model` | Provider / model |
| `GET\|POST /api/keys` · `GET\|POST /api/settings` · `GET\|POST /api/tools` | Keys (presence only), settings, tool permissions |

## Security

- Every file path is resolved against its base folder — path traversal is rejected in both the web layer
  and agent tools.
- Upload filenames are sanitised (`[^\w.\-/]` → `_`).
- API keys are **never** returned to the browser (presence booleans only).
- Shell commands run in `output/`, are bounded by `SHELL_TIMEOUT`, screened by the deny-list, and can be
  disabled with `ALLOW_SHELL=false` or via the Tools dialog.
- `web_fetch` is SSRF-protected; MCP stdio servers are gated by `ALLOW_MCP_STDIO`.
- The UI has no authentication of its own — it is meant for local use or behind the OAuth-proxy /
  gateway OpenShift variants. Anyone who can reach it can use your API keys and the enabled tools.
- Batch runs are subject to the same path, shell, and tool restrictions as Chat.

## Prompt Injection Safeguards

Input file contents are treated as **data**, not instructions, in both modes:

- **Write access is enforced at the tool level** — only `write_output` / `append_output`, scoped to
  `output/`, write anything; the model has no write tool for `agent/` or `input/`.
- **Delimiters** — `read_input_file` wraps every file in `[UNTRUSTED FILE DATA …]` /
  `---BEGIN FILE: name---` / `---END FILE: name---` markers; content arrives as a tool result, not as part
  of the user or kickoff message.
- **System prompt policy** — `agent/` is trusted; `input/`, `web_fetch` and MCP results are untrusted data;
  suspected injection must be flagged, not obeyed.
- **Tripwire** — the heuristic scanner above adds an explicit `SECURITY NOTICE` to suspicious results.

> **Note:** No system is completely airtight against a sufficiently crafted adversarial file. Structural
> separation, delimiter framing, the tripwire and model-level instruction are the strongest practical
> mitigation without adding a separate guardrail LLM judge.

## Project Layout

```
adk-assistant/
├── adk_core.py          ADK core: model builder, tools, skills, MCP, guardrails, Runner driver
├── web_app.py           FastAPI server: REST API, session management, SSE streams
├── templates/
│   └── index.html       Single-page UI — Chat / Batch / File Viewer / App Logs tabs
├── pyproject.toml       Dependencies (google-adk[mcp], litellm, fastapi, uvicorn, httpx)
├── tests/               pytest suite using a scripted fake model
├── sample-jobs/         Bundled Job Pack library for the Batch tab's Load button
├── agent/ input/ output/  Working folders (populate via the UI or a Job Pack)
├── .job_history.json    Last 20 Batch run records (created on first run)
└── deployment/
    ├── Containerfile                          UBI9 Python 3.12 container image
    ├── pvc.yaml                               3 PVCs: agent / input / output
    ├── secret-api-keys.yaml                   Gemini / Anthropic / OpenAI / OpenRouter keys
    ├── deployment.yaml / service.yaml / route.yaml        Basic (no-auth) OpenShift deploy
    ├── oauth-*.yaml (5 files)                 OAuth-proxy-protected OpenShift deploy
    ├── adk-assistant-template.yaml            Catalog template — basic variant
    ├── adk-assistant-oauth-template.yaml      Catalog template — OAuth variant
    ├── gateway-*.yaml (6 files)               Shared multi-instance gateway
    ├── adk-assistant-gateway-template.yaml    Catalog template — named instance behind the gateway
    └── README.md                              Podman run + OpenShift deploy guide
```

See [`deployment/README.md`](deployment/README.md) for building the image, running it with rootless
Podman, and deploying to OpenShift.
