# Exercise 06 — Multi-Agent Pipeline

**Track:** Advanced | **Time:** ~40 min

---

## Objective

Chain multiple Strands `Agent` calls in `web_app.py` to build a pipeline where
each stage uses a different model and handles a focused step.  This mirrors
the multi-agent patterns used in production AI systems.

---

## Background

### Why pipeline instead of one agent?

A single agent handling everything has limits:

- Long tasks accumulate context, increasing cost and reducing reliability.
- Different steps suit different models: cheap/fast for extraction, capable for
  reasoning.
- A specialist agent with a focused system prompt is more reliable than a generalist.

A **pipeline** splits the work into stages:

```
┌─────────────────┐   temp dir   ┌─────────────────┐   outbox   ┌─────────────────┐
│   Agent Stage 1  │ ────────────▶│  Agent Stage 2   │ ──────────▶│  Agent Stage 3   │
│  fast model      │              │  capable model   │            │  validator       │
│  (extract data)  │              │  (write report)  │            │  (quality gate)  │
└─────────────────┘               └─────────────────┘            └─────────────────┘
```

In `web_app.py`, each stage calls `strands_agent.run_agent()` with a different
`model_key`, `inbox`, and `outbox`.  The output directory of one stage becomes
the input of the next.

### Strands sequential pipeline vs. ADK SequentialAgent

| Dimension | ADK `SequentialAgent` | Strands sequential `run_agent()` |
|-----------|----------------------|----------------------------------|
| Setup | Framework class (`SequentialAgent`) | Plain function calls |
| Shared context | Built-in (shared session) | Via temp directory (file-based) |
| Debuggability | ADK event stream | Each `run_agent()` logs independently |
| Complexity | Framework-level wiring | Just Python |

For most file-processing pipelines, the sequential `run_agent()` approach is
simpler and easier to debug.  For agents that need to share reasoning context
(not just files), Strands offers its own multi-agent patterns via sub-agents.

---

## Steps

### 1. Add `_pipeline_thread()` to `web_app.py`

Find the `# ── WORKSHOP PLACEHOLDER (Exercise 06 — Multi-Agent Pipeline)` comment
in `web_app.py` and replace it with:

```python
import tempfile  # add to imports at top of file if not already present

def _pipeline_thread() -> None:
    """
    Two-stage pipeline thread.
      Stage 1 (fast model)    — extract structured data from inbox → JSON in temp dir
      Stage 2 (capable model) — read JSON, write final Markdown report to outbox

    The temp directory is created per-run and deleted automatically after
    stage 2 completes (or if an exception is raised at any point).
    """
    state.start()
    state.add_log("=== Pipeline started ===")

    log_path = OUTBOX_DIR / "agent.log"
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="strands-stage1-") as stage1_dir:
        stage1_out = Path(stage1_dir)

        with log_path.open("w", encoding="utf-8") as log_fh:
            def _log(message: str) -> None:
                if message:
                    state.add_log(message)
                    log_fh.write(message + "\n")
                    log_fh.flush()

            # ── Stage 1: Extract ──────────────────────────────────────────────
            state.add_log("─" * 60)
            state.add_log("Stage 1/2 — Extracting structured data (fast model)...")

            # Use the fastest available model for the extraction stage.
            # The extraction task is mechanical (CSV→JSON), not creative,
            # so a cheap model is sufficient.
            fast_model = (
                "claude-haiku-4-5"   if os.environ.get("ANTHROPIC_API_KEY") else
                "gpt-4o-mini"        if os.environ.get("OPENAI_API_KEY") else
                state.model          # fallback to selected model
            )

            try:
                strands_agent.run_agent(
                    model_key=fast_model,
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

            # ── Stage 2: Analyse ──────────────────────────────────────────────
            _log("─" * 60)
            _log(f"Stage 2/2 — Analysing data and writing report ({state.model})...")

            # Stage 2 reads stage 1's output as its inbox.
            # We use the model the user selected for the heavy reasoning.
            try:
                strands_agent.run_agent(
                    model_key=state.model,
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

### 2. Add the pipeline API route

After `api_run_agent()` in `web_app.py`, add:

```python
@app.route("/api/agent/pipeline", methods=["POST"])
def api_run_pipeline():
    """Start the two-stage pipeline in a background thread."""
    if state.status == "running":
        return jsonify({"error": "Agent is already running"}), 409
    if not (INBOX_DIR / "instruction.md").exists():
        return jsonify({"error": "instruction.md not found in inbox"}), 400
    if not strands_agent.get_available_models():
        return jsonify({"error": "No API key configured"}), 400

    thread = threading.Thread(target=_pipeline_thread, daemon=True, name="pipeline")
    thread.start()
    return jsonify({"status": "started", "stages": 2})
