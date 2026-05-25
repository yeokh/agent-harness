# Exercise 06 — Multi-Agent Orchestration

**Track:** Advanced | **Time:** ~40 min

---

## Objective

Extend the harness to run two agents in sequence: a **planner** agent that
decomposes the task into steps, followed by a **worker** agent that executes
them. This introduces the concept of agent orchestration.

---

## Background

Multi-agent systems split complex tasks between specialised agents:

```
User instruction
      │
      ▼
 ┌──────────┐   plan.md   ┌──────────┐   results
 │ Planner  │ ──────────▶ │  Worker  │ ──────────▶ outbox
 │  Agent   │             │  Agent   │
 └──────────┘             └──────────┘
```

**Why split into two agents?**

- **Separation of concerns**: the planner thinks; the worker acts.
- **Auditability**: you can inspect and modify the plan before executing it.
- **Error recovery**: if the worker fails, you can re-run it from the plan.
- **Cost control**: use a cheap model for planning, expensive model for execution.

---

## Steps

### 1. Add an orchestrator function to `agent_harness.py`

Add this function *before* `run_agent()`:

```python
async def run_planner_agent(
    inbox_dir: Path,
    outbox_dir: Path,
    log_callback: Callable[[str], None] | None = None,
) -> Path:
    """
    Phase 1: A planner agent reads the instruction and produces a step-by-step
    plan written to outbox/plan.md.
    """
    instruction_file = inbox_dir / "instruction.md"
    instructions = instruction_file.read_text(encoding="utf-8")

    planner_prompt = (
        "You are a task planning agent. Your ONLY job is to decompose the given "
        "task into a numbered list of concrete, actionable steps.\n\n"
        "Write the plan to outbox/plan.md as a Markdown numbered list.\n"
        "Each step must be self-contained and verifiable.\n"
        "Do NOT execute any steps — only write the plan.\n\n"
        "TASK:\n" + instructions
    )

    options = ClaudeAgentOptions(
        system_prompt=planner_prompt,
        mcp_servers={"agent-tools": create_sdk_mcp_server(
            name="agent-tools",
            version="1.0.0",
            tools=make_tools(inbox_dir, outbox_dir),
        )},
        allowed_tools=[
            "mcp__agent-tools__list_inbox_files",
            "mcp__agent-tools__write_output",
        ],
        disallowed_tools=["Read", "Write", "Edit", "Bash"],
        model="claude-haiku-4-5-20251001",   # Fast + cheap for planning
        max_turns=10,
    )

    if log_callback:
        log_callback("=== PHASE 1: Planner Agent ===")

    async with ClaudeSDKClient(options=options) as client:
        await client.query("Write the plan now.")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and log_callback:
                        log_callback(f"[planner] {block.text[:200]}")

    plan_file = outbox_dir / "plan.md"
    if not plan_file.exists():
        raise RuntimeError("Planner did not produce plan.md")
    return plan_file
```

### 2. Create a two-phase `run_orchestrated_agent()`

```python
async def run_orchestrated_agent(
    inbox_dir: Path,
    outbox_dir: Path,
    log_callback: Callable[[str], None] | None = None,
) -> None:
    """
    Two-phase orchestration:
      Phase 1 — Planner agent writes plan.md
      Phase 2 — Worker agent executes the plan
    """
    # Phase 1: planning
    plan_file = await run_planner_agent(inbox_dir, outbox_dir, log_callback)
    if log_callback:
        log_callback(f"Plan written to {plan_file}")

    # Optionally pause here for human review of plan.md
    # (In a real system you'd have a webhook or approval UI)

    # Phase 2: execution — inject the plan into the instruction
    plan_text  = plan_file.read_text(encoding="utf-8")
    orig_instr = (inbox_dir / "instruction.md").read_text(encoding="utf-8")

    injected = (
        f"{orig_instr}\n\n"
        f"---\n\n"
        f"## Execution Plan\n\n"
        f"Follow these steps exactly:\n\n{plan_text}"
    )

    # Temporarily swap instruction with the annotated version
    tmp_file = inbox_dir / "_instruction_with_plan.md"
    tmp_file.write_text(injected, encoding="utf-8")

    try:
        # Run the main agent using the enriched instruction
        await run_agent(inbox_dir, outbox_dir, log_callback)
    finally:
        tmp_file.unlink(missing_ok=True)
```

### 3. Wire it into `web_app.py`

In `_agent_thread()`, change:
```python
anyio.run(run_agent, INBOX_DIR, OUTBOX_DIR, state.add_log)
```
to:
```python
anyio.run(run_orchestrated_agent, INBOX_DIR, OUTBOX_DIR, state.add_log)
```

### 4. Test with a complex instruction

```markdown
# Task: Comprehensive Dataset Report

Read all files in the inbox. Produce a comprehensive report that includes:
- An executive summary
- A data quality assessment
- Key statistics for numeric columns
- Recommendations for data cleaning
- A suggested follow-up analysis plan

Write separate sections to separate files in the outbox.
```

**Check the outbox** — you should see `plan.md` appear first, then the
worker's output files.

---

## Variations to explore

### A. Human-in-the-loop

Add an API endpoint `POST /api/agent/approve-plan` that:
1. Pauses between phases 1 and 2
2. Waits for the user to review `plan.md` and click "Approve" in the UI
3. Only then runs the worker agent

### B. Specialist agents

Instead of one worker, dispatch to *specialist* agents based on file type:

```python
if plan_mentions_csv:
    await run_csv_specialist(inbox_dir, outbox_dir)
if plan_mentions_json:
    await run_json_specialist(inbox_dir, outbox_dir)
```

### C. Critic agent

Add a third agent that reviews the worker's output and scores it 1–10.
If the score is below 7, re-run the worker with the critic's feedback.

---

## Reflection questions

1. What are the failure modes of a two-agent pipeline? What happens if the
   planner produces a bad plan?

2. The planner uses `claude-haiku` and the worker uses `claude-opus`. What are
   the cost and quality trade-offs of this choice?

3. In the "human-in-the-loop" variation, where is the state stored between the
   two phases? What happens if the server restarts between phases?

4. How would you implement a **retry loop** where the critic agent feeds back
   to the worker until a quality threshold is met?
