# Pi CLI Agent

A web-based one-shot agent runner powered by the
[pi CLI](https://github.com/earendil-works/pi/tree/main/packages/coding-agent).

Drop an `instruction.md` (and optionally a `skill.md`) into the **inbox** via
the browser UI, click **Run Agent**, and collect results from the **outbox** — no
container required.

Built for workshops. Designed to be extended via skills.

---

## How it works

```
┌─────────────────────────────────────────────────────────────┐
│                      Host machine                           │
│                                                             │
│   python web_app.py  (Flask UI on :8080)                    │
│        │                                                    │
│        │  subprocess (background thread)                    │
│        ▼                                                    │
│   pi -p "<prompt>" --skill ./inbox/skill.md --no-session    │
│        │  pi CLI agentic loop                               │
│        ▼                                                    │
│   Anthropic API ◀── ANTHROPIC_API_KEY                       │
│        │                                                    │
│   ┌────┴──────────────────────────────┐                     │
│   │  pi built-in tools                │                     │
│   │  read · write · grep · find       │                     │
│   │  ls   · bash  · edit              │                     │
│   └────┬──────────────────────────────┘                     │
│        │                                                    │
│   ./inbox  (read)           ./outbox  (write)               │
│   instruction.md            report.md                       │
│   skill.md                  summary.md                      │
│   payload files             agent.log                       │
└─────────────────────────────────────────────────────────────┘
```

### Agentic loop

The pi CLI drives the entire agentic loop — `web_app.py` is a thin web
interface and orchestration wrapper. The agent reads its task from
`inbox/instruction.md`, uses its built-in tools to process payload files,
and writes everything to `./outbox/`.

`inbox/skill.md` is a pi skill file that defines the inbox/outbox protocol and
tool-usage guidance. Replace or extend it to change agent behaviour without
touching `web_app.py`.

---

## Repository layout

```
pi-cli-agent/
├── web_app.py             # Flask web UI + pi runner — study this!
├── pyproject.toml         # Python project metadata
├── inbox/
│   ├── instruction.md     # Task instructions (edit this per run)
│   ├── skill.md           # Agent protocol skill (extend this)
│   └── sample_data.csv    # Example payload
├── outbox/                # Agent output (created at runtime)
├── workshop/              # Workshop exercises
│   ├── README.md
│   ├── beginner/
│   └── advanced/
├── README.md              # This file
└── Quickstart.md          # 5-minute getting-started guide
```

---

## Prerequisites

| Requirement | Version | Install |
|-------------|---------|---------|
| Python | 3.13+ | [python.org](https://python.org) |
| pi CLI | latest | `curl -fsSL https://pi.dev/install.sh \| sh` |
| Anthropic API key | — | [console.anthropic.com](https://console.anthropic.com) |

> **No Docker/Podman required.** The pi CLI runs directly on the host.

---

## Quick start

```bash
# 1 — Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# 2 — Start the web UI
cd pi-cli-agent
python web_app.py

# 3 — Open your browser at http://localhost:8080

# 4 — Click "Run Agent" and watch the live log stream

# 5 — Read the results in the Outbox panel
```

See [Quickstart.md](Quickstart.md) for a step-by-step walkthrough.

---

## Configuration

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Anthropic API key |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Model to use |
| `INBOX_DIR` | `./inbox` | Inbox directory |
| `OUTBOX_DIR` | `./outbox` | Outbox directory |
| `PORT` | `8080` | Web server port |
| `HOST` | `0.0.0.0` | Web server host |

Override at startup:

```bash
CLAUDE_MODEL=claude-haiku-4-5-20251001 PORT=9000 python web_app.py
```

The model can also be changed at runtime from the web UI without restarting.

---

## Inbox structure

```
inbox/
├── instruction.md    ← Required: tells the agent what to do
├── skill.md          ← Optional: pi skill defining tools and protocol
└── *.csv / *.json …  ← Optional: payload files to process
```

### instruction.md

Describes the task. The agent reads this first and uses it as its primary
directive. Example:

```markdown
# Agent Task: Summarise Logs

Read all .log files in ./inbox/ and produce a summary table in ./outbox/summary.md
grouped by severity level.
```

### skill.md

A [pi skill file](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md)
that defines how the agent should behave — which tools to use, what the
inbox/outbox protocol is, and any domain-specific guidance.

The default `inbox/skill.md` provides a general-purpose inbox/outbox protocol.
Replace the body to specialise the agent for your domain.

---

## Extending the app

### Add tool instructions (no code required)

Edit `inbox/skill.md` to change what tools the agent uses or how it
structures its output. For example, to add bash-based data processing:

```markdown
## Data Processing
Use bash to transform data before writing:
  python3 ./inbox/transform.py --input ./inbox/data.csv --output ./outbox/data.json
```

### Add a guardrail check (Exercise 4)

Add a pre-flight Claude call in `web_app.py`'s `_agent_thread()` before
spawning pi. See
[workshop/advanced/04_guardrail.md](workshop/advanced/04_guardrail.md).

### Use formal pi skills (Exercise 5)

Create a `~/.pi/agent/skills/my-skill/SKILL.md` for globally available
skills, or extend `_agent_thread()` to pass `--skill ./path/to/skill.md`
for run-specific skills.
See [workshop/advanced/05_custom_skills.md](workshop/advanced/05_custom_skills.md).

### Multi-agent orchestration (Exercise 6)

Chain multiple `pi` runs in `web_app.py` — the outbox of one run becomes the
inbox of the next. See [workshop/advanced/06_multi_agent.md](workshop/advanced/06_multi_agent.md).

---

## vs claude-agent (web harness)

| Feature | claude-agent | pi-cli-agent |
|---------|-------------|--------------|
| Interface | Browser UI | Browser UI |
| Agent loop | Claude Agent SDK | pi CLI |
| Tools | Custom MCP tools (scoped) | pi built-in tools |
| Skills | Python @tool decorator | pi skill Markdown files |
| Container | Podman required | Runs on host directly |
| Dependencies | flask, claude-agent-sdk | flask, pi CLI (npm/curl) |
| Streaming | SSE to browser | SSE to browser |

---

## Security notes

- The agent runs on your host with your filesystem access — it is NOT
  sandboxed like the containerised claude-agent.
- The `skill.md` protocol instructs the agent to stay within inbox/outbox,
  but this is a behavioural constraint, not a hard filesystem boundary.
- For untrusted payloads or instructions, use the guardrail (Exercise 4)
  and consider running inside a container or VM.
- Never commit `ANTHROPIC_API_KEY` — use environment variables or `.env`.

---

## License

MIT
