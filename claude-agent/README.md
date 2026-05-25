# Claude Agent Harness

A containerised, web-enabled AI agent harness powered by the
[Claude Agent SDK](https://github.com/anthropics/claude-code-sdk-python).

Drop an `instruction.md` into the **inbox**, hit **Run Agent** in the browser,
and collect the results from the **outbox** — all without writing a single line
of agent scaffolding yourself.

Built for workshops. Designed to be extended.

---

## How it works

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Podman container                            │
│                                                                     │
│   Browser  ──HTTP──▶  Flask web app (web_app.py)                   │
│                              │                                      │
│                    spawns background thread                         │
│                              │                                      │
│                       agent_harness.py                              │
│                              │  Claude Agent SDK                    │
│                              ▼                                      │
│                      Anthropic API ◀── ANTHROPIC_API_KEY            │
│                              │                                      │
│            ┌─────────────────┼─────────────────┐                   │
│         MCP tools (in-process, no socket)       │                   │
│            │                                    │                   │
│      /app/inbox (read)              /app/outbox (write)             │
│      instruction.md                results + agent.log             │
│      payload files                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Agentic loop

The harness delegates the agentic loop to the **Claude Agent SDK** — there is no
manual tool-dispatch loop. Five **in-process MCP tools** give Claude scoped access
to the mounted inbox/outbox:

| Tool | Description |
|------|-------------|
| `list_inbox_files` | List payload files in `/app/inbox` |
| `read_inbox_file` | Read a file from the inbox |
| `write_output` | Write/overwrite a file in `/app/outbox` |
| `append_output` | Append to a file in the outbox |
| `list_outbox_files` | List files already written to the outbox |

Built-in Claude Code tools (`Read`, `Write`, `Edit`, `Bash`, `WebSearch`) are
**disallowed** — the agent can only interact through the volume-scoped tools above.

---

## Repository layout

```
claude-agent/
├── agent_harness.py       # Core agent logic — study this!
├── web_app.py             # Flask web application
├── templates/
│   └── index.html         # Single-page web UI
├── requirements.txt       # Python dependencies
├── Containerfile          # OCI image (Red Hat UBI 9 Python 3.12)
├── run.sh                 # Build & run helper script
├── inbox/                 # Sample inbox files
│   ├── instruction.md     # Example task instruction
│   └── sample_data.csv    # Example payload
├── outbox/                # Agent output (created at runtime)
├── workshop/              # Workshop exercises
│   ├── README.md
│   ├── beginner/
│   └── advanced/
├── README.md              # This file
├── Quickstart.md          # 5-minute getting-started guide
└── archive/               # Original implementation (reference)
```

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Linux / macOS / WSL2 | — |
| [Podman](https://podman.io/) | 4.x+ |
| Anthropic API key | — |
| Python 3.12+ | (for local dev only) |

> **No Node.js required.** The `claude-agent-sdk` wheel bundles the Claude Code
> CLI binary directly.

---

## Quick start

```bash
# 1 — Clone and enter the project
git clone <repo-url> claude-agent && cd claude-agent

# 2 — Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# 3 — Build and run (opens web UI on port 8080)
chmod +x run.sh && ./run.sh

# 4 — Open http://localhost:8080 in your browser
#     Upload instruction.md → click "Run Agent" → watch the log
```

See [Quickstart.md](Quickstart.md) for a step-by-step walkthrough.

---

## Configuration

### run.sh options

```
Usage: ./run.sh [options]

  -k KEY     Anthropic API key       (default: $ANTHROPIC_API_KEY)
  -m MODEL   Claude model            (default: claude-opus-4-5)
  -n ITER    Max agentic iterations  (default: 50)
  -p PORT    Host port               (default: 8080)
  -i DIR     Inbox directory         (default: ./inbox)
  -o DIR     Outbox directory        (default: ./outbox)
  -I IMAGE   Container image name    (default: claude-agent)
  -h         Show help
```

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `CLAUDE_MODEL` | `claude-opus-4-5` | Model to use |
| `MAX_TURNS` | `50` | Maximum agentic loop turns |
| `INBOX_DIR` | `/app/inbox` | Path to inbox inside container |
| `OUTBOX_DIR` | `/app/outbox` | Path to outbox inside container |
| `PORT` | `8080` | Web server port |

---

## Inbox structure

```
inbox/
├── instruction.md      ← Required: tells the agent what to do
├── skills/             ← Optional: custom tool files (Exercise 5)
│   └── my_tool.py
└── *.csv / *.json / …  ← Optional: payload files for the agent to process
```

---

## Extending the harness

The codebase contains four clearly marked extension points:

### Exercise 3 — Add a custom tool
Edit `agent_harness.py` and add a `@tool`-decorated function to `CUSTOM_TOOLS`.

### Exercise 4 — Implement a guardrail agent
Fill in `run_guardrail_check()` in `agent_harness.py` to validate instructions
with a second Claude call before the main agent runs.

### Exercise 5 — Dynamic skill loading
Implement `load_skills()` in `agent_harness.py` to load tools from
`inbox/skills/*.py` at runtime.

### Exercise 6 — Multi-agent orchestration
Extend `run_agent()` to spawn sub-agents or chain multiple agent runs.

See [workshop/README.md](workshop/README.md) for guided exercises.

---

## Web API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web UI |
| `GET` | `/api/inbox` | List inbox files |
| `GET` | `/api/outbox` | List outbox files |
| `GET` | `/api/file/inbox/<path>` | Read inbox file |
| `GET` | `/api/file/outbox/<path>` | Read outbox file |
| `POST` | `/api/upload` | Upload file to inbox |
| `DELETE` | `/api/inbox/<path>` | Delete inbox file |
| `DELETE` | `/api/outbox` | Clear outbox |
| `POST` | `/api/agent/run` | Start agent run |
| `POST` | `/api/agent/reset` | Reset to idle |
| `GET` | `/api/agent/status` | Status + log snapshot |
| `GET` | `/api/agent/logs` | SSE log stream |

---

## Security notes

- Runs as UID 1001 (non-root UBI default user).
- Path-traversal guards on every file read/write operation.
- `ANTHROPIC_API_KEY` is passed via environment variable — never baked into the image.
- Guardrail agent placeholder (`run_guardrail_check`) is ready to be implemented.
- The agent cannot execute shell commands — only the five scoped MCP tools.

---

## License

MIT
