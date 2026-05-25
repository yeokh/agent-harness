#!/usr/bin/env python3
"""
ADK Agent — Google Agent Development Kit file processor.

Reads instruction.md from inbox, processes files per those instructions,
writes output to outbox.  Supports Anthropic, OpenAI, and OpenRouter via
LiteLLM.  Call run_agent() from a background thread; it blocks until done,
calling log_callback for every log line produced.

Architecture
────────────
  web_app.py  →  run_agent()  →  _run_async()  →  ADK LlmAgent
                                                     ↓
                                              InMemoryRunner.run_async()
                                                     ↓
                                         streams Event objects
                                                     ↓
                                          _format_event() → log lines
                                                     ↓
                                          log_callback (AgentState)
                                                     ↓
                                          Flask SSE → browser terminal

Workshop exercises that touch this file:
  Exercise 01 — Explore        : read MODELS, _make_tools, _run_async
  Exercise 03 — Add Tool       : extend _make_tools() with new functions
  Exercise 05 — Custom Toolsets: organise tools into domain modules
  Exercise 06 — Multi-Agent    : run multiple agents sequentially / in parallel
"""

import asyncio
import json as _json
import logging
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

log = logging.getLogger("adk_agent")


# ─── Model Registry ──────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# Models are fetched live from the Anthropic and OpenRouter APIs so the UI
# always shows what is actually available.  OpenAI models are hardcoded because
# the endpoint list is stable.  Results are cached for 5 minutes.
#
# Each registry entry has:
#   provider   : "anthropic" | "openai" | "openrouter"
#   display    : human-readable label shown in the UI dropdown
#   litellm_id : exact string forwarded to LiteLlm()
#   env        : env-var that must be set for this provider
#
# HOW TO ADD A STATIC MODEL (Exercise 01 stretch goal):
#   Add an entry to _OPENAI_MODELS below.  For Anthropic / OpenRouter models
#   the API fetch will pick them up automatically.

_OPENAI_MODELS: dict[str, dict] = {
    "gpt-4o": {
        "provider":   "openai",
        "display":    "GPT-4o (most capable)",
        "litellm_id": "openai/gpt-4o",
        "env":        "OPENAI_API_KEY",
    },
    "gpt-4o-mini": {
        "provider":   "openai",
        "display":    "GPT-4o Mini (fast)",
        "litellm_id": "openai/gpt-4o-mini",
        "env":        "OPENAI_API_KEY",
    },
}

# ── Registry cache (populated lazily, refreshed every _CACHE_TTL seconds) ────
_registry: dict[str, dict] = {}
_registry_ts: float = 0.0
_registry_lock = threading.Lock()
_CACHE_TTL: float = 300.0


def _fetch_anthropic_models() -> list[dict]:
    """Return tool-capable models from the Anthropic /v1/models endpoint."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return []
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/models",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = _json.loads(resp.read())
    result = []
    for m in data.get("data", []):
        model_id = m["id"]
        result.append({
            "provider":   "anthropic",
            "display":    m.get("display_name", model_id),
            "litellm_id": model_id,
            "env":        "ANTHROPIC_API_KEY",
        })
    return result


def _fetch_openrouter_models() -> list[dict]:
    """Return tool-capable models from the OpenRouter /v1/models endpoint."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return []
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = _json.loads(resp.read())
    result = []
    for m in data.get("data", []):
        if "tools" not in (m.get("supported_parameters") or []):
            continue
        raw_id = m["id"]
        or_id  = f"openrouter/{raw_id}"
        result.append({
            "provider":   "openrouter",
            "display":    f"OR: {m.get('name', raw_id)}",
            "litellm_id": or_id,
            "env":        "OPENROUTER_API_KEY",
        })
    return result


