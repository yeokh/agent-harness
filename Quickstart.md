# Quickstart — Claude Agent Harness

Get from zero to a running agent in 5 minutes.  All the agents are developed using Python and follow the same general structure and format.
You can use the same steps below to test any of the agent, using the sample jobs provided.

---

## Install Python package/project manager - you can use pip and venv modules or uv

curl -LsSf https://astral.sh/uv/install.sh | sh

Access to LLM services:
- **Anthropic API key** from [console.anthropic.com](https://console.anthropic.com/)
- **OpenRouter API key** from [https://openrouter.ai/] 

Option for running containerized agents:
- Install **Podman** 4.x+ ([podman.io](https://podman.io/)) to run containerized AI agents.


---

## Set your API key

export ANTHROPIC_API_KEY=sk-ant-api03-...
export OPENROUTER_API_KEY=sk-or-v1-...


---

## Clone and initialize the agent project

git clone https://github.com/yeokh/agent-harness 
cd agent-harness 
cd my-agent

Create or modify `inbox/instruction.md` (a sample already exists in this repo):
The instruction file tells the agent what to do. It is loaded as the agent's task prompt before each run.


---

## (Optional) Add payload files

Drop any files the agent should process into the `inbox/` folder: 
The agent can list and read these files using its built-in tools.


---

## Initialize and run the agent

uv init 
uv sync 
source .venv/bin/activate 

python web_app.py


---

## Open the web UI

Visit **http://localhost:8080** in your browser.

You will see:
- **Inbox** panel (left) — lists files in `inbox`
- **Outbox** panel (left) — lists files written by the agent in 'outbox'
- **File viewer** (right) — click any file to see its contents
- **Run Agent** button — starts the agent
- **Log panel** (bottom) — streams the agent's activity in real-time

---

## Run the agent

1. Click **▶ Run Agent**.
2. Watch the log panel as the agent reads your instruction file and payload files.
3. When complete, new files appear in the **Outbox** panel.
4. Click any outbox file to view the results.

---

## Next steps

- Read **[README.md](README.md)** for full documentation.
- Work through the **[workshop/](workshop/README.md)** exercises to extend the harness.