```

### 3. Write two-stage instructions

The pipeline needs two instructions — one per stage.  Upload both to the inbox.

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

**inbox/stage2_instruction.md** (swap in for second run manually):
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

### 4. Run the pipeline

Restart `web_app.py`, then trigger the pipeline from the terminal:

```bash
curl -X POST http://localhost:8080/api/agent/pipeline
```

Or add a **Run Pipeline** button to `index.html`:

```html
<!-- Add next to the existing Run Agent button -->
<button class="btn btn-outline" id="pipelineBtn" onclick="runPipeline()">
  ⛓ Run Pipeline
</button>
```

```javascript
async function runPipeline() {
  const res  = await fetch('/api/agent/pipeline', { method: 'POST' });
  const data = await res.json();
  if (data.error) { toast(data.error, true); return; }
  logOffset = 0;
  clearLog(false);
  startLogStream();
  syncStatus();
}
```

Watch the browser log stream.  You should see:

```
=== Pipeline started ===
────────────────────────────────────────────────────────────
Stage 1/2 — Extracting structured data (fast model)...
model=claude-haiku-4-5  inbox=…/inbox  outbox=…/strands-stage1-…
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

### 5. Add the guardrail as stage 0

Combine with Exercise 04 to validate `instruction.md` before either stage runs.
Inside `_pipeline_thread()`, add this block immediately after `state.start()`:

```python
    # Stage 0: Guardrail — validate before either stage runs
    instructions = (INBOX_DIR / "instruction.md").read_text(encoding="utf-8")
    inbox_files  = [p.name for p in INBOX_DIR.iterdir() if p.is_file()]
    is_safe, reason = run_guardrail_check(instructions, inbox_files)
    state.add_log(f"Guardrail: {reason}")
    if not is_safe:
        state.finish(f"Guardrail blocked pipeline: {reason}")
        return
```

### 6. Add a validator as stage 3 (stretch goal)

After stage 2 completes, add a final validation pass:

```python
            # ── Stage 3: Validate ──────────────────────────────────────────
            _log("─" * 60)
            _log("Stage 3/3 — Validating report structure (fast model)...")

            try:
                strands_agent.run_agent(
                    model_key=fast_model,
                    # Stage 3 reads stage 2's output
                    inbox=OUTBOX_DIR,
                    outbox=OUTBOX_DIR,
                    log_callback=_log,
                )
            except Exception as exc:
                _log(f"Validation stage failed: {exc}")
```

Use an `instruction.md` that asks the validator to check `report.md` for
required sections and write `validation_ok.txt` or `validation_errors.txt`.

### 7. Fan-out pattern (stretch goal)

To process multiple files in parallel, use `concurrent.futures`:

```python
import concurrent.futures, tempfile

def _fan_out_thread() -> None:
    """Run one agent per inbox file, all in parallel."""
    state.start()
    state.add_log("=== Fan-out started ===")

    inbox_files = [p for p in INBOX_DIR.iterdir()
                   if p.is_file() and p.name != "instruction.md"]

    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    def _log(message):
        with lock:
            state.add_log(message)

    def process_one(filepath: Path):
        """Run a single-file agent in its own outbox subdirectory."""
        out = OUTBOX_DIR / filepath.stem
        out.mkdir(parents=True, exist_ok=True)
        strands_agent.run_agent(
            model_key=state.model,
            inbox=INBOX_DIR,
            outbox=out,
            log_callback=_log,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(process_one, f): f for f in inbox_files}
        for fut in concurrent.futures.as_completed(futures):
            fp = futures[fut]
            try:
                fut.result()
                _log(f"[meta] Completed: {fp.name}")
            except Exception as exc:
                _log(f"[error] Failed {fp.name}: {exc}")

    state.finish()
    state.add_log("=== Fan-out completed ===")
```

---

## Pipeline patterns

| Pattern | Description | Use case |
|---------|-------------|----------|
| Sequential | Output of stage N → input of N+1 | Data transformation pipelines |
| Fan-out | One input → multiple specialist agents run in parallel | Independent analyses |
| Fan-in | Multiple inputs → one aggregator | Combining parallel results |
| Guard | Validator before or after main agent | Safety checks, quality gates |
| Retry | Re-run failed stage with adjusted prompt | Error recovery |

---

## Reflection questions

1. Stage 1 uses a fast, cheap model and stage 2 uses the selected model.  What
   would break if you swapped them?  What determines the right model per stage?

2. Stage 1's output goes into a temp directory that is deleted after the `with`
   block.  If the pipeline crashes partway through stage 2, you cannot inspect
   stage 1's intermediate files.  How would you improve observability?

3. In the fan-out pattern, multiple `run_agent()` calls share a `threading.Lock`
   for logging.  What failure modes does parallelism introduce?  How would you
   handle one task failing while others succeed?

4. The sequential `run_agent()` pipeline does not share LLM context between
   stages — stage 2 only sees stage 1's file output.  When would sharing context
   be necessary, and how would you implement it in Strands?

5. How does this pipeline compare to the ADK `SequentialAgent` approach?  What
   does each make easier or harder to implement and debug?
