# Workshop: Engineering an AI Agent with the Pi CLI

Welcome! In this workshop you will explore, extend, and customise the Pi CLI
Agent to understand how production headless AI agents are built and controlled.

---

## Prerequisites

Complete the [Quickstart](../Quickstart.md) and verify the agent runs before
starting the exercises.

---

## Learning objectives

By the end of this workshop you will be able to:

1. Explain the pi CLI agentic loop and how it differs from a single LLM call
2. Write task instructions in `instruction.md` that produce reliable agent behaviour
3. Extend agent capabilities using `skill.md` without writing Python
4. Implement a guardrail that validates instructions before the agent runs
5. Create and distribute reusable pi skills for different task domains
6. Chain multiple agent runs together to build multi-step pipelines

---

## Track overview

### Beginner track  *(~60 min)*

| Exercise | Topic |
|----------|-------|
| [01 — Explore](beginner/01_explore.md) | Run the agent, trace execution, understand the flow |
| [02 — Modify Instructions](beginner/02_modify_instructions.md) | Craft different task instructions; observe different behaviours |
| [03 — Add Skill Instructions](beginner/03_add_skill.md) | Extend skill.md to give the agent new capabilities |

### Advanced track  *(~90 min)*

| Exercise | Topic |
|----------|-------|
| [04 — Guardrail Check](advanced/04_guardrail.md) | Pre-flight safety filter using a separate Claude call |
| [05 — Custom Pi Skills](advanced/05_custom_skills.md) | Build and load reusable formal pi skill files |
| [06 — Multi-Agent Pipeline](advanced/06_multi_agent.md) | Chain agent runs; orchestrate specialist sub-agents |

---

## How to work through the exercises

1. Read the **Objective** and **Background** sections first.
2. Follow the **Steps** — code snippets and file examples are provided.
3. After each step, click **Run Agent** in the web UI and verify the change worked.
4. Answer the **Reflection** questions at the end of each exercise.

---

## Getting help

- Re-read [README.md](../README.md) for architecture details.
- Run `pi --help` for the full pi CLI reference.
- Check the live log stream in the browser for agent output.
- Ask the instructor!