def _get_registry() -> dict[str, dict]:
    """Return the model registry, refreshing from APIs when the cache is stale."""
    global _registry, _registry_ts
    with _registry_lock:
        if time.monotonic() - _registry_ts < _CACHE_TTL and _registry:
            return _registry

        registry: dict[str, dict] = {}

        # OpenAI — stable list, no need to call their API
        if os.environ.get("OPENAI_API_KEY"):
            registry.update(_OPENAI_MODELS)

        # Anthropic — fetch live
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                for m in _fetch_anthropic_models():
                    registry[m["litellm_id"]] = m
            except Exception as exc:
                log.warning("Failed to fetch Anthropic models: %s", exc)

        # OpenRouter — fetch live
        if os.environ.get("OPENROUTER_API_KEY"):
            try:
                for m in _fetch_openrouter_models():
                    registry[m["litellm_id"]] = m
            except Exception as exc:
                log.warning("Failed to fetch OpenRouter models: %s", exc)

        _registry = registry
        _registry_ts = time.monotonic()
        return _registry


def get_available_models() -> list[dict]:
    """Return all models whose provider API key is present in the environment.

    Called by web_app.py on every /api/model GET request so the UI always
    reflects the current environment without a restart.
    """
    reg = _get_registry()
    return [
        {"id": mid, "display": cfg["display"], "provider": cfg["provider"]}
        for mid, cfg in reg.items()
    ]


def default_model() -> str:
    """Pick the first available model, preferring Anthropic → OpenAI → OpenRouter."""
    reg = _get_registry()
    for provider in ("anthropic", "openai", "openrouter"):
        for mid, cfg in reg.items():
            if cfg["provider"] == provider:
                return mid
    return next(iter(reg), "")  # last-resort fallback


# ─── Model Factory ────────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# This function converts a model_id string into an ADK LiteLlm object.
# LiteLlm is ADK's bridge to any LLM provider through the LiteLLM library.
#
# Routing logic:
#   openrouter/* → LiteLlm with explicit api_base + api_key (OpenRouter needs both)
#   anthropic/*  → LiteLlm reads ANTHROPIC_API_KEY from environment automatically
#   openai/*     → LiteLlm reads OPENAI_API_KEY from environment automatically
#
# The returned object is passed directly to LlmAgent(model=...).

