# Exercise 06 — Multi-Agent Pipeline

**Track:** Advanced | **Time:** ~40 min

---

## Objective

Chain multiple pi agent runs in `web_app.py` to build a pipeline where each
agent handles one specialised step. This mirrors the multi-agent patterns
used in production AI systems.

---

## Background

A single agent doing everything is simple but has limits:

- Long tasks accumulate context, increasing cost and reducing reliability.
- Different steps may need different models or tool sets.
- A specialist agent with a focused skill performs more reliably than a
  generalist handling everything.

A **pipeline** splits the work:

```
┌──────────────┐    outbox-1    ┌──────────────┐    outbox-2    ┌──────────────┐
│   Agent 1    │ ─────────────▶ │   Agent 2    │ ─────────────▶ │   Agent 3    │
│  (extract)   │                │  (analyse)   │                │   (report)   │
└──────────────┘                └──────────────┘                └──────────────┘
```

In `web_app.py`, each stage is a separate `pi -p "..."` subprocess running
in a background thread. The output directory of one stage becomes the input
of the next.

---

## Steps

### 1. Extract a `_run_pi()` helper

Open `web_app.py`. The subprocess logic inside `_agent_thread()` will be
reused for each pipeline stage. Extract it into a standalone helper:

```python
def _run_pi(
    prompt: str,
    inbox: Path,
    outbox: Path,
    model: str,
    skill: Path | None = None,
) -> int:
    """Run a single pi agent pass. Returns the exit code."""
    cmd = [
        "pi", "-p", prompt,
        "--no-session",
        "--model", model,
    ]
    if skill and skill.exists():
        cmd += ["--skill", str(skill)]

    outbox.mkdir(parents=True, exist_ok=True)
    log_path = outbox / "agent.log"

    try:
        with log_path.open("w", encoding="utf-8") as log_fh:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\n")
                if line:
                    state.add_log(line)
                    log_fh.write(line + "\n")
                    log_fh.flush()
            proc.wait()
        return proc.returncode
    except FileNotFoundError:
        state.add_log("ERROR: pi CLI not found")
        return 1
```

Now simplify `_agent_thread()` to call `_run_pi()` instead of duplicating
the subprocess code.

### 2. Build a two-stage pipeline thread

Add a `_pipeline_thread()` function to `web_app.py`:

```python
import tempfile

def _pipeline_thread() -> None:
    """
    Background thread: two-stage pipeline.
      Stage 1 (Haiku)  — extract structured data from CSV → intermediate JSON
      Stage 2 (Sonnet) — analyse JSON and write the final report
    """
    state.start()
    state.add_log("=== Pipeline started ===")

    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    with tempfile.TemporaryDirectory(prefix="pi-stage1-") as stage1_dir:
        stage1_out = Path(stage1_dir)

        # ── Stage 1: Extract ─────────────────────────────────────────────────
        state.add_log("─" * 60)
        state.add_log("Stage 1/2 — Extracting structured data (Haiku)...")
        rc = _run_pi(
            prompt=(
                f"Read {INBOX_DIR}/instruction.md then read all CSV files in {INBOX_DIR}/. "
                "Extract the raw data as JSON arrays and write one file per CSV to "
                f"{stage1_out}/ using the filename pattern <original_name>.json. "
                "Do not analyse — only extract."
            ),
            inbox=INBOX_DIR,
            outbox=stage1_out,
            model="claude-haiku-4-5-20251001",   # fast, cheap for extraction
            skill=INBOX_DIR / "skill.md",
        )
        if rc != 0:
            state.finish(f"Stage 1 failed with exit code {rc}")
            return

        # ── Stage 2: Analyse ─────────────────────────────────────────────────
        state.add_log("─" * 60)
        state.add_log("Stage 2/2 — Analysing data and writing report (Sonnet)...")
        rc = _run_pi(
            prompt=(
                f"Read all JSON files in {stage1_out}/. Each file contains employee data "
                "extracted from a CSV. Analyse the data and write a full Markdown "
                f"report to {OUTBOX_DIR}/report.md and a JSON summary to {OUTBOX_DIR}/stats.json."
            ),
            inbox=stage1_out,
            outbox=OUTBOX_DIR,
            model=model,
        )
        if rc != 0:
            state.finish(f"Stage 2 failed with exit code {rc}")
            return

    state.finish()
    state.add_log("=== Pipeline completed successfully ===")
```

