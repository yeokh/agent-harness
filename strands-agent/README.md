# Strands Agent

A web-based file-processing agent powered by **Amazon Strands SDK**.
Drop files into the **inbox**, describe the task in `instruction.md`, hit **Run Agent**,
and collect results from the **outbox** — all via a browser UI with real-time log streaming.
Inbox files can also be edited directly in the browser.

## Architecture

```
Browser (index.html)
  │  HTTP + SSE
  ▼
web_app.py  ─── Flask REST API + SSE log stream + inbox file editor
  │  import
  ▼
strands_agent.py ── Amazon Strands Agent (tools: read_file, write_file, list_files, run_bash)
  │  Strands model classes
  ▼
LLM provider  ── Anthropic Claude | OpenAI GPT | OpenRouter (via LiteLLM)
```

**`web_app.py`** handles only HTTP: file management endpoints, inbox file editing,
model selection, agent lifecycle, and SSE streaming.  No LLM calls happen here.

**`strands_agent.py`** owns all agent logic: model construction via Strands model
classes, `@tool`-decorated tool functions, the Strands Agent, and streaming callbacks.

## Supported Providers

| Provider | Environment variable | Example models |
|----------|---------------------|----------------|
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6`, `claude-opus-4-5` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini` |
| OpenRouter | `OPENROUTER_API_KEY` | `openrouter/anthropic/claude-3-5-sonnet`, `openrouter/google/gemini-2.5-flash-preview-05-20` |

Set at least one key; the UI automatically shows only the models whose key is present.

## Quick Start

```bash
cd strands-agent

# 1. Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .

# 2. Configure at least one API key
cp .env.example .env
#    edit .env and uncomment the key(s) you have

# 3. Load the env and start the server
export $(grep -v '^#' .env | xargs)   # Linux/macOS
python web_app.py
# or: strands-agent-web
```

Open **http://localhost:8080** in your browser.

## Usage

1. **Upload files** — drag-and-drop or click _Upload file_ to add to inbox.
   `instruction.md` **must** be present to run the agent.
2. **Edit inbox files** — click any inbox file, then click the **✏ Edit** button
   to edit it in-browser.  Click **💾 Save** to write the changes back.
3. **Select a model** — pick from available models in the dropdown (bottom-right).
4. **Run Agent** — the agent reads `instruction.md`, processes inbox files, writes to outbox.
5. **View results** — click any outbox file to preview it.
6. **Reset** — click _Reset_ after a run to clear state and start again.

## Strands vs Google ADK — Conceptual Comparison

| Dimension | Google ADK | Amazon Strands |
|-----------|------------|----------------|
| Tool definition | Plain Python function | Python function + `@tool` decorator |
| Agent class | `LlmAgent` | `Agent` |
| Runner | `InMemoryRunner` + `Session` | Built into `Agent` |
| Async model | `asyncio` + `runner.run_async()` | Synchronous `agent(prompt)` |
| Event stream | `Event` objects via `async for` | `callback_handler(**kwargs)` |
| Model classes | `LiteLlm(model=...)` unified | `AnthropicModel`, `OpenAIModel`, `LiteLLMModel` |

## Extending

### Change the task
Edit or replace `inbox/instruction.md` — use the browser editor or upload a new file.

### Add a model
Add an entry to `MODELS` in `strands_agent.py`:
```python
"my-model-id": {
    "provider":  "openrouter",
    "display":   "My Custom Model",
    "model_id":  "openrouter/provider/model-name",
    "env":       "OPENROUTER_API_KEY",
},
```

### Add a tool
Add a function to `_make_tools()` in `strands_agent.py`.  Wrap it with `strands_tool()`.
The function's docstring and type annotations define the schema the LLM sees.

## Project Layout

```
strands-agent/
├── web_app.py          Flask web UI (HTTP endpoints + SSE + inbox editor)
├── strands_agent.py    Amazon Strands agent (model, tools, runner)
├── templates/
│   └── index.html      Single-page browser UI with file editor
├── inbox/              Agent reads from here; files editable in browser
│   ├── instruction.md  Task definition (required)
│   └── *.txt / *.csv   Payload files
├── outbox/             Agent writes to here
│   └── agent.log       Processing summary (written by agent)
├── workshop/           Guided exercises for the workshop
├── .env.example        API key template
└── pyproject.toml      Dependencies
```
