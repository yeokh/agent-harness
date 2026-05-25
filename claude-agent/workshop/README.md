# Workshop: Engineering an AI Agent Harness

Welcome! In this workshop you will explore, modify, and extend the Claude Agent
Harness to understand how production AI agents are built.

---

## Prerequisites

Complete the [Quickstart](../Quickstart.md) and have a running agent harness
before starting the exercises.

---

## Learning objectives

By the end of this workshop you will be able to:

1. Explain what an agentic loop is and how it differs from a single LLM call
2. Write custom tool definitions that extend agent capabilities
3. Implement a guardrail agent that validates input before the main agent runs
4. Load skills dynamically from files uploaded at runtime
5. Understand how model selection ("brain swapping") affects agent behaviour
6. Describe multi-agent architectures and their trade-offs

---

## Track overview

### Beginner track  *(~60 min)*

| Exercise | Topic |
|----------|-------|
| [01 — Explore](beginner/01_explore.md) | Run the agent, read the code, understand the flow |
| [02 — Modify Instructions](beginner/02_modify_instructions.md) | Craft different task instructions; observe different behaviours |
| [03 — Add a Simple Tool](beginner/03_add_simple_tool.md) | Add a word-count tool; give the agent new capability |

### Advanced track  *(~90 min)*

| Exercise | Topic |
|----------|-------|
| [04 — Guardrail Agent](advanced/04_guardrail_agent.md) | Implement a Claude-as-judge safety filter |
| [05 — Custom Skills](advanced/05_custom_skills.md) | Load tools dynamically from skill files in the inbox |
| [06 — Multi-Agent](advanced/06_multi_agent.md) | Orchestrate multiple specialised agents |

### Demo scenarios  *(instructor-led)*

| Demo | Topic |
|------|-------|
| [D1 — Multi-step Workflow](demos/D1_multistep_workflow.md) | ReAct agent downloads CSV + plots text charts |
| [D2 — Tool Calling: Zip Files](demos/D2_zip_tool.md) | Agent inspects zip archives safely |
| [D3 — Brain Swapping](demos/D3_brain_swapping.md) | Model selection UI; capability vs. cost trade-offs |
| [D4 — Jailbreak Demo](demos/D4_jailbreak_demo.md) | Demonstrate and then prevent jail-breaking |

---

## How to work through the exercises

1. Read the **Objective** and **Background** sections first.
2. Follow the **Steps** — they include code snippets and file examples.
3. After each step, restart the web app and verify your change works.
4. Check the **Reflection** questions at the end of each exercise.

---

## Getting help

- Check the inline `# Workshop Exercise N` comments in `agent_harness.py`
- Re-read [README.md](../README.md) for architecture details
- Ask the instructor!
