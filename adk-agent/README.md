# ADK Agent

A web-based file-processing agent powered by **Google ADK** (Agent Development Kit).
Drop files into the **inbox**, describe the task in `instruction.md`, hit **Run Agent**,
and collect results from the **outbox** — all via a browser UI with real-time log streaming.

## Architecture

```
Browser (index.html)
  │  HTTP + SSE
  ▼
web_app.py  ─── Flask REST API + SSE log stream
  │  import
  ▼
adk_agent.py ── Google ADK LlmAgent (tools: read_file, write_file, list_files, run_bash)
  │  LiteLLM
  ▼
LLM provider  ── Anthropic Claude | OpenAI GPT | OpenRouter
```

**`web_app.py`** handles only HTTP: file management endpoints, model selection, agent
lifecycle, and SSE streaming.  No LLM calls happen here.

**`adk_agent.py`** owns all agent logic: model construction, tool definitions, ADK runner,
and event-to-log-line conversion.

## Supported Providers

| Provider | Environment variable | Example models |
|----------|---------------------|----------------|
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6`, `claude-opus-4-5` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini` |
| OpenRouter | `OPENROUTER_API_KEY` | `openrouter/anthropic/claude-3-5-sonnet`, `openrouter/google/gemini-2.5-flash-preview-05-20` |

Set at least one key; the UI automatically shows only the models whose key is present.

## Quick Start

```bash
cd adk-agent

# 1. Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .

# 2. Configure at least one API key
cp .env.example .env
#    edit .env and uncomment the key(s) you have

# 3. Load the env and start the server
export $(grep -v '^#' .env | xargs)   # Linux/macOS
adk-agent-web
# or: python web_app.py
```

Open **http://localhost:8080** in your browser.

## Usage

1. **Upload files** — drag-and-drop or click _Upload file_ to add to inbox.
   `instruction.md` **must** be present to run the agent.
2. **Select a model** — pick from available models in the dropdown (bottom-right).
3. **Run Agent** — the agent reads `instruction.md`, processes inbox files, writes to outbox.
4. **View results** — click any outbox file to preview it.
5. **Reset** — click _Reset_ after a run to clear state and start again.

## Extending

### Change the task
Edit (or replace) `inbox/instruction.md`.  No code changes needed.

### Add a model
Add an entry to `MODELS` in `adk_agent.py`:
```python
"my-model-id": {
    "provider":   "openrouter",
    "display":    "My Custom Model",
    "litellm_id": "openrouter/provider/model-name",
    "env":        "OPENROUTER_API_KEY",
},
```

### Add a tool
Add a function to `_make_tools()` in `adk_agent.py`.  The function's docstring becomes
the tool description the LLM sees; type-annotated parameters become the tool's schema.

## Project Layout

```
adk-agent/
├── web_app.py         Flask web UI (HTTP endpoints + SSE)
├── adk_agent.py       Google ADK agent (model, tools, runner)
├── templates/
│   └── index.html     Single-page browser UI
├── inbox/             Agent reads from here
│   ├── instruction.md Task definition (required)
│   └── *.txt / *.csv  Payload files
├── outbox/            Agent writes to here
│   └── agent.log      Processing summary (written by agent)
├── .env.example       API key template
└── pyproject.toml     Dependencies
```
