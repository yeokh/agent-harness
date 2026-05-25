# Workshop: Engineering an AI Agent with Amazon Strands SDK

Welcome!  In this workshop you will explore, extend, and customise the Strands Agent
to understand how production file-processing AI agents are built and controlled
using **Amazon's Strands SDK** for Python.

---

## Prerequisites

1. Complete the [quick-start](../README.md#quick-start) and verify the agent runs
   end-to-end (click **Run Agent** and see output in the outbox) before starting.
2. Have at least one API key set (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or
   `OPENROUTER_API_KEY`).
3. Basic Python familiarity — you will read and edit `.py` files.

---

## Learning objectives

By the end of this workshop you will be able to:

1. Explain the **Strands agentic loop** and how `Agent(model, tools)` differs from
   a single LLM API call
2. Understand the Strands `@tool` decorator and how the LLM schema is built from
   Python type annotations and docstrings
3. Trace the three event types in the log stream: `[assistant]`, `[tool_use]`, `[result]`
4. Write `instruction.md` files that produce reliable, deterministic agent behaviour
5. Add new **Python tool functions** to extend what the agent can do
6. Implement a **guardrail** that validates `instruction.md` before the agent runs
7. Build **domain-specific tool modules** and load them conditionally
8. Chain multiple Strands `Agent` calls into a **multi-stage processing pipeline**

---

## Strands SDK — core concepts

### Single LLM call vs. Strands agentic loop

```
Single LLM call:
  prompt → LLM → response            (one round trip, no tools)

Strands agentic loop (agent(prompt)):
  prompt → LLM → tool call → tool result → LLM → tool call → … → final answer
                 ↑_________________________________↑
                 (repeated automatically until task is complete)
```

### The @tool decorator

```python
from strands import tool

@tool
def word_count(filepath: str) -> str:    ← type annotations → parameter schema
    """Count words in a file."""         ← docstring → tool description (LLM reads this)
    ...
    return "3 lines, 42 words"           ← return str → tool result fed back to LLM
```

### callback_handler events

The Strands `Agent` calls `callback_handler(**kwargs)` as it generates output:

| kwargs key | Meaning |
|------------|---------|
| `data` | A streaming text chunk from the model |
| `current_tool_use` | Dict with `name` and `input` of the tool being called |
| `complete` | `True` when the agent run is finished |

---

## Track overview

### Beginner track  *(~60 min)*

| Exercise | Topic |
|----------|-------|
| [01 — Explore](beginner/01_explore.md) | Run the agent, trace execution, understand Strands events |
| [02 — Modify Instructions](beginner/02_modify_instructions.md) | Change `instruction.md`; observe different outputs and model behaviours |
| [03 — Add a Python Tool](beginner/03_add_tool.md) | Write a new `@tool` function in `strands_agent.py` |

### Advanced track  *(~90 min)*

| Exercise | Topic |
|----------|-------|
| [04 — Guardrail Check](advanced/04_guardrail.md) | Pre-flight safety validation before the main agent runs |
| [05 — Custom Toolsets](advanced/05_custom_toolsets.md) | Organise tools into domain modules; load them conditionally |
| [06 — Multi-Agent Pipeline](advanced/06_multi_agent.md) | Chain agent runs; build a two-stage extract → analyse pipeline |

---

## How to work through the exercises

1. Read the **Objective** and **Background** sections first.
2. Follow the numbered **Steps** — code snippets are provided for every change.
3. After each step, click **Run Agent** in the web UI and verify the change worked
   by checking the log stream and the outbox.
4. Answer the **Reflection** questions at the end of each exercise before moving on.

---

## Key files to keep open

| File | Role |
|------|------|
| `strands_agent.py` | Agent logic — model registry, @tool functions, Strands Agent |
| `web_app.py`       | Web layer — Flask endpoints, SSE streaming, inbox editor |
| `inbox/instruction.md` | Task definition — what the agent does this run (editable in browser) |
| Browser terminal   | Live event stream — what the agent is doing right now |

---

## Getting help

- Re-read [README.md](../README.md) for architecture details.
- Check the [Strands SDK docs](https://strandsagents.com/latest/) for API reference.
- Browse the [Strands SDK GitHub](https://github.com/strands-agents/sdk-python) for examples.
- Look for `# WORKSHOP` comments in `strands_agent.py` and `web_app.py` — each
  comment points to the relevant exercise and explains what to change.
- Ask the instructor!
