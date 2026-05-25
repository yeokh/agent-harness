#!/usr/bin/env python3
"""
Smolagents Agent — HuggingFace Smolagents file processor.

Reads instruction.md from inbox, processes files per those instructions,
writes output to outbox.  Supports Anthropic, OpenAI, and OpenRouter via
LiteLLM.  Call run_agent() from a background thread; it blocks until done,
calling log_callback for every log line produced.

Architecture
────────────
  web_app.py  →  run_agent()  →  ToolCallingAgent.run()
                                         ↓
                              step_callbacks=[_step_callback]
                                         ↓
                             ActionStep / FinalAnswerStep
                                         ↓
                              _format_step() → log lines
                                         ↓
                              log_callback (AgentState)
                                         ↓
                              Flask SSE → browser terminal

Comparison with ADK (adk_agent.py)
───────────────────────────────────
  ADK uses:        google.adk LlmAgent + InMemoryRunner (async event loop)
  Smolagents uses: smolagents ToolCallingAgent (synchronous, step callbacks)

  ADK tools:       plain Python functions passed directly to LlmAgent
  Smolagents tools: functions must be wrapped with @tool (or tool()) to become
                    Tool objects with .name / .description / .inputs schema

  ADK logging:     async event stream yielded per Event object
  Smolagents logging: synchronous step_callbacks called after each complete step

Workshop exercises that touch this file:
  Exercise 01 — Explore        : read MODELS, _make_tools, run_agent, _format_step
  Exercise 03 — Add Tool       : extend _make_tools() with new @tool functions
  Exercise 05 — Custom Toolsets: organise tools into domain modules
  Exercise 06 — Multi-Agent    : call run_agent() multiple times in a pipeline
"""

import json
import logging
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable

log = logging.getLogger("smolagent_agent")


# ─── Model Registry ──────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# This dict is the single source of truth for every model the agent can use.
# web_app.py calls get_available_models() on every /api/model request; the
# browser dropdown is built from the result.
#
# Keys explained:
#   provider   : routing path — "anthropic" | "openai" | "openrouter"
#   display    : human-readable name shown in the UI model selector
#   litellm_id : exact model string forwarded to smolagents LiteLLMModel
#   env        : the environment variable that must be non-empty to unlock
#                this model (UI only shows models you have a key for)
#
# Note on litellm_id format (different from ADK!):
#   ADK used bare model names like "claude-sonnet-4-6".
#   Smolagents LiteLLMModel prefers provider-prefixed IDs like
#   "anthropic/claude-sonnet-4-6" to make routing explicit.
#
# HOW TO ADD A MODEL (Exercise 01 stretch goal):
#   Duplicate any entry, change the dict key, litellm_id, and display.
#   If it is an OpenRouter model, the key must start with "openrouter/".
#   No other code changes are needed.

MODELS: dict[str, dict] = {
    # ── Anthropic (ANTHROPIC_API_KEY) ─────────────────────────────────────────
    "claude-opus-4-5": {
        "provider":   "anthropic",
        "display":    "Claude Opus 4.5 (most capable)",
        "litellm_id": "anthropic/claude-opus-4-5",
        "env":        "ANTHROPIC_API_KEY",
    },
    "claude-sonnet-4-6": {
        "provider":   "anthropic",
        "display":    "Claude Sonnet 4.6 (balanced)",
        "litellm_id": "anthropic/claude-sonnet-4-6",
        "env":        "ANTHROPIC_API_KEY",
    },
    "claude-haiku-4-5-20251001": {
        "provider":   "anthropic",
        "display":    "Claude Haiku 4.5 (fast)",
        "litellm_id": "anthropic/claude-haiku-4-5-20251001",
        "env":        "ANTHROPIC_API_KEY",
    },
    # ── OpenAI (OPENAI_API_KEY) ───────────────────────────────────────────────
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
    # ── OpenRouter (OPENROUTER_API_KEY) ───────────────────────────────────────
    # OpenRouter proxies 200+ models; the model string uses provider/name format.
    # See https://openrouter.ai/models for the full catalogue.
    "openrouter/anthropic/claude-3-5-sonnet": {
        "provider":   "openrouter",
        "display":    "OR: Claude 3.5 Sonnet",
        "litellm_id": "openrouter/anthropic/claude-3-5-sonnet",
        "env":        "OPENROUTER_API_KEY",
    },
    "openrouter/anthropic/claude-3-7-sonnet": {
        "provider":   "openrouter",
        "display":    "OR: Claude 3.7 Sonnet",
        "litellm_id": "openrouter/anthropic/claude-3-7-sonnet",
        "env":        "OPENROUTER_API_KEY",
    },
    "openrouter/google/gemini-2.5-flash": {
        "provider":   "openrouter",
        "display":    "OR: Gemini 2.5 Flash",
        "litellm_id": "openrouter/google/gemini-2.5-flash",
        "env":        "OPENROUTER_API_KEY",
    },
    "openrouter/openai/gpt-4o": {
        "provider":   "openrouter",
        "display":    "OR: GPT-4o",
        "litellm_id": "openrouter/openai/gpt-4o",
        "env":        "OPENROUTER_API_KEY",
    },
    "openrouter/meta-llama/llama-4-maverick": {
        "provider":   "openrouter",
        "display":    "OR: Llama 4 Maverick",
        "litellm_id": "openrouter/meta-llama/llama-4-maverick",
        "env":        "OPENROUTER_API_KEY",
    },
}


