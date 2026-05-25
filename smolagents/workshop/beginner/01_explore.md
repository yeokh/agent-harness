# Exercise 01 — Explore the Smolagents Agent

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Run the agent for the first time and build a mental model of how the
**Smolagents agentic loop** works by tracing execution from the browser through
`web_app.py`, into `smolagent_agent.py`, and out to the LLM provider.

---

## Background

### Single LLM call vs. agentic loop

```
Single LLM call:
  prompt → LLM → response            (one round trip, no tools)

Smolagents agentic loop:
  task → LLM → tool call → tool result → LLM → tool call → … → final answer
               ↑___________________________________↑
               (repeated until task is complete or max_steps reached)
```

The smolagents `ToolCallingAgent` manages this loop automatically.  Your code supplies:
1. **Tool objects** — Python callables wrapped with `@tool`
2. A **model** — a `LiteLLMModel` pointing to your chosen LLM provider
3. A **task** — the specific job for this run (includes inbox/outbox paths)

### Smolagents step types

Every action the agent takes produces a **step** object.  There are three kinds:

| Step type | What it means | Log prefix |
|-----------|--------------|------------|
| `ActionStep` | The model called a tool (includes reasoning + result) | `[tool_use]` + `[result]` |
| `PlanningStep` | The model created an explicit plan | `[assistant] [Plan]` |
| `FinalAnswerStep` | The model produced a final answer | `[assistant] [Done]` |

### Comparison with ADK events

```
ADK:        one Event object per atomic action
              Event(text)         → [assistant]
              Event(tool_call)    → [tool_use]
              Event(tool_result)  → [result]

Smolagents: one ActionStep per complete reasoning+tool cycle
              ActionStep.model_output_message → [assistant]  (reasoning)
              ActionStep.tool_calls           → [tool_use]   (what tool to call)
              ActionStep.observations         → [result]     (tool result)
```

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
cd smolagents
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
built from whichever API keys are present in your environment.

### 4. Run the agent

Click **Run Agent**.  Watch the log stream in the terminal panel below.

### 5. Identify step types in the log

As the agent runs, find examples of each step type:

```
model=claude-sonnet-4-6  inbox=…/inbox  outbox=…/outbox
[assistant] I'll start by listing the inbox files…    ← ActionStep reasoning
[tool_use] list_files(directory='inbox')              ← ActionStep tool_calls
[result] file1.txt  (5 bytes)…                        ← ActionStep observations
[tool_use] read_file(filepath='instruction.md')       ← next ActionStep
[result] Read each file…                              ← its observations
[assistant] Now I'll generate ASCII art for fish…     ← reasoning text
[tool_use] write_file(filepath='file1.html', …)       ← writing output
[result] Wrote 842 bytes → file1.html                 ← confirmed
[assistant] [Done] All files processed successfully.  ← FinalAnswerStep
```

Count how many `[tool_use]` lines appear.  Each represents one complete
round trip to the LLM and back.

### 6. Inspect the output

After the run completes, click the files in the **Outbox** panel.  Check:
- `file1.html`, `file2.html`, `file3.html` — agent-generated output
- `agent.log` — the full run log, written by `_agent_thread()` in `web_app.py`

### 7. Trace the code

Open `smolagent_agent.py` and `web_app.py` side by side.  Find each landmark:

| Thing to find | Where |
|---------------|-------|
| The model registry | `MODELS` dict in `smolagent_agent.py` |
| How available models are filtered | `get_available_models()` in `smolagent_agent.py` |
| How the model object is created | `_build_model()` in `smolagent_agent.py` |
| Where tool functions are defined | `_make_tools()` in `smolagent_agent.py` |
| How closures become Tool objects | `_tool(read_file)` calls in `_make_tools()` |
| The task instructions | `_TASK_TEMPLATE` in `smolagent_agent.py` |
| Where the agent is created and run | `run_agent()` in `smolagent_agent.py` |
| How steps become log lines | `_format_step()` in `smolagent_agent.py` |
| How the background thread is started | `api_run_agent()` in `web_app.py` |
| Where logs flow from thread to browser | `_agent_thread()` → `AgentState.add_log()` → `api_agent_logs()` |

### 8. Understand the execution model

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
    │  calls smolagent_agent.run_agent()
    │       ↓
    │  ToolCallingAgent.run(task)     ← SYNCHRONOUS (no asyncio needed)
    │       ↓
    │  step_callbacks=[_step_callback]
    │       ↓ called after each ActionStep
    └─ calls state.add_log() for every log line
```

**Why is smolagents synchronous when ADK is async?**
Smolagents' `ToolCallingAgent.run()` blocks the calling thread directly.
The ADK runner used Python's asyncio event loop internally.
Both approaches work fine inside a daemon thread — the difference is
that smolagents does not require `asyncio.run()` as a wrapper.

---

## Reflection questions

1. The `_TASK_TEMPLATE` in `smolagent_agent.py` is filled with inbox/outbox
   paths at runtime.  In ADK, the equivalent `_SYSTEM_PROMPT` was a fixed
   string.  What are the trade-offs of each approach?

2. Look at `_make_tools()`.  Why do we call `_tool(read_file)` instead of
   passing `read_file` directly to `ToolCallingAgent`?  What would happen
   if you passed plain functions without the `_tool()` wrapper?

3. Open `_build_model()`.  Compare it to the ADK equivalent.  The model IDs
   for Anthropic use `"anthropic/claude-sonnet-4-6"` format here (with prefix)
   vs. `"claude-sonnet-4-6"` in ADK (no prefix).  Why the difference?

4. Click **Run Agent** a second time without clearing the outbox.  Does the
   agent overwrite, append to, or skip existing files?

5. Change the model in the dropdown and run again.  Does the output differ?
   Which model is faster?  Which produces better ASCII art?

---

## Key takeaways

- The Smolagents agentic loop is automatic: `ToolCallingAgent` handles the
  call → tool → call cycle; you provide tools and a task.
- Every agent action appears in the log as `[tool_use]`, `[result]`, or
  `[assistant]` — you can follow exactly what the agent did and why.
- **ADK vs Smolagents**: ADK emits one Event per atomic action (async);
  Smolagents emits one ActionStep per complete reasoning+tool cycle (sync).
  Same information, different granularity.
- `web_app.py` is a thin web layer; all agent logic lives in `smolagent_agent.py`.
- Tools are plain Python closures wrapped with `tool()` — the wrapper adds
  the name/description/schema metadata that the LLM needs to call them.