def _build_model(model_id: str):
    """Return the appropriate ADK LiteLlm instance for *model_id*."""
    reg = _get_registry()
    if model_id not in reg:
        raise ValueError(f"Unknown model: {model_id!r}")

    cfg      = reg[model_id]
    litellm  = cfg["litellm_id"]
    provider = cfg["provider"]

    from google.adk.models.lite_llm import LiteLlm  # noqa: PLC0415

    if provider == "openrouter":
        # OpenRouter requires the API base URL and key to be explicit.
        return LiteLlm(
            model=litellm,
            api_base="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        )

    # For Anthropic and OpenAI, LiteLLM auto-reads the key from the environment.
    return LiteLlm(model=litellm)


# ─── Agent Tools ──────────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 03 — Add a Python Tool)
# ───────────────────────────────────────────
# In Google ADK, tools are ordinary Python functions.  The ADK framework
# inspects each function and gives the LLM a schema based on:
#   • function name   → tool name (what the LLM calls)
#   • docstring       → tool description (what the LLM reads to decide when to use it)
#   • type annotations→ parameter schema (the arguments the LLM must supply)
#   • return type     → must be str (the result returned to the LLM)
#
# To add a new tool:
#   1. Write a function inside _make_tools() following the pattern below.
#   2. Add it to the `return [...]` list at the bottom of _make_tools().
#   3. Restart web_app.py — no other changes needed.
#
# PLACEHOLDER ─ add your custom tools below run_bash(), before the return.
#
# Example tools to try for Exercise 03:
#   • word_count(filepath)            — count lines and words in a file
#   • convert_csv_to_json(filepath)   — parse CSV and return JSON string
#   • validate_json(filepath)         — check a JSON file parses correctly
#   • image_to_base64(filepath)       — encode a binary file for embedding
#
# WORKSHOP (Exercise 05 — Custom Toolsets)
# ─────────────────────────────────────────
# For larger projects, move related tool functions into their own module, e.g.:
#   tools/csv_tools.py    → CSV-specific helpers
#   tools/report_tools.py → formatting and rendering
# Then import and include them here:
#   from tools.csv_tools import parse_csv, pivot_table
#   return [..., parse_csv, pivot_table]

def _make_tools(inbox: Path, outbox: Path) -> list:
    """Return tool functions bound to *inbox* and *outbox* paths.

    All tools are defined as closures that capture the resolved absolute paths
    at construction time.  This keeps tools stateless and easy to test.
    """
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
        candidates = [
            Path(filepath),          # try as absolute path first
            inbox_r / filepath,      # then relative to inbox
            outbox_r / filepath,     # then relative to outbox
        ]
        for c in candidates:
            resolved = c.resolve()
            if _in_allowed(resolved) and resolved.is_file():
                try:
                    return resolved.read_text(encoding="utf-8")
                except Exception as exc:
                    return f"Error reading {filepath}: {exc}"
        return f"File not found: {filepath}"

    # ── Tool: write_file ──────────────────────────────────────────────────────
    def write_file(filepath: str, content: str) -> str:
        """Write text content to a file in the outbox directory.

        Creates any intermediate directories automatically.  Only the outbox
        is writable; attempts to write outside it are rejected.

        Args:
            filepath: Destination path.  May be absolute (must be inside outbox)
                      or a relative path (resolved against outbox root).
            content:  Full text content to write.

        Returns:
            Confirmation message showing bytes written, or an error.
        """
        abs_path = Path(filepath).resolve()
        if str(abs_path).startswith(str(outbox_r)):
            target = abs_path
        else:
            target = (outbox_r / filepath).resolve()
            if not str(target).startswith(str(outbox_r)):
                return f"Path traversal denied: {filepath}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {target.stat().st_size} bytes → {target.relative_to(outbox_r)}"

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
        if directory in ("inbox", str(inbox_r)):
            base, label = inbox_r, "inbox"
        elif directory in ("outbox", str(outbox_r)):
            base, label = outbox_r, "outbox"
        else:
            return f"Unknown directory '{directory}'. Use 'inbox' or 'outbox'."
        if not base.exists():
            return f"{label} does not exist."
        files = sorted(base.rglob("*"))
        rows  = [
            f"{p.relative_to(base)}  ({p.stat().st_size} bytes)"
            for p in files if p.is_file()
        ]
        return "\n".join(rows) if rows else f"{label} is empty."

    # ── Tool: run_bash ────────────────────────────────────────────────────────
    # SECURITY NOTE: run_bash executes arbitrary shell commands on the host.
    # It is intentionally included for power tasks (archive extraction, Python
    # scripts, format conversion) but introduces real risk if an attacker
    # controls instruction.md.  See Exercise 04 (Guardrail) for mitigation.
    def run_bash(command: str) -> str:
        """Execute a bash shell command in the project root directory.

        Use this for tasks that require external tools: extracting archives,
        running Python one-liners, converting file formats, or validating JSON.
        The working directory is set to the parent of inbox/outbox.

        Args:
            command: Shell command string to execute.  Piping, redirection,
                     and multi-command chains (&&, ;) are all supported.

        Returns:
            Combined stdout + stderr output (trimmed), or an error message.
        """
        # Block a small set of obviously destructive patterns.
        # This is NOT a complete sandbox — combine with OS-level restrictions
        # and the Exercise 04 guardrail for production deployments.
        blocked = ["rm -rf /", "dd if=", "mkfs", ":(){ :|:& };:"]
        for b in blocked:
            if b in command:
                return f"Command blocked (contains '{b}')"
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(inbox_r.parent),   # project root (parent of inbox/)
            )
            output = (result.stdout + result.stderr).strip()
            return output or f"Exit code {result.returncode}"
        except subprocess.TimeoutExpired:
            return "Command timed out (60 s)"
        except Exception as exc:
            return f"Error: {exc}"

    # ── WORKSHOP PLACEHOLDER (Exercise 03) ────────────────────────────────────
    # Add your new tool functions here, then include them in the list below.
    #
    # Template:
    #
    # def my_tool(arg1: str, arg2: int = 0) -> str:
    #     """One-line description the LLM sees when deciding whether to call this.
    #
    #     Longer explanation of behaviour and edge cases (not shown to the LLM
    #     but useful for code review).
    #
    #     Args:
    #         arg1: Description of first argument.
    #         arg2: Description of second argument (optional, defaults to 0).
    #
    #     Returns:
    #         String result that the LLM reads as the tool response.
    #     """
    #     ...
    #     return "result string"
    # ─────────────────────────────────────────────────────────────────────────

    return [read_file, write_file, list_files, run_bash]
    # Exercise 03: append your new tools to this list, e.g.:
    # return [read_file, write_file, list_files, run_bash, my_tool]


