# Quickstart — Pi CLI Agent

Get the agent running in 5 minutes.

---

## Step 1 — Install the pi CLI

```bash
curl -fsSL https://pi.dev/install.sh | sh
```

Or with npm:

```bash
npm install -g @earendil-works/pi-coding-agent
```

Verify:

```bash
pi --version
```

---

## Step 2 — Set your API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Add it to your shell profile (`~/.bashrc`, `~/.zshrc`) to avoid setting it
every session.

---

## Step 3 — Enter the project

```bash
cd pi-cli-agent
```

---

## Step 4 — Inspect the inbox

```
inbox/
├── instruction.md   ← what the agent will do
├── skill.md         ← how the agent should behave
└── sample_data.csv  ← example payload
```

Open `inbox/instruction.md` — it asks the agent to analyse the CSV and
write a Markdown report.

---

## Step 5 — Start the web UI

```bash
python web_app.py
```

You will see:

```
  Pi CLI Agent Web UI
  ─────────────────────────────
  URL    : http://localhost:8080
  Inbox  : /path/to/inbox
  Outbox : /path/to/outbox
```

---

## Step 6 — Run the agent

1. Open **http://localhost:8080** in your browser
2. The inbox files are already listed (instruction.md, skill.md, sample_data.csv)
3. Click **Run Agent**
4. Watch the live log stream — the agent will:
   - Read `instruction.md` and `skill.md`
   - List and read `sample_data.csv`
   - Compute statistics
   - Write `outbox/report.md` and `outbox/summary.md`

---

## Step 7 — Inspect the output

Switch to the **Outbox** panel in the browser to read the generated files.

Or from the terminal:

```bash
ls outbox/
cat outbox/report.md
```

---

## What just happened?

```
web_app.py  (Flask — browser sends POST /api/agent/run)
  └─ background thread spawned:
       pi -p "<prompt>" --skill ./inbox/skill.md --no-session
                │
                │  agentic loop (managed by pi)
                ▼
         read instruction.md
         read skill.md  (loaded as pi skill — defines inbox/outbox protocol)
         ls ./inbox/
         read sample_data.csv
         write ./outbox/report.md
         write ./outbox/summary.md
                │
                ▼
         exit — pi stops when the task is complete
```

Log lines stream back to the browser in real time via SSE. The full run is
also saved to `outbox/agent.log`.

---

## Configuration

Change the model or port with environment variables:

```bash
# Use a different model
CLAUDE_MODEL=claude-haiku-4-5-20251001 python web_app.py

# Run on a different port
PORT=9000 python web_app.py

# Use a custom inbox/outbox location
INBOX_DIR=~/tasks/inbox OUTBOX_DIR=~/tasks/outbox python web_app.py
```

The model can also be switched at runtime from the web UI without restarting.

---

## Next steps

Work through the [workshop exercises](workshop/README.md) to learn how to:

- Modify `instruction.md` to give the agent new tasks
- Extend `skill.md` to change agent behaviour
- Add a guardrail safety check
- Build and use formal pi skills
- Chain multiple agent runs together
