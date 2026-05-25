# Exercise 01 — Explore the Strands Agent

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Run the agent for the first time and build a mental model of how the
**Strands agentic loop** works by tracing execution from the browser through
`web_app.py`, into `strands_agent.py`, and out to the LLM provider.

---

## Background

### Single LLM call vs. Strands agentic loop

```
Single LLM call:
  prompt → LLM → response            (one round trip, no tools)

Strands agentic loop:
  prompt → LLM → tool call → tool result → LLM → tool call → … → final answer
                 ↑_________________________________↑
                 (Agent handles this loop automatically)
```

The Strands `Agent` manages this loop automatically.  Your code supplies:
1. A **model** — a Strands model object (`AnthropicModel`, `OpenAIModel`, or `LiteLLMModel`)
2. A **system prompt** — standing instructions baked into every LLM call
3. **Tool functions** — Python callables decorated with `@tool`
4. A **task prompt** — the specific job for this run (read from `instruction.md`)

### Strands vs. Google ADK

| Concept | Google ADK | Amazon Strands |
|---------|------------|----------------|
| Tool definition | Plain Python function | Python function + `@tool` |
| Agent class | `LlmAgent` | `Agent` |
| Runner | `InMemoryRunner` + `Session` | Built into `Agent` |
| Async model | `asyncio.run()` required | Synchronous `agent(prompt)` |
| Event stream | `Event` objects via `async for` | `callback_handler(**kwargs)` |

### Strands event types (in the log stream)

| Log prefix | Source | Meaning |
|------------|--------|---------|
| `[assistant]` | `callback_handler` `data` kwarg | Model "thinking out loud" or final answer |
| `[tool_use]` | Tool function (embedded log) | Model invoked a tool |
| `[result]` | Tool function (embedded log) | Tool returned a result to the model |

### Tools available in this harness

| Tool | What it does |
|------|-------------|
| `read_file` | Read a file from inbox or outbox |
| `write_file` | Write a file to the outbox |
| `list_files` | List all files in inbox or outbox |
| `run_bash` | Execute a shell command (tar extraction, Python one-liners, etc.) |

---

## Steps

### 1. Start the web UI

```bash
cd strands-agent
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY / OPENROUTER_API_KEY
python web_app.py
```

Open **http://localhost:8080** in your browser.

### 2. Inspect the inbox

Click each file in the **Inbox** panel:
- `instruction.md` — the task the agent will follow; read it now
- `file1.txt`, `file2.txt`, `file3.txt` — simple payload files

**New feature**: click the **✏ Edit** button in the viewer toolbar to edit
any inbox file directly in your browser.  Click **💾 Save** to write the change back.
This is how you modify `instruction.md` without leaving the browser.

### 3. Select a model

In the bottom-right dropdown, pick any available model.  The list is
built from whichever API keys are present in your environment — models whose
key is missing do not appear.

### 4. Run the agent

Click **Run Agent**.  Watch the log stream in the terminal panel below.

### 5. Identify event types in the log

As the agent runs, find examples of each event type:

```
[assistant] I'll start by listing the inbox files…    ← model thinking aloud
[tool_use] list_files(directory='inbox')              ← model invoked a tool
[result] list_files: instruction.md (234 bytes)…      ← tool result returned
[tool_use] read_file(filepath='instruction.md')       ← another tool call
[result] read_file: 'Read each file…'                 ← tool result
[assistant] Now I'll generate ASCII art for fish…     ← model reasoning
[tool_use] write_file(filepath='file1.html', …)       ← writing output
[result] write_file: Wrote 842 bytes → file1.html     ← write confirmed
```

Count how many tool calls the agent makes in total.  Each one is a round
trip to the LLM and back.

### 6. Inspect the output

After the run completes, click the files in the **Outbox** panel.  Check:
- `file1.html`, `file2.html`, `file3.html` — agent-generated output
- `agent.log` — the full run log, written by `_agent_thread()` in `web_app.py`

