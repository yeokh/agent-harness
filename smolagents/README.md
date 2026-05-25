# Smolagents Workshop Agent

A web-based file-processing AI agent powered by [HuggingFace Smolagents](https://github.com/huggingface/smolagents).  Reads `instruction.md` and payload files from the **inbox** folder, processes them using a `ToolCallingAgent`, and writes output to the **outbox** folder.

## Quick-start

```bash
pip install -e .
cp .env.example .env
# edit .env and set at least one API key
source .env
python web_app.py
```

Open **http://localhost:8080**.

## Project layout

```
smolagents/
├── smolagent_agent.py  ← agent logic (models, tools, runner)
├── web_app.py          ← Flask web UI (HTTP endpoints, SSE streaming)
├── templates/
│   └── index.html      ← single-page web UI
├── inbox/              ← drop instruction.md and payload files here
│   ├── instruction.md  ← task definition (read by agent at runtime)
│   ├── file1.txt
│   └── ...
├── outbox/             ← agent writes all output here
├── workshop/           ← step-by-step workshop exercises
│   ├── README.md
│   ├── beginner/
│   └── advanced/
├── pyproject.toml
└── .env.example
```

## API keys

Set at least one:

| Variable | Provider |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude models |
| `OPENAI_API_KEY` | GPT models |
| `OPENROUTER_API_KEY` | 200+ models via OpenRouter |

Models appear automatically in the UI based on which keys are present.

## Architecture

```
Browser  ──GET/POST──▶  web_app.py (Flask)
                              │
                        threading.Thread
                              │
                    smolagent_agent.run_agent()
                              │
                    ToolCallingAgent.run(task)
                              │
                    step_callbacks=[…]  ──▶  SSE  ──▶  Browser terminal
                              │
                    LiteLLMModel  ──▶  Anthropic / OpenAI / OpenRouter
```

## Workshop

See [workshop/README.md](workshop/README.md) for the full exercise guide.

Six exercises from beginner to advanced:
- **01 Explore** — run the agent, trace step callbacks
- **02 Modify Instructions** — change `instruction.md`, observe output changes
- **03 Add a Tool** — extend the agent with a new `@tool`-decorated function
- **04 Guardrail** — add pre-flight safety validation
- **05 Custom Toolsets** — organise tools into domain modules
- **06 Multi-Agent Pipeline** — chain stages; explore `ManagedAgent`
