# Exercise 01 — Explore the Pi CLI Agent

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Run the agent for the first time and develop a mental model of how the
agentic loop works by tracing execution from `web_app.py` through pi to the API.

---

## Background

An **agentic loop** is different from a single LLM call:

```
Single LLM call:
  prompt → LLM → response  (one round trip)

Agentic loop:
  prompt → LLM → tool call → tool result → LLM → tool call → … → final response
                 ↑_________________________↑  (repeated until task done)
```

With the pi CLI, the loop is managed entirely by pi. Our job is to:
1. Write the task instruction that tells the agent what to do
2. Write the skill that tells the agent *how* to do it (tools, protocol)
3. Collect the results from the outbox

The pi CLI has these built-in tools available to the agent:

| Tool | What it does |
|------|-------------|
| `read` | Read a file |
| `write` | Write a file |
| `edit` | Edit a file in-place |
| `bash` | Run a shell command |
| `grep` | Search file content |
| `find` | Find files by name/pattern |
| `ls` | List directory contents |

---

## Steps

### 1. Start the web UI

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python web_app.py
```

Open **http://localhost:8080** in your browser.

### 2. Run the agent

Click **Run Agent**. Watch the log stream appear in the browser.

### 3. Observe the inbox

The **Inbox** panel shows:
- `instruction.md` — the task the agent will follow
- `skill.md` — the pi skill defining the inbox/outbox protocol
- `sample_data.csv` — a payload file the agent can read

Click `instruction.md` to read it. What is the agent being asked to do?

### 4. Watch the agentic loop

As pi runs, look for these phases in the log stream:

1. **Planning** — the agent reads `instruction.md` and `skill.md`, then decides what to do
2. **Discovery** — the agent calls `ls` or `find` to see what files are in `./inbox/`
3. **Reading** — the agent calls `read` on each payload file
4. **Processing** — the agent reasons over the data
5. **Writing** — the agent calls `write` to produce output in `./outbox/`
6. **Done** — pi exits when the task is complete

### 5. Inspect the output

Switch to the **Outbox** panel in the browser, or from the terminal:

```bash
ls outbox/
cat outbox/report.md
cat outbox/summary.md
cat outbox/agent.log
```

- `report.md` — the main analysis output
- `summary.md` — the one-paragraph overview written by the agent
- `agent.log` — the full run log

### 6. Read the web app code

Open `web_app.py`. Find:

| Thing to find | Where |
|---------------|-------|
| The prompt sent to pi | `_build_prompt()` function |
| Where the pi command is built | `_agent_thread()` — look for `cmd: list[str]` |
| How skill.md is loaded | `--skill` flag added if `skill_file.exists()` |
| How output is streamed + logged | `subprocess.Popen(...)` loop inside `_agent_thread()` |
| How the browser gets live updates | `AgentState.add_log()` → SSE via `/api/agent/logs` |

### 7. Inspect the skill file

Open `inbox/skill.md`. Notice:

- The frontmatter (`---`) with `name` and `description` — this is the pi skill format
- The inbox/outbox rules the agent is told to follow
- The tool-usage guidance section

The agent receives the skill's `description` in its system prompt automatically.
When the task matches, pi loads the full skill body for detailed guidance.

---

## Reflection questions

1. The agent can call `bash` to run shell commands. What could it do with this
   tool that the claude-agent (container harness) could not? What risk does this
   introduce?

2. The `instruction.md` is read *by the agent* using its `read` tool, not
   injected into the system prompt by the runner. What are the implications for
   prompt injection attacks?

3. What would happen if you clicked **Run Agent** twice in a row without clearing
   the outbox? Would the agent overwrite, append, or skip existing files?

4. `web_app.py` passes `--no-session` to pi. What does this do, and why is it
   important for a headless runner?

---

## Key takeaways

- The pi CLI manages the agentic loop; `web_app.py` is a thin web wrapper.
- `skill.md` is the primary control point for agent behaviour — no Python required.
- All activity streams to the browser and is saved to `outbox/agent.log`.
- The agent's tool set is pi's built-in tools; you extend *behaviour* via skills,
  not by writing custom tool code.
