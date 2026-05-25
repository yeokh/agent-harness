#!/usr/bin/env python3
"""
Strands Agent — Amazon Strands SDK file processor.

Reads instruction.md from inbox, processes files per those instructions,
writes output to outbox.  Supports Anthropic, OpenAI, and OpenRouter via
the Strands SDK.  Call run_agent() from a background thread; it blocks
until done, calling log_callback for every log line produced.

Architecture
────────────
  web_app.py  →  run_agent()  →  _build_model()    → Strands model object
                                 _make_tools()      → list of @tool functions
                                 Agent(model, tools) → Strands Agent
                                 agent(prompt)      → agentic loop (auto)
                                 log via embedded logging in tool closures
                                 + callback_handler for model text streaming
                                                   ↓
                                        log_callback (AgentState)
                                                   ↓
                                        Flask SSE → browser terminal

Strands vs Google ADK — key differences
────────────────────────────────────────
  ADK:    LlmAgent + InMemoryRunner.run_async() → Event stream
  Strands: Agent(model, tools) + agent(prompt)  → automatic agentic loop
           Tools use @tool decorator (or strands.tool() applied to closures)
           Streaming via callback_handler(**kwargs)
           No asyncio wiring needed — Strands handles it internally

Workshop exercises that touch this file:
  Exercise 01 — Explore        : read _registry, _make_tools, run_agent
  Exercise 03 — Add Tool       : extend _make_tools() with new @tool functions
  Exercise 05 — Custom Toolsets: organise tools into domain modules
  Exercise 06 — Multi-Agent    : call run_agent() multiple times sequentially
"""

import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable

import httpx

log = logging.getLogger("strands_agent")


# ─── Dynamic Model Registry ──────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# Instead of a hardcoded dict, models are fetched live from each provider's
# API on first use and cached for the session.  This means newly released
# models appear automatically and retired model IDs (like a stale preview
# slug) are never offered to the user.
#
# Each entry in the registry has:
#   id       : unique key used by the UI and passed to _build_model()
#   provider : "anthropic" | "openai" | "openrouter"
#   display  : human-readable label shown in the UI dropdown
#   model_id : exact model string forwarded to the Strands model class
#   env      : environment variable that enables this provider
#
# HOW TO FILTER MODELS (Exercise 01 stretch goal):
#   Edit _fetch_openrouter_models() below to narrow the provider list or
#   add a minimum context_length filter.  No other code changes are needed.

_registry_lock:  threading.Lock   = threading.Lock()
_registry_cache: list[dict] | None = None  # None = not yet fetched


def _fetch_anthropic_models() -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return []
    try:
        r = httpx.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=10,
        )
        r.raise_for_status()
        entries = r.json().get("data", [])
        result = [
            {
                "id":       m["id"],
                "provider": "anthropic",
                "display":  m.get("display_name", m["id"]),
                "model_id": m["id"],
                "env":      "ANTHROPIC_API_KEY",
            }
            for m in entries
        ]
        result.sort(key=lambda x: x["id"])
        return result
    except Exception as exc:
        log.warning("Failed to fetch Anthropic models: %s", exc)
        return []


def _fetch_openai_models() -> list[dict]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return []
    try:
        r = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        r.raise_for_status()
        entries = r.json().get("data", [])
        # Keep only GPT chat models; exclude embeddings, whisper, dall-e, etc.
        gpt = sorted(
            [m for m in entries if m["id"].startswith("gpt-")],
            key=lambda m: m["id"],
        )
        return [
            {
                "id":       m["id"],
                "provider": "openai",
                "display":  m["id"],
                "model_id": m["id"],
                "env":      "OPENAI_API_KEY",
            }
            for m in gpt
        ]
    except Exception as exc:
        log.warning("Failed to fetch OpenAI models: %s", exc)
        return []


