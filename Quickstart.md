# Quickstart — Claude Agent Harness

Get from zero to a running agent in 5 minutes.

---

## Step 1 — Prerequisites

You need:
- **Podman** 4.x+ installed ([podman.io](https://podman.io/))
- An **Anthropic API key** from [console.anthropic.com](https://console.anthropic.com/)

Check Podman is working:
```bash
podman --version
```

---

## Step 2 — Set your API key

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
```

Add this to your `~/.bashrc` or `~/.zshrc` to make it permanent.

---

## Step 3 — Write an instruction file

Create `inbox/instruction.md` (a sample already exists in this repo):

```markdown
# Task

Read all CSV files in the inbox.
For each file, count the rows and list the column names.
Write a Markdown summary to `outbox/summary.md`.
When finished, write "DONE" as the last line.
```

The instruction file tells the agent what to do. It is loaded as the agent's
task prompt before each run.

---

## Step 4 — (Optional) Add payload files

Drop any files the agent should process into the `inbox/` folder:

```bash
cp my_data.csv inbox/
cp my_report.json inbox/
```

The agent can list and read these files using its built-in tools.

---

## Step 5 — Build and run

```bash
chmod +x run.sh
./run.sh
```

The script:
1. Builds the container image (first run only — cached after that)
2. Starts the Flask web application
3. Mounts `./inbox` and `./outbox` into the container

---

## Step 6 — Open the web UI

Visit **http://localhost:8080** in your browser.

You will see:
- **Inbox** panel (left) — lists files in `./inbox/`
- **Outbox** panel (left) — lists files written by the agent
- **File viewer** (right) — click any file to see its contents
- **Run Agent** button — starts the agent
- **Log panel** (bottom) — streams the agent's activity in real-time

---

## Step 7 — Run the agent

1. Click **▶ Run Agent**.
2. Watch the log panel as the agent reads your instruction file and payload files.
3. When complete, new files appear in the **Outbox** panel.
4. Click any outbox file to view the results.

---

## Common options

Run on a different port:
```bash
./run.sh -p 9090
```

Use a different model:
```bash
./run.sh -m claude-haiku-4-5
```

Use a custom inbox directory:
```bash
./run.sh -i /path/to/my/inbox -o /path/to/my/outbox
```

---

## Running without a container (local dev)

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run the web app directly
ANTHROPIC_API_KEY=sk-ant-... \
INBOX_DIR=./inbox \
OUTBOX_DIR=./outbox \
python web_app.py

# Or run the agent headlessly (no web UI)
python agent_harness.py
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ANTHROPIC_API_KEY is not set` | Export the env var before running `./run.sh` |
| `instruction.md not found` | Upload it via the web UI or place it in `./inbox/` |
| Agent seems stuck | Check the log panel for errors; try `⟳ Reset` then re-run |
| Port 8080 in use | Use `./run.sh -p 9090` |
| Build fails | Ensure Podman can reach `registry.access.redhat.com` |

---

## Next steps

- Read **[README.md](README.md)** for full documentation.
- Work through the **[workshop/](workshop/README.md)** exercises to extend the harness.