# ─── Dynamic Model Discovery ─────────────────────────────────────────────────
#
# These functions query the provider APIs at runtime so the model dropdown
# always reflects what your API key actually has access to, without requiring
# manual updates to the MODELS dict above.
#
# Results are cached for _DYNAMIC_CACHE_TTL seconds to avoid a round-trip on
# every /api/model request.  MODELS serves as a static fallback for any
# provider whose live fetch fails or whose key is absent.

_DYNAMIC_MODELS: dict[str, dict] = {}
_dynamic_cache_ts: float = 0.0
_DYNAMIC_CACHE_TTL: int = 300  # seconds


def _fetch_anthropic_models() -> list[tuple[str, dict]]:
    """Return (model_id, cfg) pairs from the Anthropic models API."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return []
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return [
            (m["id"], {
                "provider":   "anthropic",
                "display":    m.get("display_name", m["id"]),
                "litellm_id": f"anthropic/{m['id']}",
                "env":        "ANTHROPIC_API_KEY",
            })
            for m in data.get("data", [])
        ]
    except Exception as exc:
        log.warning("Failed to fetch Anthropic models: %s", exc)
        return []


def _fetch_openrouter_models() -> list[tuple[str, dict]]:
    """Return (model_id, cfg) pairs from the OpenRouter models API."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return []
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return [
            (f"openrouter/{m['id']}", {
                "provider":   "openrouter",
                "display":    f"OR: {m.get('name', m['id'])}",
                "litellm_id": f"openrouter/{m['id']}",
                "env":        "OPENROUTER_API_KEY",
            })
            for m in data.get("data", [])
            if not m["id"].startswith("~")  # skip alias entries
        ]
    except Exception as exc:
        log.warning("Failed to fetch OpenRouter models: %s", exc)
        return []


def _refresh_dynamic_models() -> None:
    """Populate _DYNAMIC_MODELS from live APIs; no-op if cache is fresh."""
    global _DYNAMIC_MODELS, _dynamic_cache_ts
    if time.time() - _dynamic_cache_ts < _DYNAMIC_CACHE_TTL and _DYNAMIC_MODELS:
        return
    fresh: dict[str, dict] = {}
    for model_id, cfg in _fetch_anthropic_models() + _fetch_openrouter_models():
        fresh[model_id] = cfg
    _DYNAMIC_MODELS = fresh
    _dynamic_cache_ts = time.time()


def get_available_models() -> list[dict]:
    """Return the list of models available with the current API keys.

    Prefers live data from provider APIs (refreshed every 5 minutes) and falls
    back to the static MODELS registry when a fetch fails or a key is absent.
    Called by web_app.py on every GET /api/model request.
    """
    _refresh_dynamic_models()

    # Providers covered by a successful live fetch — skip their static entries.
    dynamic_providers = {cfg["provider"] for cfg in _DYNAMIC_MODELS.values()}

    result: list[dict] = []
    seen: set[str] = set()

    for model_id, cfg in _DYNAMIC_MODELS.items():
        result.append({"id": model_id, "display": cfg["display"], "provider": cfg["provider"]})
        seen.add(model_id)

    # Static fallback: include only if the provider had no live data.
    for model_id, cfg in MODELS.items():
        if model_id in seen or cfg["provider"] in dynamic_providers:
            continue
        if os.environ.get(cfg["env"]):
            result.append({"id": model_id, "display": cfg["display"], "provider": cfg["provider"]})

    return result


def default_model() -> str:
    """Pick the first available model, preferring Anthropic → OpenAI → OpenRouter."""
    available = get_available_models()
    for provider in ("anthropic", "openai", "openrouter"):
        for m in available:
            if m["provider"] == provider:
                return m["id"]
    return next(iter(MODELS))


