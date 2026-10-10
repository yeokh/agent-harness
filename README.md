# Agent Harness

This repository contains several agent harness implementations using different frameworks and LLM providers. 
The base architecture for the harness is to have access to 3 folders:
- agent folder: read only folders that contain agent instructions and skills .md files.
- input folder: read only job payload files and artifacts.
- output folder: read/write job output files and artifacts.

Implemented agent harness includes interactive web-based agents as well as batch job agents that ends once a job is completed. 

The agent will initialize from the agent folder, process the files from the input folder and then write/copy everything related to the job into the output folder.


# Purpose

This repository serves as a reference implementation and testing ground for building scalable AI agents that:
- Accept task instructions via markdown files
- Process input files (CSV, JSON, YAML, text, etc.)
- Execute tasks using multiple LLM providers
- Stream results back to users via a web UI or write to the output folder.
- Support easy extension with custom tools and skills

Perfect for:
- Learning how to build AI agents
- Comparing different agent frameworks
- Prototyping LLM-powered file processors
- Building production agent pipelines


Example of agent job structure:
job-name/
├── agent/instruction.md     # Task definition for the agent
├── inbox/                   # Input files to process
└── outbox/                  # Agent output and results


## Basic Architecture

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