def _fetch_openrouter_models() -> list[dict]:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return []
    try:
        r = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        r.raise_for_status()
        entries = r.json().get("data", [])
        # Keep only text-output models (exclude image-gen, embedding, etc.)
        text_models = sorted(
            [
                m for m in entries
                if m.get("architecture", {}).get("modality", "").endswith("->text")
            ],
            key=lambda m: m["id"],
        )
        return [
            {
                "id":       f"openrouter/{m['id']}",
                "provider": "openrouter",
                "display":  f"OR: {m.get('name', m['id'])}",
                "model_id": f"openrouter/{m['id']}",
                "env":      "OPENROUTER_API_KEY",
            }
            for m in text_models
        ]
    except Exception as exc:
        log.warning("Failed to fetch OpenRouter models: %s", exc)
        return []


def _registry() -> list[dict]:
    """Return the model registry, fetching from provider APIs on first call."""
    global _registry_cache
    if _registry_cache is None:
        with _registry_lock:
            if _registry_cache is None:
                log.info("Loading model registry from provider APIs…")
                _registry_cache = (
                    _fetch_anthropic_models()
                    + _fetch_openai_models()
                    + _fetch_openrouter_models()
                )
                log.info("Model registry loaded: %d models", len(_registry_cache))
    return _registry_cache


def _get_model_cfg(model_key: str) -> dict | None:
    return next((m for m in _registry() if m["id"] == model_key), None)


def get_available_models() -> list[dict]:
    """Return all models from configured providers.

    Called by web_app.py on every /api/model GET request so the UI always
    reflects the live provider catalogue without a server restart.
    """
    return [
        {"id": m["id"], "display": m["display"], "provider": m["provider"]}
        for m in _registry()
    ]


def default_model() -> str:
    """Pick the first available model, preferring Anthropic → OpenAI → OpenRouter."""
    for provider in ("anthropic", "openai", "openrouter"):
        for m in _registry():
            if m["provider"] == provider:
                return m["id"]
    reg = _registry()
    return reg[0]["id"] if reg else ""


# ─── Model Factory ────────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# This function converts a model_key string into a Strands model object.
#
# Strands model classes:
#   AnthropicModel  — direct Anthropic API (requires ANTHROPIC_API_KEY)
#   OpenAIModel     — direct OpenAI API (requires OPENAI_API_KEY)
#   LiteLLMModel    — proxy via LiteLLM (used here for OpenRouter)
#
# The model object is passed to Agent(model=...) in run_agent().
# Each class reads its API key from the environment automatically —
# no explicit key passing is needed for Anthropic and OpenAI.
# OpenRouter requires an explicit api_base and api_key because it is
# an OpenAI-compatible proxy, not a first-party SDK target.
#
# WORKSHOP (Exercise 01 stretch goal — filter models):
#   Edit _fetch_openrouter_models() to narrow the provider list or add a
#   minimum context_length filter.  _build_model() handles any entry automatically.

def _build_model(model_key: str):
    """Return the appropriate Strands model instance for *model_key*."""
    cfg = _get_model_cfg(model_key)
    if cfg is None:
        raise ValueError(f"Unknown model: {model_key!r}")

    model_id = cfg["model_id"]
    provider = cfg["provider"]

    if provider == "anthropic":
        # AnthropicModel reads ANTHROPIC_API_KEY from the environment.
        # max_tokens is required for Claude models.
        from strands.models.anthropic import AnthropicModel  # noqa: PLC0415
        return AnthropicModel(
            model_id=model_id,
            max_tokens=8096,
        )

    if provider == "openai":
        # OpenAIModel reads OPENAI_API_KEY from the environment.
        from strands.models.openai import OpenAIModel  # noqa: PLC0415
        return OpenAIModel(
            model_id=model_id,
            client_args={"api_key": os.environ.get("OPENAI_API_KEY", "")},
        )

    if provider == "openrouter":
        # OpenRouter is an OpenAI-compatible proxy.  LiteLLMModel lets us
        # route to it by passing the custom base URL and API key explicitly.
        # Requires: pip install strands-agents[litellm]
        from strands.models.litellm import LiteLLMModel  # noqa: PLC0415
        return LiteLLMModel(
            model_id=model_id,
            params={
                "api_key":  os.environ.get("OPENROUTER_API_KEY", ""),
                "api_base": "https://openrouter.ai/api/v1",
            },
        )

    raise ValueError(f"Unknown provider: {provider!r}")


