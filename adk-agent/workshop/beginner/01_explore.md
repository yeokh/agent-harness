# Exercise 01 — Explore the ADK Agent

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Run the agent for the first time and build a mental model of how the
**ADK agentic loop** works by tracing execution from the browser through
`web_app.py`, into `adk_agent.py`, and out to the LLM provider.

---

## Background

### Single LLM call vs. agentic loop

```
Single LLM call:
  prompt → LLM → response            (one round trip, no tools)

ADK agentic loop:
  prompt → LLM → tool call → tool result → LLM → tool call → … → final answer
                 ↑_________________________________↑
                 (repeated until task is complete)
```

The ADK `LlmAgent` manages this loop automatically.  Your code supplies:
1. A **system prompt** — standing instructions baked into every LLM call
2. **Tool functions** — Python callables the LLM can invoke
3. A **task prompt** — the specific job for this run (read from `instruction.md`)

### ADK Event types

Every action the agent takes produces an `Event` object.  There are three kinds:

| Event type | What it means | Log prefix |
|------------|--------------|------------|
| Text part | The model is "thinking out loud" or giving a final answer | `[assistant]` |
| Function call | The model wants to invoke a tool | `[tool_use]` |
| Function response | The tool returned a result back to the model | `[result]` |

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
cd adk-agent
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY / OPENROUTER_API_KEY
python web_app.py
```

Open **http://localhost:8080** in your browser.

### 2. Inspect the inbox

Click each file in the **Inbox** panel:
- `instruction.md` — the task the agent will follow; read it now
- `file1.txt`, `file2.txt`, `file3.txt` — simple payload files

Notice: `instruction.md` is a plain Markdown file you can edit or replace via
the upload button.  The agent *reads* it at runtime using the `read_file` tool —
it is not hard-coded into any Python.

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
[tool_use] list_files(directory='inbox')              ← model invoking a tool
[result] list_files: file1.txt (4 bytes)…             ← tool result returned
[tool_use] read_file(filepath='inbox/instruction.md') ← another tool call
[result] read_file: Read each file…                   ← tool result
[assistant] Now I'll generate ASCII art for fish…     ← model reasoning
[tool_use] write_file(filepath='outbox/file1.html', …)← writing output
[result] write_file: Wrote 842 bytes → file1.html     ← write confirmed
```

Count how many tool calls the agent makes in total.  Each one is a round trip
to the LLM and back.

### 6. Inspect the output

After the run completes, click the files in the **Outbox** panel.  Check:
- `file1.html`, `file2.html`, `file3.html` — agent-generated output
- `agent.log` — the full run log, written by `_agent_thread()` in `web_app.py`

### 7. Trace the code

Open `adk_agent.py` and `web_app.py` side by side.  Find each landmark:

| Thing to find | Where |
|---------------|-------|
| The model registry | `MODELS` dict in `adk_agent.py` |
| How available models are filtered | `get_available_models()` in `adk_agent.py` |
| The agent's standing instructions | `_SYSTEM_PROMPT` in `adk_agent.py` |
| Where tool functions are defined | `_make_tools()` in `adk_agent.py` |
| How LiteLlm objects are created | `_build_model()` in `adk_agent.py` |
| The ADK runner setup | `_run_async()` in `adk_agent.py` |
| How the background thread is started | `api_run_agent()` in `web_app.py` |
| Where logs flow from thread to browser | `_agent_thread()` → `AgentState.add_log()` → `api_agent_logs()` |
| The SSE generator | `api_agent_logs()` in `web_app.py` |

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
    │  calls adk_agent.run_agent()  →  ADK loop  →  LLM provider
    └─ calls state.add_log() for every event line
```

Why a background thread?  Flask request handlers must return quickly.  The
ADK agent can run for minutes.  The thread lets the agent run while the SSE
connection streams its output live.

---

## Reflection questions

1. The `_SYSTEM_PROMPT` in `adk_agent.py` is fixed — it never changes between
   runs.  The task-specific instructions live in `instruction.md` and are read
   by the agent at runtime.  What are the security implications of this split?

2. Look at `run_bash` in `_make_tools()`.  The agent can execute any shell
   command on the host machine.  What could a malicious `instruction.md` do
   with this capability?

3. The ADK uses `InMemoryRunner`, which means session history is lost when the
   Python process restarts.  What would you need to change to persist history
   across restarts?

4. Click **Run Agent** a second time without clearing the outbox.  What happens?
   Does the agent overwrite, append to, or skip the existing files?

5. Change the model in the dropdown and run again.  Does the output differ?
   Which model is faster?  Which produces better ASCII art?

---

## Key takeaways

- The ADK agentic loop is automatic: `LlmAgent` handles the call → tool → call
  cycle; you provide tools and a system prompt.
- Every agent action appears in the log as `[tool_use]`, `[result]`, or
  `[assistant]` events — you can follow exactly what the agent did and why.
- `web_app.py` is a thin web layer; all agent logic lives in `adk_agent.py`.
- `instruction.md` controls *what* the agent does; `_SYSTEM_PROMPT` controls
  *how* it behaves (its constraints and conventions).
- Tools are plain Python functions — no decorators, no framework magic.
