# Agent Harness — Multi-Framework AI Agent Platform

A comprehensive repository showcasing **multiple AI agent implementations** using different frameworks and LLM providers. Each agent is a web-based file-processing system that reads instructions and payload files from an **inbox**, executes tasks using AI models, and writes results to an **outbox**.

## 🎯 Purpose

This repository serves as a **reference implementation** and **testing ground** for building scalable AI agents that:
- Accept task instructions via markdown files
- Process input files (CSV, JSON, YAML, text, etc.)
- Execute tasks using multiple LLM providers
- Stream results back to users via a web UI
- Support easy extension with custom tools and skills

Perfect for:
- Learning how to build AI agents
- Comparing different agent frameworks
- Prototyping LLM-powered file processors
- Building production agent pipelines

---

## 📦 What's Included

### **Agent Implementations**

| Agent | Framework | LLM Providers | Status |
|-------|-----------|---------------|--------|
| [**claude-agent**](claude-agent/) | Claude Agent SDK | Anthropic, OpenRouter | ✓ Primary |
| [**adk-agent**](adk-agent/) | Google ADK (LiteLLM) | Anthropic, OpenAI, OpenRouter | ✓ Active |
| [**langchain-agent**](langchain-agent/) | LangChain | Anthropic, OpenAI | ✓ Reference |
| [**pi-cli-agent**](pi-cli-agent/) | Pi CLI | Anthropic | ✓ Reference |
| [**strands-agent**](strands-agent/) | Strands | Anthropic | ✓ Reference |
| [**smolagents**](smolagents/) | Hugging Face Agents | Anthropic, OpenAI | ✓ Reference |
| [**deep-agent**](deep-agent/) | LangChain Deep Agents | Anthropic, OpenRouter | ✓ Reference |

### **Example Jobs**