# ─── Streaming Callback ───────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# The Strands Agent calls this function with **kwargs as it generates output.
# Unlike ADK's Event stream, Strands uses a single callable that receives
# different keyword arguments depending on the event type:
#
#   data=<str>                — a text chunk being streamed from the model
#   current_tool_use=<dict>   — the tool the model is about to invoke
#                               (dict has "name" and "input" keys)
#   complete=True             — the agent run is finished
#
# The callback runs synchronously on the same thread as the agent, so avoid
# any blocking I/O inside it — just append to a buffer or call log_callback.
#
# NOTE: Tool results are logged inside the tool functions themselves (see
# _make_tools below).  The callback only handles model-generated text.

def _make_streaming_callback(log_callback: Callable[[str], None]):
    """Return a Strands callback_handler that routes model text to log_callback.

    Buffers partial lines so that each [assistant] log entry is a complete
    sentence or paragraph, not a raw streaming chunk.
    """
    _buf: list[str] = []

    def handler(**kwargs) -> None:
        # ── Text streaming ────────────────────────────────────────────────────
        # The 'data' key carries raw text chunks as the model generates them.
        # We buffer until we hit a newline, then emit the complete line.
        chunk = kwargs.get("data", "")
        if chunk:
            _buf.append(chunk)
            text = "".join(_buf)
            # Flush all complete lines; keep the trailing partial line buffered.
            if "\n" in text:
                lines = text.split("\n")
                for line in lines[:-1]:
                    stripped = line.strip()
                    if stripped:
                        log_callback(f"[assistant] {stripped}")
                _buf.clear()
                if lines[-1]:
                    _buf.append(lines[-1])

        # ── Tool use event ────────────────────────────────────────────────────
        # 'current_tool_use' fires when the model has decided to call a tool.
        # We do NOT log it here — each tool function already logs its own
        # [tool_use] call at the top of its body (see _make_tools).
        # Logging here would produce duplicate [tool_use] entries.
        # The callback is therefore used ONLY for model text streaming.

    return handler


# ─── Agent Tools ──────────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 03 — Add a Python Tool)
# ───────────────────────────────────────────
# In Amazon Strands, tools are Python functions decorated with @tool (or
# wrapped with strands.tool()).  The framework inspects each function and
# gives the LLM a schema based on:
#   • function name        → tool name (what the LLM calls)
#   • docstring            → tool description (what the LLM reads)
#   • type annotations     → parameter schema (the arguments the LLM supplies)
#   • return type str      → all tools must return str
#
# Unlike ADK, Strands tools can be closures — we apply strands.tool() to the
# inner function *after* defining it.  This lets tools capture inbox/outbox
# paths and log_callback at construction time without global state.
#
# To add a new tool:
#   1. Write a function inside _make_tools() following the pattern below.
#   2. Wrap it with strands_tool() and add it to the return list.
#   3. Restart web_app.py — no other changes needed.
#
# PLACEHOLDER ─ add your custom tools below run_bash(), before the return.
#
# Example tools to try for Exercise 03:
#   • word_count(filepath)          — count lines and words in a file
#   • convert_csv_to_json(filepath) — parse CSV and return JSON string
#   • validate_json(filepath)       — check a JSON file parses correctly
#   • fetch_url(url)                — retrieve a web page (if network allowed)
#
# WORKSHOP (Exercise 05 — Custom Toolsets)
# ─────────────────────────────────────────
# For larger projects, move related tool functions into their own module:
#   tools/csv_tools.py    → CSV-specific helpers
#   tools/report_tools.py → formatting and rendering
# Each module exports a make_*_tools(inbox, outbox, log_callback) factory.
# Import them here and extend the return list.

