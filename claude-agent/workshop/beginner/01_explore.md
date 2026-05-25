# Exercise 01 — Explore the Harness

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Run the agent for the first time and develop a mental model of how the
agentic loop works by tracing execution through the codebase.

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

The Claude Agent SDK manages this loop for us. Our job is to:
1. Define the tools the agent can call
2. Write the instruction that tells it what to do
3. Collect the results

---

## Steps

### 1. Run the harness

```bash
export ANTHROPIC_API_KEY=sk-ant-...
./run.sh
```

Open **http://localhost:8080**.

### 2. Observe the inbox

The `inbox/` folder already contains:
- `instruction.md` — the task the agent will follow
- `sample_data.csv` — a payload file the agent can read

Click `instruction.md` in the UI to read it. What is the agent being asked to do?

### 3. Run the agent

Click **▶ Run Agent** and watch the log panel.

Look for these log entry types:
- `[INFO] Loading instruction.md` — harness reading the task
- `[tool_use] list_inbox_files` — agent calling a tool
- `[tool_use] read_inbox_file(...)` — agent reading a payload file
- `[assistant] ...` — agent reasoning
- `[result] turns=N cost=$0.00NN` — run summary

**Question:** How many tool calls did the agent make? How many turns?

### 4. Inspect the output

Click the outbox file `report.md`. What did the agent produce?

### 5. Read the code

Open `agent_harness.py`. Find:

| Thing to find | Where |
|---------------|-------|
| The five MCP tool definitions | `make_tools()` function |
| Where instructions are loaded | `run_agent()` — look for `instruction.md` |
| The system prompt the agent receives | `system_prompt = (...)` |
| Where the SDK agentic loop runs | `async with ClaudeSDKClient(...)` |
| The guardrail placeholder | `run_guardrail_check()` |
| The custom tools placeholder | `CUSTOM_TOOLS` list |

---

## Reflection questions

1. What would happen if the agent tried to call the built-in `Bash` tool?
   *(Hint: look at `disallowed_tools` in `ClaudeAgentOptions`)*

2. What is the purpose of `MAX_TURNS`? What risk does it mitigate?

3. The agent reads `instruction.md` as a *system prompt*. What is the
   difference between a system prompt and a user message?

4. If you wanted the agent to also search the web, what would you need to do?

---

## Key takeaways

- The SDK drives the agentic loop; we only define tools and the task.
- Tools are the agent's only interface to the outside world.
- `allowed_tools` and `disallowed_tools` together form a permission boundary.
- All activity is logged — you can trace every decision the agent made.