### 7. Trace the code

Open `strands_agent.py` and `web_app.py` side by side.  Find each landmark:

| Thing to find | Where |
|---------------|-------|
| The model registry | `MODELS` dict in `strands_agent.py` |
| How available models are filtered | `get_available_models()` in `strands_agent.py` |
| How models are instantiated | `_build_model()` in `strands_agent.py` |
| The agent's standing instructions | `_SYSTEM_PROMPT` in `strands_agent.py` |
| Where tool functions are defined | `_make_tools()` in `strands_agent.py` |
| How the @tool decorator is applied | `[strands_tool(fn) for fn in ...]` at the end of `_make_tools()` |
| The streaming callback | `_make_streaming_callback()` in `strands_agent.py` |
| Where the Agent is created | `run_agent()` in `strands_agent.py` |
| How the background thread is started | `api_run_agent()` in `web_app.py` |
| Where logs flow from thread to browser | `_agent_thread()` → `AgentState.add_log()` → `api_agent_logs()` |

### 8. Understand the thread model

```
Browser tab
    │  GET /api/agent/logs (long-lived SSE connection)
    ▼
Flask request thread (api_agent_logs)
    │  reads AgentState.snapshot() every 0.4 s
    │
AgentState (shared object with threading.Lock)
    │
Background thread (_agent_thread)
    │  calls strands_agent.run_agent()  →  Strands Agent loop  →  LLM provider
    └─ calls state.add_log() for every event line
```

Why a background thread?  Flask request handlers must return quickly.
`agent(prompt)` blocks until the agentic loop finishes — which can take minutes.
The thread lets the agent run while the SSE connection streams its output live.

### 9. Understand how tool logging works in Strands

In the ADK version, tool calls were captured from `Event` objects emitted by
the framework.  In Strands, we embed the logging directly inside each tool
closure — look at `read_file` inside `_make_tools()`:

```python
def read_file(filepath: str) -> str:
    """Read a file from inbox or outbox."""
    log_callback(f"[tool_use] read_file(filepath={filepath!r})")  # ← our log call
    # ... implementation ...
    log_callback(f"[result] read_file: {content[:200]!r}…")       # ← our log call
    return content
```

This gives the same visibility as ADK's Event stream but is purely Python —
no framework event parsing required.

---

## Reflection questions

1. The `_SYSTEM_PROMPT` in `strands_agent.py` is fixed — it never changes between
   runs.  The task-specific instructions live in `instruction.md` and are read
   by the agent at runtime.  What are the security implications of this split?

2. Look at `run_bash` in `_make_tools()`.  The agent can execute any shell command
   on the host machine.  What could a malicious `instruction.md` do with this?

3. Strands uses a synchronous `agent(prompt)` call instead of ADK's async runner.
   What does this mean for Flask's threading model?  Why do we run the agent in a
   background thread rather than the request handler directly?

4. Click **Run Agent** a second time without clearing the outbox.  What happens?
   Does the agent overwrite, append to, or skip the existing files?

5. Change the model in the dropdown and run again.  Does the output differ?
   Which model is faster?  Which produces better ASCII art?

---

## Key takeaways

- The Strands agentic loop is automatic: `Agent` handles the call → tool → call
  cycle; you provide `@tool` functions and a system prompt.
- Every agent action appears in the log as `[tool_use]`, `[result]`, or
  `[assistant]` events — you can follow exactly what the agent did and why.
- `web_app.py` is a thin web layer; all agent logic lives in `strands_agent.py`.
- `instruction.md` controls *what* the agent does; `_SYSTEM_PROMPT` controls
  *how* it behaves (its constraints and conventions).
- Strands tools are Python functions decorated with `@tool` — docstrings and
  type annotations build the schema the LLM uses to decide when and how to call them.
- The inbox file editor lets you iterate on `instruction.md` without leaving the browser.
