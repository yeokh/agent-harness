# Exercise 06 — Multi-Agent Pipeline

**Track:** Advanced | **Time:** ~40 min

---

## Objective

Chain multiple ADK agent calls in `web_app.py` to build a pipeline where each
stage uses a different model and handles a focused step.  This mirrors the
multi-agent patterns used in production AI systems.

---

## Background

### Why pipeline instead of one agent?

A single agent handling everything has limits:

- Long tasks accumulate context, increasing cost and reducing reliability.
- Different steps suit different models: cheap/fast for extraction, capable for
  reasoning.
- A specialist agent with a focused prompt is more reliable than a generalist.

A **pipeline** splits the work into stages:

```
┌─────────────────┐   temp dir   ┌─────────────────┐   outbox   ┌─────────────────┐
│   Agent Stage 1  │ ────────────▶│  Agent Stage 2   │ ──────────▶│  Agent Stage 3   │
│  fast model      │              │  capable model   │            │  validator       │
│  (extract data)  │              │  (write report)  │            │  (quality gate)  │
└─────────────────┘               └─────────────────┘            └─────────────────┘
```

In `web_app.py`, each stage calls `adk_agent.run_agent()` with a different
`model_id`, `inbox`, and `outbox`.  The output directory of one stage becomes
the input of the next.

### Two implementation approaches

| Approach | When to use |
|----------|------------|
| **Sequential `run_agent()` calls** | Simple pipelines, easy to debug, full control |
| **ADK `SequentialAgent`** | When stages need to share session state / memory |