def _make_tools(
    inbox:        Path,
    outbox:       Path,
    log_callback: Callable[[str], None],
) -> list:
    """Return Strands @tool functions bound to *inbox*, *outbox*, and *log_callback*.

    All tools are defined as closures so they share the resolved absolute
    paths and log_callback without global state.  strands.tool() is applied
    after definition so Strands can introspect the type annotations properly.

    Each tool logs its invocation with [tool_use] and its result with [result]
    so workshop participants can trace exactly what the agent is doing.
    """
    from strands import tool as strands_tool  # noqa: PLC0415

    inbox_r  = inbox.resolve()
    outbox_r = outbox.resolve()
    allowed  = (inbox_r, outbox_r)

    def _in_allowed(path: Path) -> bool:
        """Return True if *path* is inside inbox or outbox."""
        p = path.resolve()
        return any(str(p).startswith(str(a)) for a in allowed)

    # ── Tool: read_file ───────────────────────────────────────────────────────
    def read_file(filepath: str) -> str:
        """Read a file from the inbox or outbox and return its text content.

        Searches both inbox and outbox directories.  Use this to read
        instruction.md, payload files, or results written by a previous step.

        Args:
            filepath: Path to the file.  May be absolute or relative to inbox.

        Returns:
            File contents as a UTF-8 string, or an error message.
        """
        # WORKSHOP NOTE: Every tool logs its call here so the browser
        # terminal shows [tool_use] lines matching the ADK harness format.
        log_callback(f"[tool_use] read_file(filepath={filepath!r})")

        candidates = [
            Path(filepath),          # try as absolute path first
            inbox_r / filepath,      # then relative to inbox
            outbox_r / filepath,     # then relative to outbox
        ]
        for c in candidates:
            resolved = c.resolve()
            if _in_allowed(resolved) and resolved.is_file():
                try:
                    content = resolved.read_text(encoding="utf-8")
                    log_callback(f"[result] read_file: {content[:200]!r}…")
                    return content
                except Exception as exc:
                    result = f"Error reading {filepath}: {exc}"
                    log_callback(f"[result] read_file: {result}")
                    return result
        result = f"File not found: {filepath}"
        log_callback(f"[result] read_file: {result}")
        return result

    # ── Tool: write_file ──────────────────────────────────────────────────────
    def write_file(filepath: str, content: str) -> str:
        """Write text content to a file in the outbox directory.

        Creates any intermediate directories automatically.  Only the outbox
        is writable; attempts to write outside it are rejected.

        Args:
            filepath: Destination path.  May be absolute (must be inside outbox)
                      or a relative path (resolved against the outbox root).
            content:  Full text content to write.

        Returns:
            Confirmation message showing bytes written, or an error.
        """
        log_callback(f"[tool_use] write_file(filepath={filepath!r}, content=<{len(content)} chars>)")

        abs_path = Path(filepath).resolve()
        if str(abs_path).startswith(str(outbox_r)):
            target = abs_path
        else:
            target = (outbox_r / filepath).resolve()
            if not str(target).startswith(str(outbox_r)):
                result = f"Path traversal denied: {filepath}"
                log_callback(f"[result] write_file: {result}")
                return result

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        result = f"Wrote {target.stat().st_size} bytes → {target.relative_to(outbox_r)}"
        log_callback(f"[result] write_file: {result}")
        return result

    # ── Tool: list_files ──────────────────────────────────────────────────────
    def list_files(directory: str = "inbox") -> str:
        """List all files in the inbox or outbox directory.

        Call this first to discover what payload files are available before
        reading them one by one.

        Args:
            directory: "inbox" or "outbox" (or their absolute paths).

        Returns:
            Newline-separated list of relative paths with file sizes.
        """
        log_callback(f"[tool_use] list_files(directory={directory!r})")

        if directory in ("inbox", str(inbox_r)):
            base, label = inbox_r, "inbox"
        elif directory in ("outbox", str(outbox_r)):
            base, label = outbox_r, "outbox"
        else:
            result = f"Unknown directory '{directory}'. Use 'inbox' or 'outbox'."
            log_callback(f"[result] list_files: {result}")
            return result

        if not base.exists():
            result = f"{label} does not exist."
            log_callback(f"[result] list_files: {result}")
            return result

        files = sorted(base.rglob("*"))
        rows  = [
            f"{p.relative_to(base)}  ({p.stat().st_size} bytes)"
            for p in files if p.is_file()
        ]
        result = "\n".join(rows) if rows else f"{label} is empty."
        log_callback(f"[result] list_files: {result[:300]}")
        return result

    # ── Tool: run_bash ────────────────────────────────────────────────────────
    # SECURITY NOTE: run_bash executes arbitrary shell commands on the host.
    # It is intentionally included for power tasks (archive extraction, Python
    # scripts, format conversion) but introduces real risk if an attacker
    # controls instruction.md.  See Exercise 04 (Guardrail) for mitigation.
    def run_bash(command: str) -> str:
        """Execute a bash shell command in the project root directory.

        Use for tasks requiring external tools: extracting archives, running
        Python one-liners, converting file formats, or validating JSON.
        The working directory is set to the parent of inbox/outbox.

        Args:
            command: Shell command string to execute.  Piping, redirection,
                     and multi-command chains (&&, ;) are all supported.

        Returns:
            Combined stdout + stderr output (trimmed), or an error message.
        """
        log_callback(f"[tool_use] run_bash(command={command!r})")

        # Block a small set of obviously destructive patterns.
        # This is NOT a complete sandbox — combine with OS-level restrictions
        # and the Exercise 04 guardrail for production deployments.
        blocked = ["rm -rf /", "dd if=", "mkfs", ":(){ :|:& };:"]
        for b in blocked:
            if b in command:
                result = f"Command blocked (contains '{b}')"
                log_callback(f"[result] run_bash: {result}")
                return result
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(inbox_r.parent),   # project root (parent of inbox/)
            )
            output = (proc.stdout + proc.stderr).strip()
            result = output or f"Exit code {proc.returncode}"
            log_callback(f"[result] run_bash: {result[:300]}")
            return result
        except subprocess.TimeoutExpired:
            result = "Command timed out (60 s)"
            log_callback(f"[result] run_bash: {result}")
            return result
        except Exception as exc:
            result = f"Error: {exc}"
            log_callback(f"[result] run_bash: {result}")
            return result

    # ── WORKSHOP PLACEHOLDER (Exercise 03) ────────────────────────────────────
    # Add your new tool functions here.
    #
    # Pattern (same as the tools above):
    #
    # def my_tool(arg1: str, arg2: int = 0) -> str:
    #     """One-line description the LLM reads when deciding whether to call this.
    #
    #     Longer explanation of behaviour and edge cases.
    #
    #     Args:
    #         arg1: Description of first argument.
    #         arg2: Description of second argument (optional).
    #
    #     Returns:
    #         String result that the LLM reads as the tool response.
    #     """
    #     log_callback(f"[tool_use] my_tool(arg1={arg1!r}, arg2={arg2!r})")
    #     ...
    #     result = "result string"
    #     log_callback(f"[result] my_tool: {result}")
    #     return result
    # ─────────────────────────────────────────────────────────────────────────

    # Apply the Strands @tool decorator to each closure.
    # strands_tool() inspects the function's __doc__ and __annotations__ to
    # build the JSON schema the LLM sees — so keep docstrings and type hints.
    base_tools = [read_file, write_file, list_files, run_bash]

    # Exercise 03: append your new tool functions to base_tools before this line.
    # Example: base_tools.append(my_tool)

    return [strands_tool(fn) for fn in base_tools]