# ─── System Prompt ────────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# The system prompt is the agent's standing instructions — it is injected into
# every LLM call automatically by the ADK LlmAgent.
#
# The task-specific instructions live in inbox/instruction.md and are read by
# the agent at runtime using the read_file tool.  Keeping them separate means
# you can change the task without touching this code or restarting the server.
#
# WORKSHOP (Exercise 03 — Add Tool)
# ──────────────────────────────────
# If you add a new tool that requires special usage guidance (e.g. "always
# validate JSON after writing it"), add a bullet point here so the agent knows
# to apply it even when instruction.md does not mention it.

_SYSTEM_PROMPT = """\
You are a file-processing agent powered by Google ADK. Follow these steps:

1. Call list_files("inbox") to discover what payload files are available.
2. Call read_file on instruction.md to understand your task.
3. Process each relevant payload file according to those instructions.
4. Write all output files to the outbox directory using write_file.
5. Write a concise processing summary to outbox/agent.log.

Guidelines:
- Only read from inbox; only write to outbox.
- If the inbox contains a .tar or .zip archive, extract it with run_bash before
  processing its contents.
- When a task requires computation (sorting, aggregating, parsing CSV), prefer
  run_bash with a Python one-liner over doing it in your reasoning.
- Do not invent data; base all output strictly on the input files.
- Confirm each write_file call succeeded before moving to the next file.
"""


# ─── ADK Event Formatter ──────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# The ADK runner emits Event objects as the agent works.  Each Event has:
#   event.author  : who produced it ("user", "model", or the agent name)
#   event.content : a Content object containing a list of Part objects
#
# A Part can be one of three things:
#   part.text              → plain text the model is saying (shown as [assistant])
#   part.function_call     → a tool the model wants to invoke  (shown as [tool_use])
#   part.function_response → the result returned by that tool  (shown as [result])
#
# This function converts those structured objects into the flat log-line strings
# that AgentState stores and the browser terminal displays.
# The CSS in index.html colours each prefix differently:
#   [tool_use]  → green    [result] → grey    [assistant] → white

def _format_event(event) -> list[str]:
    """Convert a single ADK Event into zero or more log lines."""
    lines: list[str] = []
    try:
        content = getattr(event, "content", None)
        if content is None:
            return lines
        author = getattr(event, "author", "model")
        parts  = getattr(content, "parts", None) or []

        for part in parts:
            # ── Plain text from the model ────────────────────────────────────
            text = getattr(part, "text", None)
            if text and text.strip():
                prefix = "[assistant]" if author != "user" else "[user]"
                for line in text.strip().split("\n"):
                    if line.strip():
                        lines.append(f"{prefix} {line}")

            # ── Tool call: the model asking to invoke a tool ─────────────────
            fc = getattr(part, "function_call", None)
            if fc:
                name     = getattr(fc, "name", "?")
                raw_args = getattr(fc, "args", {}) or {}
                args_str = ", ".join(
                    f"{k}={repr(str(v))[:60]}" for k, v in dict(raw_args).items()
                )
                lines.append(f"[tool_use] {name}({args_str})")

            # ── Tool response: the result sent back to the model ─────────────
            fr = getattr(part, "function_response", None)
            if fr:
                name = getattr(fr, "name", "?")
                resp = getattr(fr, "response", {})
                if isinstance(resp, dict):
                    resp_str = str(resp.get("result", resp))[:300]
                else:
                    resp_str = str(resp)[:300]
                lines.append(f"[result] {name}: {resp_str}")

    except Exception as exc:
        lines.append(f"[meta] event parse error: {exc}")

    return lines


