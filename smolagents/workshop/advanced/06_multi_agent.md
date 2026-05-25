# Exercise 06 — Multi-Agent Pipeline

**Track:** Advanced | **Time:** ~40 min

---

## Objective

Chain multiple Smolagents agent calls in `web_app.py` to build a pipeline where
each stage uses a different model and handles a focused step.  Also explore
`ManagedAgent` — smolagents' native orchestration primitive for hierarchical
multi-agent systems.

---

## Background

### Why pipeline instead of one agent?

A single agent handling everything has limits:

- Long tasks accumulate context, increasing cost and reducing reliability.
- Different steps suit different models: cheap/fast for extraction, capable for reasoning.
- A specialist agent with a focused prompt is more reliable than a generalist.

A **pipeline** splits the work into stages:

```
┌──────────────────┐  temp dir   ┌──────────────────┐  outbox  ┌────────────────┐
│  Agent Stage 1   │ ───────────▶│  Agent Stage 2   │ ────────▶│  Agent Stage 3 │
│  fast model      │             │  capable model   │          │  validator      │
│  (extract data)  │             │  (write report)  │          │  (quality gate) │
└──────────────────┘             └──────────────────┘          └────────────────┘
```

Each stage calls `smolagent_agent.run_agent()` with a different `model_id`,
`inbox`, and `outbox`.

### Smolagents vs ADK for pipelines

| Approach | ADK | Smolagents |
|----------|-----|-----------|
| Sequential `run_agent()` calls | ✅ `adk_agent.run_agent()` (same pattern) | ✅ `smolagent_agent.run_agent()` |
| Native orchestration | `SequentialAgent` | `ManagedAgent` + `ToolCallingAgent` |
| Shared session between stages | Via `SequentialAgent` | Via `ManagedAgent` |

This exercise covers both approaches.

---

## Steps

### 1. Add a `_pipeline_thread()` to `web_app.py`

Find the `# ── WORKSHOP PLACEHOLDER (Exercise 06 — Multi-Agent Pipeline)` comment
in `web_app.py` and replace it with:

```python
import tempfile  # add to imports at top of file if not present

def _pipeline_thread() -> None:
    """
    Two-stage pipeline thread.
      Stage 1 (fast model)    — extract structured data from inbox → JSON in temp dir
      Stage 2 (capable model) — read JSON, write final Markdown report to outbox
    """
    state.start()
    state.add_log("=== Pipeline started ===")

    with tempfile.TemporaryDirectory(prefix="smolagents-stage1-") as stage1_dir:
        stage1_out = Path(stage1_dir)

        log_path = OUTBOX_DIR / "agent.log"
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

        with log_path.open("w", encoding="utf-8") as log_fh:
            def _log(message: str) -> None:
                if message:
                    state.add_log(message)
                    log_fh.write(message + "\n")
                    log_fh.flush()

            # ── Stage 1: Extract ─────────────────────────────────────────────
            state.add_log("─" * 60)
            state.add_log("Stage 1/2 — Extracting structured data (fast model)...")

            fast_model = (
                "claude-haiku-4-5-20251001" if "claude" in state.model else
                "gpt-4o-mini"               if os.environ.get("OPENAI_API_KEY") else
                state.model
            )

            try:
                smolagent_agent.run_agent(
                    model_id=fast_model,
                    inbox=INBOX_DIR,
                    outbox=stage1_out,
                    log_callback=_log,
                )
            except Exception as exc:
                state.finish(f"Stage 1 failed: {exc}")
                return

            _log("─" * 60)
            _log("Stage 1 complete.  Intermediate files:")
            for p in sorted(stage1_out.iterdir()):
                _log(f"  {p.name}  ({p.stat().st_size} bytes)")

            # ── Stage 2: Analyse ─────────────────────────────────────────────
            _log("─" * 60)
            _log(f"Stage 2/2 — Analysing data and writing report ({state.model})...")

            try:
                smolagent_agent.run_agent(
                    model_id=state.model,
                    inbox=stage1_out,
                    outbox=OUTBOX_DIR,
                    log_callback=_log,
                )
            except Exception as exc:
                state.finish(f"Stage 2 failed: {exc}")
                return

    state.finish()
    state.add_log("=== Pipeline completed successfully ===")
```

### 2. Write a two-stage instruction pair

Upload both files to the inbox:

**inbox/instruction.md** (Stage 1 — extraction):
```markdown
# Stage 1: Data Extraction

Read all CSV files in the inbox.  For each file:
1. Parse every row into a JSON object.
2. Write the objects as a JSON array to the outbox using the original filename
   with a .json extension (e.g. sample_data.csv → sample_data.json).
3. Also write a schema file: <name>_schema.json listing column names and
   the data type you infer for each (string, number, or boolean).

Do not summarise or analyse — only extract.
Write outbox/agent.log with a one-line entry per file processed.
```

**inbox/stage2_instruction.md** (used in the second stage run):
```markdown
# Stage 2: Analysis and Report

Read all .json files in the inbox.

Produce a Markdown report at outbox/report.md with:
  ## Executive Summary   (2–3 sentences on key findings)
  ## Department Analysis (table: department, headcount, avg salary)
  ## Top Earners         (top 3 by salary)
  ## Conclusion          (one sentence)

Also write outbox/stats.json with:
  total_employees, average_salary, department_count, top_earner_name
```

### 3. Add the pipeline API endpoint

After `api_run_agent()` in `web_app.py`, add:

```python
@app.route("/api/agent/pipeline", methods=["POST"])
def api_run_pipeline():
    """Start the two-stage pipeline in a background thread."""
    if state.status == "running":
        return jsonify({"error": "Agent is already running"}), 409
    if not (INBOX_DIR / "instruction.md").exists():
        return jsonify({"error": "instruction.md not found in inbox"}), 400
    if not smolagent_agent.get_available_models():
        return jsonify({"error": "No API key configured"}), 400

    thread = threading.Thread(target=_pipeline_thread, daemon=True, name="pipeline")
    thread.start()
    return jsonify({"status": "started", "stages": 2})
```

### 4. Run the pipeline

Restart `web_app.py`, then trigger the pipeline:

```bash
curl -X POST http://localhost:8080/api/agent/pipeline
```

Watch the browser log stream:
```
=== Pipeline started ===
────────────────────────────────────────────────────────────
Stage 1/2 — Extracting structured data (fast model)...
model=claude-haiku-4-5-20251001  inbox=…/inbox  outbox=…/tmp-stage1-…
[tool_use] list_files(directory='inbox')
[tool_use] read_file(filepath='sample_data.csv')
[tool_use] write_file(filepath='sample_data.json', …)
────────────────────────────────────────────────────────────
Stage 1 complete.  Intermediate files:
  sample_data.json  (1842 bytes)
────────────────────────────────────────────────────────────
Stage 2/2 — Analysing data and writing report (claude-sonnet-4-6)...
[tool_use] read_file(filepath='sample_data.json')
[tool_use] write_file(filepath='report.md', …)
=== Pipeline completed successfully ===
```

### 5. Add guardrail as stage 0 (combine with Exercise 04)

Inside `_pipeline_thread()`, immediately after `state.start()`:

```python
    # Stage 0: Guardrail
    instructions = (INBOX_DIR / "instruction.md").read_text(encoding="utf-8")
    inbox_files  = [p.name for p in INBOX_DIR.iterdir() if p.is_file()]
    is_safe, reason = run_guardrail_check(instructions, inbox_files)
    state.add_log(f"Guardrail: {reason}")
    if not is_safe:
        state.finish(f"Guardrail blocked pipeline: {reason}")
        return
```

### 6. Native Smolagents: `ManagedAgent` orchestration (stretch goal)

Smolagents has a native multi-agent primitive called `ManagedAgent`.  Unlike
the sequential `run_agent()` approach above (where stages run independently),
`ManagedAgent` embeds specialised agents as **tools** inside an orchestrator:

```python
from smolagents import ToolCallingAgent, LiteLLMModel, ManagedAgent

def _run_managed_pipeline(log_callback):
    model_fast = LiteLLMModel(model_id="anthropic/claude-haiku-4-5-20251001",
                              api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    model_main = smolagent_agent._build_model(state.model)

    # Specialist: extraction agent
    extractor = ToolCallingAgent(
        tools=smolagent_agent._make_tools(INBOX_DIR, OUTBOX_DIR),
        model=model_fast,
        verbosity_level=0,
        max_steps=20,
    )
    managed_extractor = ManagedAgent(
        agent=extractor,
        name="data_extractor",
        description=(
            "Extracts structured data from CSV files in the inbox and writes "
            "JSON output to the outbox.  Call with a clear extraction task."
        ),
    )

    # Orchestrator: uses managed_extractor as a tool, then writes the report
    orchestrator = ToolCallingAgent(
        tools=[managed_extractor] + smolagent_agent._make_tools(INBOX_DIR, OUTBOX_DIR),
        model=model_main,
        step_callbacks=[lambda step: [log_callback(l)
                                      for l in smolagent_agent._format_step(step)]],
        verbosity_level=0,
        max_steps=20,
    )

    task = (
        "First call data_extractor to extract all CSV files from the inbox as JSON. "
        "Then read the JSON output and write a Markdown report to outbox/report.md "
        "with sections: Executive Summary, Findings, Conclusion."
    )
    result = orchestrator.run(task)
    if result:
        log_callback(f"[assistant] {str(result)[:400]}")
```

**When to use `ManagedAgent` vs sequential `run_agent()` calls:**

| Aspect | Sequential `run_agent()` | `ManagedAgent` orchestration |
|--------|--------------------------|------------------------------|
| Stage communication | Files in temp dir | Orchestrator sees sub-agent text replies |
| Debugging | Easy — stages logged separately | Harder — sub-agent runs are nested |
| Stage isolation | Complete | Sub-agent shares LLM context |
| Parallelism | Requires threads | Natural via multiple `ManagedAgent` tools |
| ADK equivalent | Sequential `run_agent()` calls | `SequentialAgent` / `ParallelAgent` |

---

## Pipeline patterns

| Pattern | Description | Use case |
|---------|-------------|----------|
| Sequential | Output of stage N → input of N+1 | Data transformation pipelines |
| Fan-out | One input → multiple agents in parallel | Independent analyses |
| Fan-in | Multiple inputs → one aggregator | Combining parallel results |
| Guard | Validator before or after main agent | Safety checks, quality gates |
| ManagedAgent | Sub-agent as a tool for an orchestrator | Hierarchical reasoning |

---

## Reflection questions

1. Stage 1 uses a fast, cheap model and stage 2 uses the selected model.  What
   would break if you swapped them?

2. Stage 1's output goes into a temp directory deleted after the `with` block.
   If the pipeline crashes during stage 2, you cannot inspect stage 1's files.
   How would you improve observability for failed pipelines?

3. The `ManagedAgent` approach lets the orchestrator see what sub-agents
   *said* (text replies), not just their file output.  Describe a scenario
   where this is necessary vs. one where file-based isolation is preferable.

4. Compare this pipeline to the ADK version.  The `_pipeline_thread()` code
   is nearly identical — only the import changed.  What does this say about
   the relationship between the web layer and the agent framework?

5. In the `ManagedAgent` example, we pass `_format_step` to the orchestrator
   but not the sub-agent.  What log output would you miss if you also added
   step_callbacks to the extractor?
