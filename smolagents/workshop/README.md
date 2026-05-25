# Workshop: Engineering an AI Agent with HuggingFace Smolagents

Welcome!  In this workshop you will explore, extend, and customise the Smolagents Agent
to understand how production file-processing AI agents are built and controlled
using **HuggingFace Smolagents** for Python.

If you have also worked through the **ADK Agent** workshop, you will notice that
the architecture, exercises, and web UI are intentionally parallel — the goal is
to compare how the same agent patterns are expressed in two different frameworks.

---

## Prerequisites

1. Complete the quick-start and verify the agent runs end-to-end (click
   **Run Agent** and see output in the outbox) before starting.
2. Have at least one API key set (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or
   `OPENROUTER_API_KEY`).
3. Basic Python familiarity — you will read and edit `.py` files.

### Quick-start

```bash
cd smolagents
pip install -e .                         # installs smolagents[litellm] + flask
cp .env.example .env
# edit .env and set at least one API key
source .env  # or: export ANTHROPIC_API_KEY=sk-ant-...
python web_app.py
```

Open **http://localhost:8080** in your browser.

---

## Learning objectives

By the end of this workshop you will be able to:

1. Explain the **Smolagents agentic loop** and how it differs from a single LLM API call
2. Describe how `ToolCallingAgent` differs from `CodeAgent` and when to use each
3. Identify the three types of smolagents step (`ActionStep`, `PlanningStep`, `FinalAnswerStep`)
4. Use the **`@tool` decorator** to register Python functions as agent tools
5. Implement a **guardrail** that validates `instruction.md` before the agent runs
6. Build **domain-specific tool modules** and load them conditionally
7. Chain multiple agent calls into a **multi-stage processing pipeline**

---

## Smolagents vs ADK — key differences at a glance

| Aspect | ADK (adk_agent.py) | Smolagents (smolagent_agent.py) |
|--------|-------------------|---------------------------------|
| Agent type | `LlmAgent` | `ToolCallingAgent` |
| Execution model | Async (`asyncio`) | Synchronous |
| Tool registration | Plain Python functions | Must wrap with `@tool` / `tool()` |
| Event/step stream | Async `Event` objects | Synchronous `step_callbacks` |
| System prompt | Custom (passed to `LlmAgent`) | Framework default (includes tool schema) |
| Task prompt | Hardcoded in `_run_async()` | Passed to `agent.run(task)` |
| Model wrapper | `LiteLlm` (ADK class) | `LiteLLMModel` (smolagents class) |

The web layer (`web_app.py`) and the HTML/JS UI are **identical** between the two
projects — the web layer does not need to know which agent framework is underneath.

---

## Track overview

### Beginner track  *(~60 min)*

| Exercise | Topic |
|----------|-------|
| [01 — Explore](beginner/01_explore.md) | Run the agent, trace execution, understand smolagents steps |
| [02 — Modify Instructions](beginner/02_modify_instructions.md) | Change `instruction.md`; observe different outputs and model behaviours |
| [03 — Add a Python Tool](beginner/03_add_tool.md) | Write a new tool using the `@tool` decorator in `smolagent_agent.py` |

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
| `smolagent_agent.py` | Agent logic — model registry, tool definitions, smolagents runner |
| `web_app.py`         | Web layer — Flask endpoints, SSE streaming, thread management |
| `inbox/instruction.md` | Task definition — what the agent does this run |
| Browser terminal | Live smolagents step stream — what the agent is doing right now |

---

## Getting help

- Re-read [README.md](../README.md) for architecture details.
- Check [HuggingFace Smolagents docs](https://huggingface.co/docs/smolagents) for API reference.
- Check [Smolagents GitHub](https://github.com/huggingface/smolagents) for source and examples.
- Look for `# WORKSHOP` comments in `smolagent_agent.py` and `web_app.py` — each
  comment points to the relevant exercise and explains what to change.
- Ask the instructor!