# ─── Async Runner ─────────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# The ADK execution model has three layers:
#
#   LlmAgent      — the "brain": holds the system prompt, model, and tools.
#                   Runs the reasoning-and-tool-calling loop automatically.
#
#   InMemoryRunner — the "engine": manages sessions (conversation history),
#                    dispatches runs to the agent, and emits Event objects.
#                    "InMemory" means session history is lost on process restart.
#                    Swap for a persistent runner for production deployments.
#
#   Session       — a conversation context that holds message history.
#                   Each agent run in this harness gets a fresh session so runs
#                   are independent (equivalent to pi's --no-session flag).
#
# WORKSHOP (Exercise 06 — Multi-Agent Pipeline)
# ──────────────────────────────────────────────
# To chain multiple agent passes, call _run_async() (or run_agent()) more than
# once with different model_id / inbox / outbox combinations.  The output of
# one call becomes the inbox for the next.
# See workshop/advanced/06_multi_agent.md for the full exercise.

async def _run_async(
    model_id: str,
    inbox: Path,
    outbox: Path,
    log_callback: Callable[[str], None],
) -> None:
    """Create and drive the ADK agent, emitting log lines via *log_callback*."""
    from google.adk.agents import LlmAgent          # noqa: PLC0415
    from google.adk.runners import InMemoryRunner   # noqa: PLC0415
    from google.genai import types as genai_types   # noqa: PLC0415

    model  = _build_model(model_id)
    tools  = _make_tools(inbox, outbox)

    # LlmAgent is the core reasoning agent: it calls the LLM, interprets tool
    # calls, executes them, and feeds results back — all in a loop until done.
    agent  = LlmAgent(
        name="file_processor",
        model=model,
        instruction=_SYSTEM_PROMPT,
        tools=tools,
    )

    # InMemoryRunner wires together the agent, a session service, and an
    # artifact service.  For this harness we only need the session service.
    runner  = InMemoryRunner(agent=agent, app_name="adk_agent")
    session = await runner.session_service.create_session(
        app_name="adk_agent",
        user_id="run_user",
    )

    # The user message is the initial prompt that kicks off the agentic loop.
    # It tells the agent where to find the task and its files.
    prompt = (
        f"Read {inbox}/instruction.md for your task, then execute it fully. "
        f"Input files are in {inbox}/. "
        f"Write all outputs (including agent.log summary) to {outbox}/. "
        f"Do not access paths outside {inbox}/ and {outbox}/."
    )

    user_message = genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text(text=prompt)],
    )

    log_callback(f"model={model_id}  inbox={inbox}  outbox={outbox}")

    # runner.run_async() starts the agentic loop and yields an Event for each
    # action the agent takes.  We convert each event to log lines immediately.
    async for event in runner.run_async(
        user_id="run_user",
        session_id=session.id,
        new_message=user_message,
    ):
        for line in _format_event(event):
            log_callback(line)


# ─── Public Synchronous API ───────────────────────────────────────────────────
#
# WORKSHOP (Exercise 06 — Multi-Agent Pipeline)
# ──────────────────────────────────────────────
# run_agent() is synchronous so it can be called from a plain threading.Thread
# (Flask's background thread model).  Internally it creates a new asyncio event
# loop via asyncio.run() — this is safe because the thread has no existing loop.
#
# To build a pipeline, call run_agent() multiple times in _pipeline_thread():
#
#   adk_agent.run_agent("claude-haiku-4-5-20251001", inbox, stage1_out, log)
#   adk_agent.run_agent(state.model, stage1_out, outbox, log)
#
# See workshop/advanced/06_multi_agent.md for a full worked example.

def run_agent(
    model_id: str,
    inbox: Path,
    outbox: Path,
    log_callback: Callable[[str], None],
) -> None:
    """Run the ADK agent synchronously (blocks until complete).

    Intended to be called from a background daemon thread started by
    web_app.py.  Raises on fatal errors; the caller is responsible for
    catching and recording them.

    Args:
        model_id:     Key from MODELS (e.g. "claude-sonnet-4-6").
        inbox:        Absolute path to the inbox directory.
        outbox:       Absolute path to the outbox directory.
        log_callback: Called with each log line as it is produced.
    """
    asyncio.run(_run_async(model_id, inbox, outbox, log_callback))
