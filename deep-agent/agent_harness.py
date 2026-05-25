#!/usr/bin/env python3
"""
Deep Agent Harness — Core Agent Logic
======================================
Implements the agentic loop using LangChain DeepAgents.

Architecture:
  • instruction.md in inbox/   → loaded as the agent task
  • skill.md in inbox/         → optional behaviour guidelines appended to system prompt
  • run_agent()                → synchronous entry point (called by web_app.py)

Environment variables:
  ANTHROPIC_API_KEY    API key for Anthropic (e.g. anthropic:claude-sonnet-4-6)
  OPENROUTER_API_KEY   API key for OpenRouter (any model via openrouter.ai)
  DEFAULT_MODEL        default: anthropic:claude-sonnet-4-6
  INBOX_DIR            default: ./inbox
  OUTBOX_DIR           default: ./outbox

Model string formats:
  anthropic:claude-sonnet-4-6          -> uses ANTHROPIC_API_KEY
  anthropic:claude-opus-4-7            -> uses ANTHROPIC_API_KEY
  openrouter:anthropic/claude-opus-4-7 -> uses OPENROUTER_API_KEY
  openrouter:openai/gpt-4o             -> uses OPENROUTER_API_KEY
  (any string when only OPENROUTER_API_KEY is set -> routed to OpenRouter)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger("agent_harness")


# ─── Model factory ─────────────────────────────────────────────────────────────
def _create_model(model_name: str):
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


# ─── System prompt builder ─────────────────────────────────────────────────────
def _build_system_prompt(skill_content: str, inbox_dir: Path, outbox_dir: Path) -> str:
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


# ─── Main agent run ─────────────────────────────────────────────────────────────
def run_agent(
    inbox_dir: Path,
    outbox_dir: Path,
    model_name: str,
    log_callback: Callable[[str], None] | None = None,
) -> None:
    """
    Run the DeepAgents agent against the given inbox/outbox directories.

    Args:
        inbox_dir:    Directory containing instruction.md and payload files.
        outbox_dir:   Directory the agent writes results to.
        model_name:   LangChain model identifier string.
        log_callback: Optional callable; receives each log line in real-time
                      (used by web_app.py to stream logs to the browser).

    Raises:
        FileNotFoundError: If instruction.md is missing from inbox_dir.
        ImportError:       If deepagents or langchain dependencies are not installed.
        Exception:         Any error from the underlying agent execution.
    """
    from deepagents import create_deep_agent  # type: ignore
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # type: ignore

    def _log(msg: str) -> None:
        log.info(msg)
        if log_callback:
            log_callback(msg)

    instruction_path = inbox_dir / "instruction.md"
    if not instruction_path.exists():
        raise FileNotFoundError("instruction.md not found in inbox/")

    instruction   = instruction_path.read_text(encoding="utf-8")
    skill_path    = inbox_dir / "skill.md"
    skill_content = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""

    system_prompt = _build_system_prompt(skill_content, inbox_dir, outbox_dir)
    model         = _create_model(model_name)

    _log(f"model={model_name}  skill={'yes' if skill_content.strip() else 'no'}")

    from deepagents.backends import FilesystemBackend  # type: ignore

    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        backend=FilesystemBackend(root_dir="/", virtual_mode=False),
    )

    _log(f"Inbox:  {inbox_dir}")
    _log(f"Outbox: {outbox_dir}")
    _log("─" * 60)

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
                            _log(f"[assistant] {line}")
                    for tc in getattr(msg, "tool_calls", []):
                        args_str  = json.dumps(tc.get("args", {}))
                        truncated = args_str[:150] + ("…" if len(args_str) > 150 else "")
                        _log(f"[tool_use] {tc['name']} | {truncated}")
                elif isinstance(msg, ToolMessage):
                    result  = str(msg.content)
                    preview = result[:300] + ("…" if len(result) > 300 else "")
                    _log(f"[tool_result] {preview}")
                else:
                    if hasattr(msg, "content") and msg.content:
                        _log(str(msg.content))


# ─── Standalone entry point ───────────────────────────────────────────────────
# Run without the web UI: python agent_harness.py
def _main() -> None:
    inbox  = Path(os.environ.get("INBOX_DIR",  "./inbox")).resolve()
    outbox = Path(os.environ.get("OUTBOX_DIR", "./outbox")).resolve()
    model  = os.environ.get("DEFAULT_MODEL", "anthropic:claude-sonnet-4-6")

    outbox.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(outbox / "agent.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    log.info("=" * 60)
    log.info(
        "Deep Agent Harness — Standalone Mode  %s",
        datetime.now(timezone.utc).isoformat(),
    )
    log.info("inbox=%s  outbox=%s  model=%s", inbox, outbox, model)
    log.info("=" * 60)

    try:
        run_agent(inbox, outbox, model)
    except FileNotFoundError as exc:
        log.error("%s", exc)
        sys.exit(1)
    except ImportError as exc:
        log.error(
            "Import error: %s — install: pip install deepagents langchain-anthropic langchain-openai",
            exc,
        )
        sys.exit(1)
    except Exception as exc:
        log.error("Fatal: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    _main()