# ─── System Prompt ────────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# The system prompt is the agent's standing instructions — injected into every
# LLM call automatically by the Strands Agent.
#
# The task-specific instructions live in inbox/instruction.md and are read
# by the agent at runtime using the read_file tool.  Keeping them separate
# means you can change the task without touching this code or restarting.
#
# WORKSHOP (Exercise 03 — Add Tool)
# ──────────────────────────────────
# If you add a new tool that requires special usage guidance (e.g. "always
# validate JSON after writing it"), add a bullet point here so the agent
# applies it even when instruction.md does not mention it.

_SYSTEM_PROMPT = """\
You are a file-processing agent powered by Amazon Strands. Follow these steps:

1. Call list_files("inbox") to discover what payload files are available.
2. Call read_file on "instruction.md" to understand your task.
3. Process each relevant payload file according to those instructions.
4. Write all output files to the outbox directory using write_file.
5. Write a concise processing summary to outbox/agent.log.

Guidelines:
- Only read from inbox; only write to outbox.
- If the inbox contains a .tar or .zip archive, extract it with run_bash
  before processing its contents.
- When a task requires computation (sorting, aggregating, parsing CSV), prefer
  run_bash with a Python one-liner over doing it in your reasoning.
- Do not invent data; base all output strictly on the input files.
- Confirm each write_file call succeeded before moving to the next file.
"""


