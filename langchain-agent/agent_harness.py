#!/usr/bin/env python3
"""
LangChain Agent Harness
=======================
Core agent logic: model factory, system-prompt construction, and the main
agentic loop.  Can run standalone (CLI) or be driven by web_app.py.

Usage (standalone):
    python agent_harness.py

Environment variables:
    ANTHROPIC_API_KEY    API key for Anthropic models
    OPENROUTER_API_KEY   API key for OpenRouter
    DEFAULT_MODEL        default: anthropic:claude-sonnet-4-6
    INBOX_DIR            default: ./inbox
    OUTBOX_DIR           default: ./outbox
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("agent_harness")

# ─── Configuration ─────────────────────────────────────────────────────────────
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "anthropic:claude-sonnet-4-6")
INBOX_DIR     = Path(os.environ.get("INBOX_DIR",  "./inbox")).resolve()
OUTBOX_DIR    = Path(os.environ.get("OUTBOX_DIR", "./outbox")).resolve()


# ─── Model factory ─────────────────────────────────────────────────────────────
def create_model(model_name: str):
    """Instantiate a LangChain chat model from a model identifier string.

    Routing logic:
    1. 'openrouter:<model>' prefix  -> ChatOpenAI via OpenRouter base URL
    2. Only OPENROUTER_API_KEY set  -> ChatOpenAI via OpenRouter base URL
    3. All other cases              -> init_chat_model (handles 'anthropic:*', etc.)
    """
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    anthropic_key  = os.environ.get("ANTHROPIC_API_KEY")

    use_openrouter = model_name.startswith("openrouter:") or (
        openrouter_key and not anthropic_key
    )

    if use_openrouter:
        from langchain_openai import ChatOpenAI  # type: ignore

        clean = model_name.removeprefix("openrouter:")
        return ChatOpenAI(
            model=clean,
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_key or "",
        )

    from langchain.chat_models import init_chat_model  # type: ignore

    return init_chat_model(model_name)


# ─── System prompt ─────────────────────────────────────────────────────────────
def build_system_prompt(inbox_dir: Path, outbox_dir: Path, skill_content: str) -> str:
    """Construct the agent system prompt, optionally augmented by skill.md."""
    prompt = (
        f"You are a task automation agent.\n"
        f"- Read all input files from the inbox directory: {inbox_dir}\n"
        f"- Write every output file to the outbox directory: {outbox_dir}\n"
        f"- Never modify files in the inbox directory.\n"
        f"- Never write files outside the outbox directory.\n"
        f"- Do not use the 'task' sub-agent tool. Complete all work directly.\n"
        f"- Complete the full task before stopping."
    )
    if skill_content.strip():
        prompt += f"\n\n## Additional Behaviour Guidelines\n{skill_content.strip()}"
    return prompt


# ─── Agent runner ──────────────────────────────────────────────────────────────
def run_agent(
    inbox_dir: Path,
    outbox_dir: Path,
    model_name: str,
    log_callback,
) -> None:
    """Run the DeepAgents agentic loop.

    Args:
        inbox_dir:    Directory containing instruction.md and input files.
        outbox_dir:   Directory where output files will be written.
        model_name:   LangChain model identifier string.
        log_callback: Callable[[str], None] — receives each log line as produced.

    Raises:
        FileNotFoundError: If instruction.md is missing from inbox_dir.
        ImportError:        If required packages are not installed.
        Exception:          Any error raised by the agent.
    """
    from deepagents import create_deep_agent  # type: ignore
    from deepagents.backends import FilesystemBackend  # type: ignore
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # type: ignore

    log_callback("=== Agent run started ===")

    instruction_path = inbox_dir / "instruction.md"
    if not instruction_path.exists():
        raise FileNotFoundError("instruction.md not found in inbox/")

    instruction   = instruction_path.read_text(encoding="utf-8")
    skill_path    = inbox_dir / "skill.md"
    skill_content = (
        skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
    )

    system_prompt = build_system_prompt(inbox_dir, outbox_dir, skill_content)
    model         = create_model(model_name)

    log_callback(f"model={model_name}  skill={'yes' if skill_content.strip() else 'no'}")

    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        backend=FilesystemBackend(root_dir="/", virtual_mode=False),
    )

    log_callback(f"Inbox:  {inbox_dir}")
    log_callback(f"Outbox: {outbox_dir}")
    log_callback("─" * 60)

    for update in agent.stream(
        {"messages": [HumanMessage(content=instruction)]},
        stream_mode="updates",
    ):
        for _node, node_output in update.items():
            if not isinstance(node_output, dict):
                continue
            for msg in node_output.get("messages", []):
                if isinstance(msg, AIMessage):
                    content = msg.content
                    if isinstance(content, list):
                        text = " ".join(
                            b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    else:
                        text = str(content)
                    for line in text.splitlines():
                        if line.strip():
                            log_callback(f"[assistant] {line}")
                    for tc in getattr(msg, "tool_calls", []):
                        args_str = json.dumps(tc.get("args", {}))
                        truncated = args_str[:150] + ("…" if len(args_str) > 150 else "")
                        log_callback(f"[tool_use] {tc['name']} | {truncated}")
                elif isinstance(msg, ToolMessage):
                    result  = str(msg.content)
                    preview = result[:300] + ("…" if len(result) > 300 else "")
                    log_callback(f"[tool_result] {preview}")
                else:
                    if hasattr(msg, "content") and msg.content:
                        log_callback(str(msg.content))

    log_callback("─" * 60)
    log_callback("=== Agent run completed successfully ===")


# ─── Standalone entry point ────────────────────────────────────────────────────
def _main() -> None:
    """Run the agent from the command line without the web UI."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    inbox_dir  = INBOX_DIR
    outbox_dir = OUTBOX_DIR
    model_name = DEFAULT_MODEL

    inbox_dir.mkdir(parents=True, exist_ok=True)
    outbox_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  LangChain Agent (standalone)")
    print(f"  ────────────────────────────")
    print(f"  Inbox  : {inbox_dir}")
    print(f"  Outbox : {outbox_dir}")
    print(f"  Model  : {model_name}\n")

    log_lines: list[str] = []

    def _log(msg: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        print(f"  {msg}")
        log_lines.append(f"{ts}  {msg}")

    error: str | None = None
    try:
        run_agent(inbox_dir, outbox_dir, model_name, _log)
    except Exception as exc:
        _log(f"FATAL: {exc}")
        error = str(exc)

    outbox_dir.mkdir(parents=True, exist_ok=True)
    log_path = outbox_dir / "agent.log"
    with log_path.open("w", encoding="utf-8") as fh:
        for line in log_lines:
            fh.write(line + "\n")

    if error:
        sys.exit(1)


if __name__ == "__main__":
    _main()