# ─── Model Factory ────────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# This function converts a model_id string into a smolagents LiteLLMModel.
# LiteLLMModel is smolagents' bridge to any LLM provider through LiteLLM.
#
# COMPARISON with ADK:
#   ADK:        LiteLlm(model="claude-sonnet-4-6", ...)            ← ADK class
#   Smolagents: LiteLLMModel(model_id="anthropic/claude-sonnet-4-6")  ← smolagents class
#
# Routing logic (same concept, different API):
#   openrouter/* → LiteLLMModel with explicit api_base + api_key
#   anthropic/*  → LiteLLMModel reads ANTHROPIC_API_KEY from environment
#   openai/*     → LiteLLMModel reads OPENAI_API_KEY from environment
#
# The returned object is passed directly to ToolCallingAgent(model=...).

def _build_model(model_id: str):
    """Return the appropriate smolagents LiteLLMModel instance for *model_id*."""
    if model_id in MODELS:
        cfg = MODELS[model_id]
    elif model_id in _DYNAMIC_MODELS:
        cfg = _DYNAMIC_MODELS[model_id]
    else:
        raise ValueError(f"Unknown model: {model_id!r}")
    litellm  = cfg["litellm_id"]
    provider = cfg["provider"]

    from smolagents import LiteLLMModel  # noqa: PLC0415

    if provider == "openrouter":
        # OpenRouter requires the API base URL and key to be explicit.
        return LiteLLMModel(
            model_id=litellm,
            api_base="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        )

    # For Anthropic and OpenAI, LiteLLM auto-reads the key from the environment.
    # We pass the key explicitly too as a safety net.
    return LiteLLMModel(
        model_id=litellm,
        api_key=os.environ.get(cfg["env"], ""),
    )


# ─── Agent Tools ──────────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 03 — Add a Python Tool)
# ───────────────────────────────────────────
# In HuggingFace Smolagents, tools are Python functions wrapped with the
# @tool decorator (or tool() function call).  Smolagents inspects:
#   • function name       → tool name (what the LLM calls)
#   • docstring           → tool description + parameter descriptions
#   • type annotations    → parameter schema the LLM must follow
#   • return type (-> str)→ output_type set to "string"
#
# KEY DIFFERENCE from ADK:
#   ADK tools: plain Python functions passed directly to LlmAgent(tools=[...])
#   Smolagents tools: must be wrapped with tool() to become Tool objects
#     with .name, .description, and .inputs schema attributes.
#
# In this harness, tools are closures defined inside _make_tools() so they
# can capture the inbox and outbox paths without using global state.
# Each closure is converted to a Tool with the tool() wrapper.
#
# To add a new tool:
#   1. Write a function inside _make_tools() following the pattern below.
#   2. Wrap it with _tool() in the return list at the bottom.
#   3. Restart web_app.py — no other changes needed.
#
# PLACEHOLDER ─ add your custom tools below run_bash, before the return.
#
# Example tools to try for Exercise 03:
#   • word_count(filepath)            — count lines and words in a file
#   • convert_csv_to_json(filepath)   — parse CSV and return JSON string
#   • validate_json(filepath)         — check a JSON file parses correctly
#
# WORKSHOP (Exercise 05 — Custom Toolsets)
# ─────────────────────────────────────────
# For larger projects, move related tool functions into their own module, e.g.:
#   tools/csv_tools.py    → CSV-specific helpers
#   tools/report_tools.py → formatting and rendering
# Then import and include them here:
#   from tools.csv_tools import make_csv_tools
#   extra_tools = make_csv_tools(inbox, outbox)   # returns list of Tool objects
#   return [..., *extra_tools]

def _make_tools(inbox: Path, outbox: Path) -> list:
    """Return smolagents Tool objects bound to *inbox* and *outbox* paths.

    All tools are defined as closures (capturing paths at construction time)
    then converted to Tool objects via smolagents' tool() wrapper.
    This pattern keeps tools stateless and path-safe.
    """
    # Import the smolagents tool() factory inside the function so the module
    # can be imported even if smolagents is not yet installed.
    from smolagents import tool as _tool  # noqa: PLC0415

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
        rows = [
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

        Use this for tasks requiring external tools: extracting archives,
        running Python one-liners, converting file formats, or validating JSON.
        The working directory is set to the parent of inbox/outbox.

        Args:
            command: Shell command string to execute.  Piping, redirection,
                     and multi-command chains (&&, ;) are all supported.
        """
        # Block a small set of obviously destructive patterns.
        # This is NOT a complete sandbox — see Exercise 04 for the guardrail.
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
    # Add your new tool functions here, then wrap them with _tool() in the list.
    #
    # IMPORTANT: Unlike ADK (plain functions), smolagents requires the tool()
    # wrapper to register name, description, and input schema.
    #
    # Template:
    #
    # def my_tool(arg1: str, arg2: int = 0) -> str:
    #     """One-line description the LLM sees when deciding whether to call this.
    #
    #     Longer explanation of behaviour and edge cases.
    #
    #     Args:
    #         arg1: Description of first argument.
    #         arg2: Description of second argument (optional, defaults to 0).
    #     """
    #     ...
    #     return "result string"
    # ─────────────────────────────────────────────────────────────────────────

    # Wrap each closure with smolagents' tool() to register it as a Tool object.
    # tool() reads __name__, __doc__, and __annotations__ from the closure.
    return [
        _tool(read_file),
        _tool(write_file),
        _tool(list_files),
        _tool(run_bash),
    ]
    # Exercise 03: append your new tool, e.g.:
    # return [_tool(read_file), _tool(write_file), _tool(list_files),
    #         _tool(run_bash), _tool(my_tool)]


# ─── Task Prompt Template ─────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# KEY DIFFERENCE from ADK:
#   ADK:       _SYSTEM_PROMPT passed to LlmAgent(instruction=...) — becomes
#              the standing system message for EVERY LLM call.
#
#   Smolagents: uses its OWN default system prompt (TOOL_CALLING_SYSTEM_PROMPT)
#              that includes tool descriptions and calling conventions.
#              We do NOT override the system prompt — doing so would break
#              the tool-calling format instructions.
#
#              Instead, we embed our agent guidelines in the TASK string
#              passed to agent.run(task).  This is the idiomatic smolagents way.
#
# The template is filled with actual inbox/outbox paths at runtime (in run_agent).
# The task-specific instructions live in inbox/instruction.md and are read by
# the agent at runtime using the read_file tool.  Keeping them separate means
# you can change the task without touching this code or restarting the server.
#
# WORKSHOP (Exercise 03 — Add Tool)
# ──────────────────────────────────
# If you add a new tool requiring special guidance, add a bullet point here
# so the agent applies it even when instruction.md does not mention it.

_TASK_TEMPLATE = """\
You are a file-processing agent.  Use the tools available to complete your task.

Your working directories:
  inbox  (read-only): {inbox}
  outbox (writable):  {outbox}

Steps to follow:
1. Call list_files("inbox") to discover available payload files.
2. Call read_file("instruction.md") to read your specific task instructions.
3. Process each relevant file per those instructions.
4. Write all output files to the outbox using write_file.
5. Write a concise processing summary to outbox/agent.log.

Constraints:
- Only read from inbox; only write to outbox.
- If the inbox contains a .tar or .zip archive, extract it with run_bash first.
- When a task requires computation (sorting, parsing CSV), prefer run_bash with
  a Python one-liner over doing arithmetic in your reasoning.
- Do not invent data; base all output strictly on the input files.
- Confirm each write_file call succeeded before moving to the next file.

Begin now.
"""


# ─── Step Formatter ───────────────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# Smolagents emits step objects via step_callbacks as the agent works.
# Each step represents one complete reasoning-and-tool-execution cycle.
#
# COMPARISON with ADK:
#   ADK:        async event stream of Event objects; each event is one
#               atomic action (text, function_call, or function_response).
#   Smolagents: synchronous step_callbacks; each step BUNDLES all three:
#               the model's reasoning text, the tool call, and the result.
#
# Step types and what they contain:
#
#   ActionStep      → the model called a tool
#     .model_output_message : LLM reasoning text before the tool call
#     .tool_calls           : list of ToolCall(name, arguments)
#     .observations         : tool result returned to the model
#     .error                : any error during tool execution
#
#   PlanningStep    → model created a plan (optional, if planning enabled)
#     .model_output_message : the plan text
#
#   FinalAnswerStep → model returned a final answer (run complete)
#     .final_answer         : the answer string
#
# Log prefix colour coding in index.html:
#   [tool_use] → green   [result] → grey   [assistant] → white

def _format_step(step) -> list[str]:
    """Convert a single smolagents step into zero or more log lines."""
    lines: list[str] = []
    try:
        step_type = type(step).__name__

        if step_type == "ActionStep":
            # ── Model's reasoning text (before the tool call) ────────────────
            msg = getattr(step, "model_output_message", None)
            if msg:
                content = getattr(msg, "content", None)
                if isinstance(content, str) and content.strip():
                    for line in content.strip().split("\n"):
                        if line.strip():
                            lines.append(f"[assistant] {line}")
                elif isinstance(content, list):
                    # Some models return content as a list of blocks
                    for block in content:
                        if isinstance(block, dict):
                            text = block.get("text", "")
                        else:
                            text = getattr(block, "text", "") or ""
                        if text and text.strip():
                            lines.append(f"[assistant] {text.strip()}")

            # ── Tool calls the model requested ───────────────────────────────
            tool_calls = getattr(step, "tool_calls", None) or []
            for tc in tool_calls:
                name = getattr(tc, "name", "?")
                args = getattr(tc, "arguments", {}) or {}
                if isinstance(args, dict):
                    args_str = ", ".join(
                        f"{k}={repr(str(v))[:60]}" for k, v in args.items()
                    )
                else:
                    args_str = str(args)[:120]
                lines.append(f"[tool_use] {name}({args_str})")

            # ── Tool result returned to the model ────────────────────────────
            obs = getattr(step, "observations", None)
            if obs and str(obs).strip():
                lines.append(f"[result] {str(obs).strip()[:300]}")

            # ── Any error that occurred ───────────────────────────────────────
            error = getattr(step, "error", None)
            if error:
                lines.append(f"[error] {error}")

        elif step_type == "PlanningStep":
            msg = getattr(step, "model_output_message", None)
            if msg:
                content = getattr(msg, "content", None)
                if isinstance(content, str) and content.strip():
                    lines.append(f"[assistant] [Plan] {content.strip()[:400]}")

        elif step_type == "FinalAnswerStep":
            answer = getattr(step, "final_answer", None)
            if answer and str(answer).strip():
                lines.append(f"[assistant] [Done] {str(answer).strip()[:400]}")

    except Exception as exc:
        lines.append(f"[meta] step parse error: {exc}")

    return lines


# ─── Public Synchronous API ───────────────────────────────────────────────────
#
# WORKSHOP (Exercise 01 — Explore)
# ─────────────────────────────────
# run_agent() is synchronous so it can be called from a plain threading.Thread
# (Flask's background thread model).
#
# COMPARISON with ADK:
#   ADK:        asyncio.run(_run_async(...))   — ADK is inherently async
#   Smolagents: agent.run(task)                — smolagents is synchronous
#
# Because smolagents is synchronous, we do NOT need an inner event loop or the
# asyncio.run() wrapper that the ADK version requires.  The threading.Thread
# in web_app.py provides the background execution directly.
#
# WORKSHOP (Exercise 06 — Multi-Agent Pipeline)
# ──────────────────────────────────────────────
# To build a pipeline, call run_agent() multiple times in _pipeline_thread():
#
#   smolagent_agent.run_agent("claude-haiku-4-5-20251001", inbox, stage1_out, log)
#   smolagent_agent.run_agent(state.model, stage1_out, outbox, log)
#
# See workshop/advanced/06_multi_agent.md for the full exercise.

def run_agent(
    model_id: str,
    inbox: Path,
    outbox: Path,
    log_callback: Callable[[str], None],
) -> None:
    """Run the smolagents ToolCallingAgent synchronously (blocks until complete).

    Intended to be called from a background daemon thread started by web_app.py.
    Raises on fatal errors; the caller is responsible for catching them.

    Args:
        model_id:     Key from MODELS (e.g. "claude-sonnet-4-6").
        inbox:        Absolute path to the inbox directory.
        outbox:       Absolute path to the outbox directory.
        log_callback: Called with each log line as it is produced.
    """
    from smolagents import ToolCallingAgent  # noqa: PLC0415

    model = _build_model(model_id)
    tools = _make_tools(inbox, outbox)

    def _step_callback(step) -> None:
        """Forward each step's log lines to the Flask SSE stream."""
        for line in _format_step(step):
            log_callback(line)

    # ToolCallingAgent uses the model's native function-calling API
    # (Claude tool_use, OpenAI function calls) rather than string-parsed commands.
    # max_steps limits tool calls to prevent runaway loops.
    # verbosity_level=0 suppresses rich console output (we log via callback instead).
    agent = ToolCallingAgent(
        tools=tools,
        model=model,
        step_callbacks=[_step_callback],
        max_steps=30,
        verbosity_level=0,
    )

    task = _TASK_TEMPLATE.format(inbox=inbox, outbox=outbox)
    log_callback(f"model={model_id}  inbox={inbox}  outbox={outbox}")

    # agent.run() blocks until the task is complete (or max_steps is reached).
    # The step_callbacks above stream each tool call and result as it happens.
    result = agent.run(task)

    # The return value of agent.run() is the final answer the LLM produced.
    if result and str(result).strip():
        log_callback(f"[assistant] {str(result).strip()[:500]}")