### 3. Add a pipeline API endpoint

Add a new route to `web_app.py`:

```python
@app.route("/api/agent/pipeline", methods=["POST"])
def api_run_pipeline():
    if state.status == "running":
        return jsonify({"error": "Agent is already running"}), 409
    if not (INBOX_DIR / "instruction.md").exists():
        return jsonify({"error": "instruction.md not found in inbox — upload it first"}), 400

    thread = threading.Thread(target=_pipeline_thread, daemon=True, name="pipeline")
    thread.start()
    return jsonify({"status": "started"})
```

### 4. Run the pipeline

Restart `web_app.py`, then trigger the pipeline from the terminal:

```bash
curl -X POST http://localhost:8080/api/agent/pipeline
```

Or add a **Run Pipeline** button to the web UI by calling the same endpoint
from JavaScript.

Watch the log stream in the browser:
- Stage 1 (Haiku) runs first — fast, cheap, produces JSON
- Stage 2 (Sonnet) runs second — reads the JSON and writes the report

Check the outputs in the **Outbox** panel, or from the terminal:

```bash
ls outbox/
cat outbox/report.md
cat outbox/stats.json
```

### 5. Add a guardrail as stage 0

Combine with Exercise 04 to add a guardrail check before stage 1:

```python
def _pipeline_thread() -> None:
    state.start()
    state.add_log("=== Pipeline started ===")

    # Stage 0: Guardrail
    instructions = (INBOX_DIR / "instruction.md").read_text(encoding="utf-8")
    inbox_files  = [p.name for p in INBOX_DIR.iterdir() if p.is_file()]
    is_safe, reason = run_guardrail_check(instructions, inbox_files)
    state.add_log(f"Guardrail: {reason}")
    if not is_safe:
        state.finish(f"Guardrail blocked: {reason}")
        return

    # Stage 1, 2 as above...
```

### 6. Add a validator as stage 3 (stretch goal)

Add a final pi call that reads the report and checks it meets quality criteria:

```python
        # Stage 3: Validate
        state.add_log("Stage 3/3 — Validating report structure (Haiku)...")
        rc = _run_pi(
            prompt=(
                f"Read {OUTBOX_DIR}/report.md. Verify it contains: an Executive Summary, "
                "at least one data table, and a Conclusion. If any section is missing, "
                f"write {OUTBOX_DIR}/validation_errors.txt with the list of missing sections. "
                f"If all sections are present, write {OUTBOX_DIR}/validation_ok.txt."
            ),
            inbox=OUTBOX_DIR,   # stage 3 reads stage 2's output
            outbox=OUTBOX_DIR,
            model="claude-haiku-4-5-20251001",
        )
```

---

## Pipeline patterns

| Pattern | Description | Use case |
|---------|-------------|----------|
| Sequential | Output of stage N → input of stage N+1 | Data transformation pipelines |
| Fan-out | One input → multiple specialist agents | Parallel independent analyses |
| Fan-in | Multiple inputs → one aggregator | Combining results from parallel runs |
| Guard | Validator before or after main agent | Safety checks, quality gates |
| Retry | Re-run failed stages with different prompt | Error recovery |

---

## Reflection questions

1. The pipeline uses Haiku for extraction and Sonnet for analysis. What
   determines the right model for each stage? What would break if you swapped them?

2. Stage 1's output goes into a temp directory. What are the implications
   for debugging a failed pipeline? How would you improve observability?

3. A fan-out pipeline spawns multiple pi processes simultaneously. What
   Python primitive would you use to run them in parallel? What new failure
   modes does parallelism introduce?

4. How does this multi-agent design compare to the claude-agent SDK approach,
   where you would spawn sub-agents using `ClaudeSDKClient` inside the same
   Python process?