This exercise covers both.

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
      Stage 1 (fast model)     — extract structured data from inbox → JSON in temp dir
      Stage 2 (capable model)  — read JSON, write final Markdown report to outbox
    """
    state.start()
    state.add_log("=== Pipeline started ===")

    # A temporary directory holds stage 1's output.  It is deleted automatically
    # when the `with` block exits — even if an exception is raised.
    with tempfile.TemporaryDirectory(prefix="adk-stage1-") as stage1_dir:
        stage1_out = Path(stage1_dir)

        # Helper: write one log line to AgentState and to agent.log
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

            # Pick the fastest available model for the extraction stage.
            fast_model = (
                "claude-haiku-4-5-20251001"  if "claude-haiku" in state.model else
                "gpt-4o-mini"               if os.environ.get("OPENAI_API_KEY") else
                state.model                 # fallback to selected model
            )

            # Stage 1 reads from inbox, writes JSON to the temp dir.
            # We pass a focused prompt that says "extract only, do not analyse".
            try:
                adk_agent.run_agent(
                    model_id=fast_model,
                    inbox=INBOX_DIR,
                    outbox=stage1_out,
                    log_callback=_log,
                )
            except Exception as exc:
                state.finish(f"Stage 1 failed: {exc}")
                return

            # Write a stage-separation marker to agent.log
            _log("─" * 60)
            _log("Stage 1 complete.  Intermediate files:")
            for p in sorted(stage1_out.iterdir()):
                _log(f"  {p.name}  ({p.stat().st_size} bytes)")

            # ── Stage 2: Analyse ─────────────────────────────────────────────
            _log("─" * 60)
            _log(f"Stage 2/2 — Analysing data and writing report ({state.model})...")

            # Stage 2 reads from the temp dir (stage 1 output), writes to outbox.
            # We use the model the user selected in the UI for the heavy reasoning.
            try:
                adk_agent.run_agent(
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

The pipeline needs two instructions — one per stage.  Create them as two
separate files and upload both to the inbox:

**inbox/instruction.md** (used by Stage 1 — extraction):
```markdown
# Stage 1: Data Extraction

Read all CSV files in the inbox.  For each file:
1. Parse every row into a JSON object.
2. Write the objects as a JSON array to the outbox using the original filename
   with a .json extension (e.g. sample_data.csv → sample_data.json).
3. Also write a schema file: <name>_schema.json listing column names and
   the data type you infer for each (string, number, or boolean).

Do not summarise or analyse the data — only extract.
Write outbox/agent.log with a one-line entry per file processed.
```

**inbox/stage2_instruction.md** (you will swap this in for the second run):
```markdown
# Stage 2: Analysis and Report

Read all .json files in the inbox.  These were extracted from CSV files.

Produce a single Markdown report at outbox/report.md with:
  ## Executive Summary   (2–3 sentences on key findings)
  ## Department Analysis (table: department, headcount, avg salary)
  ## Top Earners         (top 3 by salary with name, dept, salary, location)
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
    if not adk_agent.get_available_models():
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

Watch the browser log stream.  You should see:
```
=== Pipeline started ===
────────────────────────────────────────────────────────────
Stage 1/2 — Extracting structured data (fast model)...
model=claude-haiku-4-5-20251001  inbox=…/inbox  outbox=…/tmp-stage1-…
[tool_use] list_files(directory='inbox')
[tool_use] read_file(filepath='…/sample_data.csv')
[tool_use] write_file(filepath='sample_data.json', …)
────────────────────────────────────────────────────────────
Stage 1 complete.  Intermediate files:
  sample_data.json  (1842 bytes)
────────────────────────────────────────────────────────────
Stage 2/2 — Analysing data and writing report (claude-sonnet-4-6)...
[tool_use] list_files(directory='inbox')
[tool_use] read_file(filepath='sample_data.json')
[tool_use] write_file(filepath='outbox/report.md', …)
=== Pipeline completed successfully ===
```

Check the **Outbox** panel: `report.md` and `stats.json` should be present.

### 5. Add the guardrail as stage 0

Combine with Exercise 04 to validate `instruction.md` before either stage runs.
Inside `_pipeline_thread()`, add this block immediately after `state.start()`:

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

### 6. Add a validator as stage 3 (stretch goal)

After stage 2 completes, add a final pass that checks quality:

```python
            # ── Stage 3: Validate ─────────────────────────────────────────
            _log("─" * 60)
            _log("Stage 3/3 — Validating report structure (fast model)...")

            validation_inbox = OUTBOX_DIR   # stage 3 reads stage 2's output
            validation_outbox = OUTBOX_DIR  # writes validation result alongside

            try:
                adk_agent.run_agent(
                    model_id=fast_model,
                    inbox=validation_inbox,
                    outbox=validation_outbox,
                    log_callback=_log,
                )
            except Exception as exc:
                _log(f"Validation stage failed: {exc}")
```

Use an `instruction.md` that asks the validator to check `report.md` for
required sections and write `validation_ok.txt` or `validation_errors.txt`.

### 7. (Optional) Native ADK SequentialAgent

For pipelines where stages need to share context (e.g. stage 2 needs to know
what stage 1 decided), use ADK's built-in `SequentialAgent`:

```python
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types

async def _run_sequential_pipeline_async(log_callback):
    extract_agent = LlmAgent(
        name="extractor",
        model=_build_model("claude-haiku-4-5-20251001"),
        instruction="Extract CSV data as JSON.  Write to outbox.",
        tools=_make_tools(INBOX_DIR, OUTBOX_DIR),
    )
    analyse_agent = LlmAgent(
        name="analyser",
        model=_build_model(state.model),
        instruction="Read JSON from inbox (outbox of extractor).  Write report.",
        tools=_make_tools(OUTBOX_DIR, OUTBOX_DIR),
    )

    pipeline = SequentialAgent(
        name="pipeline",
        sub_agents=[extract_agent, analyse_agent],
    )

    runner  = InMemoryRunner(agent=pipeline, app_name="pipeline")
    session = await runner.session_service.create_session(
        app_name="pipeline", user_id="run_user"
    )
    msg = genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text("Run the full pipeline.")],
    )
    async for event in runner.run_async(
        user_id="run_user", session_id=session.id, new_message=msg
    ):
        for line in _format_event(event):
            log_callback(line)
```

The `SequentialAgent` passes context between sub-agents automatically via the
shared session — the analyser can see what the extractor said.

---

## Pipeline patterns

| Pattern | Description | Use case |
|---------|-------------|----------|
| Sequential | Output of stage N → input of N+1 | Data transformation pipelines |
| Fan-out | One input → multiple specialist agents run in parallel | Independent analyses |
| Fan-in | Multiple inputs → one aggregator | Combining parallel results |
| Guard | Validator before or after main agent | Safety checks, quality gates |
| Retry | Re-run failed stage with adjusted prompt | Error recovery |

**Fan-out with asyncio (stretch goal):**

```python
import asyncio

async def _fan_out(files: list[str], log_callback) -> None:
    """Run one agent per file, all in parallel."""
    tasks = [
        _run_async(
            model_id=state.model,
            inbox=INBOX_DIR,
            outbox=OUTBOX_DIR / f"result_{f}",
            log_callback=log_callback,
        )
        for f in files
    ]
    await asyncio.gather(*tasks)
```

---

## Reflection questions

1. Stage 1 uses a fast, cheap model and stage 2 uses the selected model.  What
   would break if you swapped them?  What determines the right model per stage?

2. Stage 1's output goes into a temp directory that is deleted after the `with`
   block.  If the pipeline crashes partway through stage 2, you cannot inspect
   stage 1's intermediate files.  How would you improve observability for
   debugging failed pipelines?

3. The fan-out pattern runs multiple agents in parallel via `asyncio.gather`.
   What new failure modes does parallelism introduce?  How would you handle
   one task failing while others succeed?

4. The `SequentialAgent` approach shares session context between stages; the
   `run_agent()` call approach does not.  Describe a scenario where shared
   context is necessary, and one where isolation between stages is preferable.

5. How does this pipeline compare to the claude-agent SDK approach, where you
   would spawn sub-agents using the Claude Agent SDK inside the same Python
   process?  What does each approach make easier or harder?