# ─── Public Synchronous API ───────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# run_agent() is the single entry point called by web_app.py.  It is
# synchronous so it can be called from a plain threading.Thread (Flask's
# background thread model) without any asyncio wiring in web_app.py.
#
# Strands Agent internals:
#   Agent(model, tools, system_prompt) — the "brain": holds the system prompt,
#                                         model, and tools; drives the agentic loop.
#   agent(prompt)                      — starts the loop: LLM call → tool call
#                                         → result → LLM call … → final answer.
#                                         Returns the final response string.
#
# Contrast with ADK:
#   ADK needed InMemoryRunner + Session + asyncio.run() + Event stream.
#   Strands collapses all that into a single synchronous agent() call.
#
# WORKSHOP (Exercise 06 — Multi-Agent Pipeline)
# ──────────────────────────────────────────────
# To chain multiple passes, call run_agent() more than once with different
# model_key / inbox / outbox combinations:
#
#   run_agent("claude-haiku-4-5", inbox, stage1_out, log)   # fast extract
#   run_agent(state.model, stage1_out, outbox, log)         # capable report
#
# See workshop/advanced/06_multi_agent.md for the full worked example.

def run_agent(
    model_key:    str,
    inbox:        Path,
    outbox:       Path,
    log_callback: Callable[[str], None],
) -> None:
    """Run the Strands agent synchronously (blocks until complete).

    Intended to be called from a background daemon thread started by
    web_app.py.  Raises on fatal errors; the caller is responsible for
    catching and recording them.

    Args:
        model_key:    Model ID from the registry (e.g. "claude-sonnet-4-6").
        inbox:        Absolute path to the inbox directory.
        outbox:       Absolute path to the outbox directory.
        log_callback: Called with each log line as it is produced.
    """
    # Import Agent here so that missing strands-agents install fails clearly
    # at run time, not at module import time.
    from strands import Agent  # noqa: PLC0415

    log_callback(f"model={model_key}  inbox={inbox}  outbox={outbox}")

    model  = _build_model(model_key)
    tools  = _make_tools(inbox, outbox, log_callback)
    cb     = _make_streaming_callback(log_callback)

    # Create the Strands Agent.  The agent manages the entire agentic loop:
    # it sends the prompt to the LLM, intercepts tool calls, executes them
    # using our tool list, and feeds results back until the LLM is done.
    agent = Agent(
        model=model,
        tools=tools,
        system_prompt=_SYSTEM_PROMPT,
        callback_handler=cb,
    )

    # The user prompt tells the agent where to find the task and its files.
    # instruction.md provides the actual task — keeping it separate means
    # the task can change without code changes or server restarts.
    prompt = (
        f"Read {inbox}/instruction.md for your task, then execute it fully. "
        f"Input files are in {inbox}/. "
        f"Write all outputs (including agent.log summary) to {outbox}/. "
        f"Do not access paths outside {inbox}/ and {outbox}/."
    )

    # agent(prompt) drives the agentic loop to completion and returns the
    # final response string.  All intermediate events (tool calls, results,
    # model text) have already been routed to log_callback by this point.
    response = agent(prompt)

    # Log the final assistant response if it contains meaningful content.
    final_text = str(response).strip()
    if final_text:
        for line in final_text.split("\n"):
            if line.strip():
                log_callback(f"[assistant] {line}")
