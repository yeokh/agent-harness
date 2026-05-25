# LangChain Agent

A web-based, one-shot agent runner powered by [LangChain DeepAgents](https://github.com/langchain-ai/deepagents).  
Drop task instructions and payload files into the inbox, click **Run Agent**, and collect results from the outbox — all from a browser.

This project replicates the `pi-cli-agent` harness but replaces the pi CLI subprocess with a native LangChain DeepAgents agent.

---

## How it works

```
Browser UI  →  Flask (web_app.py)  →  DeepAgents (LangGraph graph)  →  Anthropic / OpenRouter API
                                            │
                                    built-in file tools
                                    (read_file, write_file,
                                     edit_file, ls, glob, grep)
                                            │
                                    reads inbox/  →  writes outbox/
```

1. Upload `instruction.md` (required) and any payload files to the inbox.
2. Optionally add `skill.md` to inject extra behaviour guidelines.
3. Click **Run Agent** — the agent reads the inbox, executes the task, writes outputs to the outbox.
4. Real-time logs stream to the terminal panel via SSE.

---

## Repository layout

```
langchain-agent/
├── web_app.py            Flask app + DeepAgents runner
├── pyproject.toml        Python project metadata
├── README.md             This file
├── templates/
│   └── index.html        Single-page web UI
├── inbox/
│   ├── instruction.md    Task instructions (required to run)
│   ├── skill.md          Extra agent behaviour guidelines (optional)
│   └── *.txt / …         Payload files for the demo task
└── outbox/               Agent output files land here
```

---

## Prerequisites

- Python 3.11+
- An API key for at least one provider:
  - `ANTHROPIC_API_KEY` — for `anthropic:*` model strings
  - `OPENROUTER_API_KEY` — for `openrouter:*` model strings (or any model when only this key is set)

---

## Quick start

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 2. Install dependencies
pip install -e .

# 3. Set your API key
set ANTHROPIC_API_KEY=sk-ant-...          # Windows
# export ANTHROPIC_API_KEY=sk-ant-...    # macOS / Linux

# 4. Start the web UI
python web_app.py

# 5. Open http://localhost:8080 in your browser and click Run Agent
```

---

## Configuration

| Variable            | Default                          | Description                              |
|---------------------|----------------------------------|------------------------------------------|
| `ANTHROPIC_API_KEY` | —                                | Anthropic API key                        |
| `OPENROUTER_API_KEY`| —                                | OpenRouter API key                       |
| `DEFAULT_MODEL`     | `anthropic:claude-sonnet-4-6`    | Starting model (changeable in UI)        |
| `INBOX_DIR`         | `./inbox`                        | Directory the agent reads from           |
| `OUTBOX_DIR`        | `./outbox`                       | Directory the agent writes to            |
| `PORT`              | `8080`                           | HTTP port                                |
| `HOST`              | `0.0.0.0`                        | Bind address                             |

---

## Model string formats

The model selector in the UI accepts any LangChain-compatible model string:

| String                                  | Provider       | Key needed              |
|-----------------------------------------|----------------|-------------------------|
| `anthropic:claude-sonnet-4-6`           | Anthropic       | `ANTHROPIC_API_KEY`     |
| `anthropic:claude-opus-4-7`             | Anthropic       | `ANTHROPIC_API_KEY`     |
| `anthropic:claude-haiku-4-5-20251001`   | Anthropic       | `ANTHROPIC_API_KEY`     |
| `openrouter:anthropic/claude-opus-4-7`  | OpenRouter      | `OPENROUTER_API_KEY`    |
| `openrouter:openai/gpt-4o`              | OpenRouter      | `OPENROUTER_API_KEY`    |
| `openrouter:google/gemini-2.0-flash-001`| OpenRouter      | `OPENROUTER_API_KEY`    |

If only `OPENROUTER_API_KEY` is set (no `ANTHROPIC_API_KEY`), all model strings are routed through OpenRouter automatically.

---

## Inbox structure

| File              | Required | Purpose                                           |
|-------------------|----------|---------------------------------------------------|
| `instruction.md`  | Yes      | The task the agent will execute                   |
| `skill.md`        | No       | Extra behaviour guidelines appended to the system prompt |
| Any other files   | No       | Payload data for the task                         |

---

## Differences from pi-cli-agent

| Feature             | pi-cli-agent              | langchain-agent                     |
|---------------------|---------------------------|-------------------------------------|
| Agent runtime       | pi CLI subprocess          | LangChain DeepAgents (LangGraph)    |
| Tool execution      | pi's built-in tools       | DeepAgents filesystem tools         |
| Shell access        | Yes (via pi)              | No (filesystem only)                |
| Model selection     | Fixed dropdown (Claude only)| Free-text input (any provider)    |
| Sub-agents          | No                        | No (disabled via system prompt)     |
| Installation        | Requires pi CLI + Node.js  | Pure Python                         |

---

## Security notes

- The agent has access to the local filesystem via DeepAgents' built-in tools.
- The system prompt instructs the agent to read only from `inbox/` and write only to `outbox/`, but this is a behavioural constraint, not a hard sandbox.
- Do not expose this server to untrusted networks.