The [**example-jobs/**](example-jobs/) folder contains real-world agent tasks:

```
example-jobs/
├── job1-code-scan/          # Security scanning (YAML playbooks)
├── job-ascii-jpeg-art/      # Image to ASCII art conversion
├── job-redhat-cve-explainer/ # CVE analysis with Red Hat data
└── job4-titanic-csv/        # Data analysis (Titanic dataset)
```

Each job follows the standard pattern:
```
job-name/
├── agent/instruction.md     # Task definition for the agent
├── inbox/                   # Input files to process
└── outbox/                  # Agent output and results
```

### **Workshop Materials**

Each agent includes workshop exercises:
- **Beginner:** Explore, modify instructions, add tools
- **Advanced:** Custom toolsets, guardrails, multi-agent workflows
- **Demos:** Real-world scenarios (multi-step workflows, brain swapping, etc.)

---

## 🚀 Quick Start

### **Option 1: Claude Agent (Recommended)**

```bash
cd claude-agent

# Setup
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure
export ANTHROPIC_API_KEY=sk-ant-...

# Run
python web_app.py
```

Open **http://localhost:8080** in your browser.

### **Option 2: ADK Agent**

```bash
cd adk-agent

# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Configure
cp .env.example .env
# Edit .env and uncomment your API key(s)

# Run
adk-agent-web
```

### **Option 3: Docker/Podman (Claude Agent)**

```bash
cd claude-agent
chmod +x run.sh
export ANTHROPIC_API_KEY=sk-ant-...
./run.sh
```

---

## 📋 Standard Workflow

All agents follow this pattern:

1. **Write an instruction file** → `inbox/instruction.md`
   ```markdown
   # Task Description
   
   Read all CSV files in the inbox.
   For each file, count the rows and summarize the columns.
   Write results to `outbox/summary.md`.
   ```

2. **Add payload files** → `inbox/*.csv`, `inbox/*.json`, etc.

3. **Run the agent** → Click "Run Agent" in the web UI

4. **View results** → Check `outbox/` for agent output

---

## 🏗️ Architecture

Each agent follows this layered design:

```
Browser UI (index.html)
    ↓ HTTP + SSE
Web App (web_app.py)  ← File management, model selection, lifecycle
    ↓ import
Agent Logic (agent_harness.py)  ← LLM calls, tool definitions
    ↓ SDK/Framework
LLM Provider  ← Anthropic | OpenAI | OpenRouter
```

**Key separation of concerns:**
- **Web layer:** HTTP endpoints, file I/O, SSE streaming (no LLM calls)
- **Agent layer:** Model construction, tool definitions, task execution
- **Tools:** Built-in file operations, bash execution, custom skills

---

## 🛠️ Supported LLM Providers

| Provider | API Key | Example Models |
|----------|---------|----------------|
| **Anthropic** | `ANTHROPIC_API_KEY` | claude-opus-4-5, claude-sonnet-4-6, claude-haiku-4-5 |
| **OpenAI** | `OPENAI_API_KEY` | gpt-4o, gpt-4o-mini, gpt-4-turbo |
| **OpenRouter** | `OPENROUTER_API_KEY` | 200+ models (Claude, GPT, Gemini, LLaMA, etc.) |

Set at least one key via environment variables or `.env` files.

---

## 📁 Repository Structure

```
agent-harness/
├── README.md                    # This file
├── Quickstart.md               # Getting started guide
│
├── claude-agent/               # Claude Agent SDK implementation
│   ├── web_app.py
│   ├── agent_harness.py
│   ├── workshop/               # Learning exercises
│   └── README.md
│
├── adk-agent/                  # Google ADK + LiteLLM implementation
│   ├── web_app.py
│   ├── adk_agent.py
│   ├── workshop/
│   └── README.md
│
├── [other-agents]/             # LangChain, Pi CLI, Strands, etc.
│
├── example-jobs/               # Real-world agent tasks
│   ├── job1-code-scan/
│   ├── job-ascii-jpeg-art/
│   ├── job-redhat-cve-explainer/
│   └── job4-titanic-csv/
│
└── .gitignore                  # Excludes: .venv, .claude, node_modules
```

---

## 🎓 Learning Path

### **Beginners**
1. Read [Quickstart.md](Quickstart.md)
2. Start with [claude-agent/](claude-agent/) or [adk-agent/](adk-agent/)
3. Follow the **Beginner Workshop** exercises
4. Try an [example-job/](example-jobs/)

### **Intermediate**
1. Read agent-specific README files
2. Complete **Advanced Workshop** exercises
3. Examine the agent's tool definitions
4. Extend with custom tools

### **Advanced**
1. Build multi-agent workflows
2. Implement guardrails and validation
3. Integrate with external APIs
4. Deploy to production

---

## 🔧 Extending an Agent

### **Change the task**
Edit `inbox/instruction.md` — no code changes needed.

### **Add a custom tool**
Edit `agent_harness.py` and add a function with type hints:
```python
@tool
def my_tool(param1: str, param2: int) -> str:
    """Tool description for the LLM."""
    return "result"
```

### **Switch providers**
Set environment variables:
```bash
export ANTHROPIC_API_KEY=sk-ant-...    # Use Claude
export OPENAI_API_KEY=sk-...           # Use GPT-4
export OPENROUTER_API_KEY=sk-or-...   # Use OpenRouter
```

### **Change the model**
Update `CLAUDE_MODEL` or model selection in the agent:
```bash
CLAUDE_MODEL=claude-opus-4-5 python web_app.py
```

---

## 📊 Example Outputs

### Code Security Scanner
- **Input:** YAML playbooks
- **Output:** Vulnerability report with recommendations

### Image to ASCII Art
- **Input:** JPEG image file
- **Output:** ASCII art HTML visualization

### CVE Analysis
- **Input:** Server names
- **Output:** Security advisories with mitigation steps

### Data Analysis
- **Input:** CSV dataset
- **Output:** Summary statistics and insights

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| `API key not found` | Set `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc. as environment variables |
| `instruction.md not found` | Create it in the agent's `inbox/` folder |
| `Port 8080 in use` | Use `PORT=9090 python web_app.py` |
| Agent seems stuck | Check logs in the web UI; click "Reset" and try again |
| Module import errors | Run `pip install -r requirements.txt` or `pip install -e .` |

---

## 📚 Documentation

- **[Quickstart.md](Quickstart.md)** — 5-minute setup guide
- **[claude-agent/README.md](claude-agent/README.md)** — Claude Agent SDK details
- **[adk-agent/README.md](adk-agent/README.md)** — Google ADK + LiteLLM details
- **[example-jobs/READ.me](example-jobs/READ.me)** — Job structure and examples
- **Workshop READMEs** — Hands-on exercises in each agent's `/workshop` folder

---

## 🤝 Contributing

This is a reference implementation and learning resource. Feel free to:
- Fork and extend
- Create new agent implementations
- Add example jobs
- Share improvements

---

## 📝 License

This project is provided as-is for educational and reference purposes.

---

## 🎯 Next Steps

1. **Choose an agent** → Start with [claude-agent](claude-agent/) or [adk-agent](adk-agent/)
2. **Follow the quickstart** → [Quickstart.md](Quickstart.md)
3. **Try an example** → Run a job from [example-jobs/](example-jobs/)
4. **Build your own** → Create a custom task in `inbox/instruction.md`

**Questions?** Check the individual agent READMEs or workshop materials for detailed explanations.

---

**Happy agent building! 🚀**
