#!/usr/bin/env python3
"""
Pydantic Assistant — Flask Web Server

Serves one UI that drives two execution modes against the same agent/ /
input/ / output/ folders and the same scoped tool set:

    Chat  — interactive, multi-turn conversation (POST /api/chat, SSE)
    Batch — one-shot autonomous run (POST /api/batch/run, SSE log stream)

A Job Pack loader (GET /api/jobpacks, POST /api/jobpacks/load) can stage a
pack's agent/ + input/ files from the JOBS_DIR library before a Batch run.

File access is unified across both modes: any file in agent/, input/, or
output/ can be viewed (GET /api/file/<folder>/<name>); only agent/ and
input/ files are editable (PUT/POST/DELETE) — output/ is read-only.

Environment variables:
    ANTHROPIC_API_KEY     Anthropic provider key
    OPENAI_API_KEY        OpenAI provider key (also used for openai-compatible)
    OPENROUTER_API_KEY    OpenRouter provider key
    OPENAI_BASE_URL       OpenAI-compatible endpoint (default http://localhost:11434/v1)
    API_PROVIDER          anthropic | openai | openrouter | openai-compatible
    MODEL                 model id (default varies by provider)
    MAX_TURNS             max agentic loop iterations per Chat turn or Batch run (default 50)
    MAX_OUTPUT_TOKENS     token budget per model response (default 16384)
    ALLOW_SHELL           set false to disable run_command entirely (default true)
    SHELL_TIMEOUT         max seconds per shell command (default 60)
    DISABLED_TOOLS        comma-separated tool names to remove from the agent
    AGENT_DIR / INPUT_DIR / OUTPUT_DIR   folder overrides (default ./agent, ./input, ./output)
    JOBS_DIR              job-pack library used by the Batch tab's Load button (default ./sample-jobs)
    PORT / HOST           web server bind (default 8081 / 0.0.0.0)
"""

import asyncio
import json
import logging
import os
import queue
import re
import shutil
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import httpx
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import agent_core

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AGENT_DIR = Path(os.environ.get("AGENT_DIR", "./agent")).resolve()
INPUT_DIR = Path(os.environ.get("INPUT_DIR", "./input")).resolve()
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "./output")).resolve()
JOBS_DIR = Path(os.environ.get("JOBS_DIR", "./sample-jobs")).resolve()
PORT = int(os.environ.get("PORT", "8081"))
HOST = os.environ.get("HOST", "0.0.0.0")

for _d in (AGENT_DIR, INPUT_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

FOLDERS = {"agent": AGENT_DIR, "input": INPUT_DIR, "output": OUTPUT_DIR}
EDITABLE_FOLDERS = ("agent", "input")

INSTRUCTION_FILE = AGENT_DIR / "instruction.md"
PROJECT_ROOT = Path(__file__).resolve().parent
README_FILE = PROJECT_ROOT / "README.md"
JOB_HISTORY_FILE = PROJECT_ROOT / ".job_history.json"
JOB_HISTORY_MAX = 20
HIDDEN_FILES = {".job_history.json", ".gitkeep"}

# Map each provider to the env var name that holds its API key.
# openai-compatible is excluded from the key check (local models need no key).
KEY_ENV_VARS = {
    "anthropic":         "ANTHROPIC_API_KEY",
    "openai":            "OPENAI_API_KEY",
    "openrouter":        "OPENROUTER_API_KEY",
    "openai-compatible": "OPENAI_API_KEY",
}
NO_KEY_PROVIDERS = {"openai-compatible"}

# ---------------------------------------------------------------------------
# Application log capture
# ---------------------------------------------------------------------------

class _DequeHandler(logging.Handler):
    def __init__(self, maxlen: int = 500):
        super().__init__()
        self._records: deque = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._records.append({
                "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "msg": self.format(record),
            })
        except Exception:
            pass

    def snapshot(self, offset: int = 0) -> list:
        return list(self._records)[offset:]


_app_log_handler = _DequeHandler(maxlen=500)
_app_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(_app_log_handler)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)
log = logging.getLogger("web_app")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Chat session (Chat mode)
# ---------------------------------------------------------------------------

INTRO_MESSAGE = (
    "Hi, I'm an AI assistant. I can read instructions and skills from Agent Files, "
    "process files from Input Files, and write results to Output Files. I can do this "
    "interactively here in Chat, or you can submit the same instructions as a Batch job."
)

# Starter instruction.md content, auto-created whenever agent/instruction.md is missing
# (fresh install, manual deletion, etc.) so the app is never left without one.
DEFAULT_INSTRUCTION = (
    f"{INTRO_MESSAGE}\n\n"
    "---\n\n"
    "This is a starter `instruction.md`, created automatically because none existed yet. "
    "Replace this content with your own instructions describing what you want the agent to "
    "do — this file is the system prompt for both Chat and Batch mode. You can also load a "
    "ready-made Job Pack from the Batch tab instead of writing your own.\n"
)


class ChatSession:
    """Thread-safe conversation session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.instruction: str = ""
        self.model_messages: list = []
        self.display_messages: list = []
        self.status: str = "idle"
        self.cancel_event = threading.Event()

    def reset(self, instruction: str) -> None:
        with self._lock:
            self.status = "idle"
            self.instruction = instruction
            self.model_messages = []
            self.display_messages = [{
                "id": str(uuid.uuid4()),
                "role": "ai",
                "type": "intro",
                "content": INTRO_MESSAGE,
                "timestamp": _now(),
            }]
            if instruction.strip():
                self.display_messages.append({
                    "id": str(uuid.uuid4()),
                    "role": "you",
                    "type": "instruction",
                    "content": instruction,
                    "timestamp": _now(),
                })

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "display_messages": list(self.display_messages),
            }

    def add_display_message(self, msg: dict) -> None:
        with self._lock:
            self.display_messages.append(msg)

    def update_model_messages(self, messages: list) -> None:
        with self._lock:
            self.model_messages = messages

    def get_model_messages(self) -> list:
        with self._lock:
            return list(self.model_messages)

    def get_instruction(self) -> str:
        with self._lock:
            return self.instruction

    def set_status(self, status: str) -> None:
        with self._lock:
            self.status = status


chat_session = ChatSession()


# ---------------------------------------------------------------------------
# Agent state (Batch mode)
# ---------------------------------------------------------------------------

class AgentState:
    """Thread-safe container for one batch run's state, logs, and metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.status = "idle"  # idle | running | completed | error
        self.logs: deque[dict] = deque(maxlen=2000)
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.error: str | None = None
        self.metrics: dict | None = None

    def start(self) -> None:
        with self._lock:
            self.status = "running"
            self.logs.clear()
            self.started_at = _now()
            self.finished_at = None
            self.error = None
            self.metrics = None

    def finish(self, error: str | None = None, stats: dict | None = None) -> None:
        with self._lock:
            self.status = "error" if error else "completed"
            self.finished_at = _now()
            self.error = error
            self.metrics = self._build_metrics(stats or {})

    def _build_metrics(self, stats: dict) -> dict:
        duration = None
        if self.started_at and self.finished_at:
            duration = (
                datetime.fromisoformat(self.finished_at)
                - datetime.fromisoformat(self.started_at)
            ).total_seconds()
        return {
            "duration_seconds": duration,
            "total_turns": stats.get("total_turns"),
            "total_cost_usd": stats.get("total_cost_usd"),
            "total_input_tokens": stats.get("total_input_tokens"),
            "total_output_tokens": stats.get("total_output_tokens"),
            "log_lines": len(self.logs),
            "output_files": _count_output_files(),
            "status": self.status,
        }

    def reset(self) -> None:
        with self._lock:
            self.status = "idle"
            self.logs.clear()
            self.started_at = None
            self.finished_at = None
            self.error = None
            self.metrics = None

    def add_log(self, message: str) -> None:
        with self._lock:
            self.logs.append({"time": _now(), "msg": message})

    def snapshot(self, offset: int = 0) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "error": self.error,
                "metrics": self.metrics,
                "log_count": len(self.logs),
                "logs": list(self.logs)[offset:],
            }


batch_state = AgentState()
_batch_cancel_event = threading.Event()
_batch_thread_ref: threading.Thread | None = None


def _count_output_files() -> int:
    if not OUTPUT_DIR.exists():
        return 0
    return sum(
        1 for p in OUTPUT_DIR.rglob("*")
        if p.is_file() and p.name not in HIDDEN_FILES and p.name != "agent.log"
    )


# ---------------------------------------------------------------------------
# Job history (Batch mode)
# ---------------------------------------------------------------------------

def _load_job_history() -> list:
    try:
        if JOB_HISTORY_FILE.is_file():
            data = json.loads(JOB_HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Could not read job history: %s", exc)
    return []


def _save_job_history(history: list) -> None:
    try:
        JOB_HISTORY_FILE.write_text(
            json.dumps(history[-JOB_HISTORY_MAX:], indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("Could not write job history: %s", exc)


def _append_job_history(snap: dict) -> None:
    metrics = snap.get("metrics") or {}
    provider = os.environ.get("API_PROVIDER", agent_core.DEFAULT_PROVIDER)
    default_model = agent_core.DEFAULT_MODEL_BY_PROVIDER.get(provider, agent_core.DEFAULT_MODEL)
    entry = {
        "run_id": snap.get("started_at"),
        "status": snap.get("status"),
        "provider": provider,
        "model": os.environ.get("MODEL", default_model),
        "duration_seconds": metrics.get("duration_seconds"),
        "total_turns": metrics.get("total_turns"),
        "total_cost_usd": metrics.get("total_cost_usd"),
        "total_input_tokens": metrics.get("total_input_tokens"),
        "total_output_tokens": metrics.get("total_output_tokens"),
        "log_lines": metrics.get("log_lines"),
        "output_files": metrics.get("output_files"),
    }
    history = _load_job_history()
    history.append(entry)
    _save_job_history(history)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _ensure_default_instruction() -> None:
    """Create a starter instruction.md in agent/ if one doesn't exist yet."""
    if INSTRUCTION_FILE.is_file():
        return
    try:
        INSTRUCTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        INSTRUCTION_FILE.write_text(DEFAULT_INSTRUCTION, encoding="utf-8")
        log.info("No instruction.md found — created a default one in %s", AGENT_DIR)
    except OSError:
        log.exception("Could not create default instruction.md")


def _read_instruction() -> str:
    _ensure_default_instruction()
    if INSTRUCTION_FILE.is_file():
        return INSTRUCTION_FILE.read_text(encoding="utf-8", errors="replace")
    return ""


def _load_skills() -> tuple:
    """Return (combined_text, list_of_filenames) for all skill .md files in agent/."""
    sections = []
    files = []
    for md in sorted(AGENT_DIR.glob("*.md")):
        if md.name == "instruction.md":
            continue
        body = md.read_text(encoding="utf-8", errors="replace")
        sections.append(f"### {md.name}\n\n{body}")
        files.append(md.name)
    return "\n\n---\n\n".join(sections), files


def _safe_path(base: Path, rel: str) -> Path:
    target = (base / rel).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise ValueError(f"Path traversal denied: {rel}")
    return target


def _list_dir(directory: Path) -> list:
    result = []
    if not directory.exists():
        return result
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name in HIDDEN_FILES:
            continue
        stat = path.stat()
        result.append({
            "name": str(path.relative_to(directory)).replace("\\", "/"),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    return result


def _sanitise_filename(raw: str) -> str:
    return re.sub(r"[^\w.\-/]", "_", raw)


# ---------------------------------------------------------------------------
# Chat turn thread
# ---------------------------------------------------------------------------

def _run_chat_thread(
    user_message: str,
    prev_model_messages: list,
    instruction: str,
    event_queue: queue.Queue,
) -> None:
    chat_session.set_status("running")
    chat_session.cancel_event.clear()

    ai_text_parts = []
    tool_events = []

    def on_event(ev: dict) -> None:
        if ev["type"] == "delta":
            ai_text_parts.append(ev["content"])
        elif ev["type"] in ("tool_use", "tool_result"):
            tool_events.append(ev)
        event_queue.put(ev)

    try:
        new_messages = asyncio.run(
            agent_core.run_chat_turn(
                user_message=user_message,
                model_messages=prev_model_messages,
                agent_dir=AGENT_DIR,
                input_dir=INPUT_DIR,
                output_dir=OUTPUT_DIR,
                instruction=instruction,
                event_callback=on_event,
                cancel_event=chat_session.cancel_event,
            )
        )
        chat_session.update_model_messages(new_messages)

        full_text = "".join(ai_text_parts)
        ai_msg = {
            "id": str(uuid.uuid4()),
            "role": "ai",
            "type": "text",
            "content": full_text,
            "tool_events": tool_events,
            "timestamp": _now(),
        }
        chat_session.add_display_message(ai_msg)
        event_queue.put({"type": "done", "message": ai_msg})

    except Exception as exc:
        log.exception("Chat turn failed: %s", exc)
        err_msg = {
            "id": str(uuid.uuid4()),
            "role": "ai",
            "type": "error",
            "content": str(exc),
            "tool_events": [],
            "timestamp": _now(),
        }
        chat_session.add_display_message(err_msg)
        event_queue.put({"type": "error", "content": str(exc), "message": err_msg})
    finally:
        chat_session.set_status("idle")


# ---------------------------------------------------------------------------
# Batch run thread
# ---------------------------------------------------------------------------

def _run_batch_thread() -> None:
    stats_out: dict = {}
    _batch_cancel_event.clear()
    batch_state.start()
    batch_state.add_log("=== Batch run started ===")

    instruction = _read_instruction()
    log_path = OUTPUT_DIR / "agent.log"
    try:
        with log_path.open("w", encoding="utf-8") as log_fh:

            def _log(message: str) -> None:
                if message:
                    batch_state.add_log(message)
                    log_fh.write(message + "\n")
                    log_fh.flush()

            asyncio.run(
                agent_core.run_batch(
                    AGENT_DIR, INPUT_DIR, OUTPUT_DIR, instruction,
                    log_callback=_log, stats_out=stats_out, cancel_event=_batch_cancel_event,
                )
            )

        batch_state.finish(stats=stats_out)
        batch_state.add_log("=== Batch run completed successfully ===")
    except RuntimeError as exc:
        batch_state.finish(str(exc))
        batch_state.add_log(f"FATAL: {exc}")
    except Exception as exc:
        log.exception("Batch run failed")
        batch_state.finish(f"Unexpected error: {exc}")
        batch_state.add_log(f"FATAL: Unexpected error: {exc}")

    _append_job_history(batch_state.snapshot())


# ---------------------------------------------------------------------------
# Routes: Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/readme", methods=["GET"])
def api_readme():
    if not README_FILE.is_file():
        return jsonify({"found": False})
    content = README_FILE.read_text(encoding="utf-8", errors="replace")
    return jsonify({
        "found": True,
        "content": content,
        "size": README_FILE.stat().st_size,
    })


# ---------------------------------------------------------------------------
# Routes: Chat session
# ---------------------------------------------------------------------------

@app.route("/api/session", methods=["GET"])
def api_session():
    return jsonify(chat_session.snapshot())


@app.route("/api/chat/reset", methods=["POST"])
def api_chat_reset():
    if chat_session.status == "running":
        return jsonify({"error": "Cannot reset while a turn is running"}), 409
    chat_session.reset(_read_instruction())
    log.info("Chat session reset")
    return jsonify(chat_session.snapshot())


@app.route("/api/chat/cancel", methods=["POST"])
def api_chat_cancel():
    if chat_session.status != "running":
        return jsonify({"error": "No turn in progress"}), 409
    chat_session.cancel_event.set()
    return jsonify({"status": "cancelling"})


# ---------------------------------------------------------------------------
# Routes: Chat (SSE)
# ---------------------------------------------------------------------------

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": "Empty message"}), 400
    if chat_session.status == "running":
        return jsonify({"error": "A turn is already in progress"}), 409

    # /skills command — push all skill .md files into the conversation context
    if message.lower() in ("/skills", "/skill"):
        def _skills_stream():
            skills_text, skill_files = _load_skills()
            if not skills_text:
                content = "No skill files found in the agent folder."
                skill_files = []
            else:
                content = skills_text

            display_msg = {
                "id": str(uuid.uuid4()),
                "role": "you",
                "type": "skills",
                "content": content,
                "files": skill_files,
                "timestamp": _now(),
            }
            chat_session.add_display_message(display_msg)

            if skills_text:
                from pydantic_ai import ModelRequest, UserPromptPart
                skills_prompt = (
                    "The following skill reference documents are now available:\n\n"
                    + skills_text
                )
                new_msg = ModelRequest(parts=[UserPromptPart(content=skills_prompt)])
                prev = chat_session.get_model_messages()
                chat_session.update_model_messages(prev + [new_msg])

            yield _sse({"type": "done", "message": display_msg})

        return Response(
            stream_with_context(_skills_stream()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Regular message
    user_msg = {
        "id": str(uuid.uuid4()),
        "role": "you",
        "type": "user",
        "content": message,
        "timestamp": _now(),
    }
    chat_session.add_display_message(user_msg)

    prev_model_messages = chat_session.get_model_messages()
    instruction = chat_session.get_instruction()
    event_q: queue.Queue = queue.Queue()

    thread = threading.Thread(
        target=_run_chat_thread,
        args=(message, prev_model_messages, instruction, event_q),
        daemon=True,
        name="chat-turn",
    )
    thread.start()

    def _generate():
        yield _sse({"type": "user_message", "message": user_msg})
        while True:
            try:
                ev = event_q.get(timeout=60)
                yield _sse(ev)
                if ev.get("type") in ("done", "error"):
                    return
            except queue.Empty:
                if not thread.is_alive():
                    return
                yield _sse({"type": "ping"})

    return Response(
        stream_with_context(_generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Routes: Batch control
# ---------------------------------------------------------------------------

@app.route("/api/batch/run", methods=["POST"])
def api_batch_run():
    global _batch_thread_ref
    if batch_state.status == "running":
        return jsonify({"error": "A batch run is already in progress"}), 409

    if _batch_thread_ref is not None and _batch_thread_ref.is_alive():
        _batch_thread_ref.join(timeout=10)
        if _batch_thread_ref.is_alive():
            return jsonify({"error": "Previous run has not finished shutting down. Try again in a moment."}), 409

    if not INSTRUCTION_FILE.is_file():
        return jsonify({"error": "instruction.md not found in agent/ — create it first"}), 400

    provider = os.environ.get("API_PROVIDER", agent_core.DEFAULT_PROVIDER)
    if provider not in NO_KEY_PROVIDERS:
        env_var = KEY_ENV_VARS.get(provider)
        if env_var and not os.environ.get(env_var):
            return jsonify({"error": f"No API key configured for {provider}. Set {env_var}."}), 400

    thread = threading.Thread(target=_run_batch_thread, daemon=True, name="batch-run")
    _batch_thread_ref = thread
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/batch/stop", methods=["POST"])
def api_batch_stop():
    if batch_state.status != "running":
        return jsonify({"error": "No batch run in progress"}), 409
    _batch_cancel_event.set()
    return jsonify({"status": "cancelling"})


@app.route("/api/batch/reset", methods=["POST"])
def api_batch_reset():
    if batch_state.status == "running":
        return jsonify({"error": "Cannot reset while a batch run is in progress"}), 409
    batch_state.reset()
    return jsonify({"status": "idle"})


@app.route("/api/batch/status", methods=["GET"])
def api_batch_status():
    offset = int(request.args.get("offset", 0))
    return jsonify(batch_state.snapshot(offset=offset))


@app.route("/api/batch/logs", methods=["GET"])
def api_batch_logs():
    """SSE stream of batch run log lines.

    Each payload is JSON:
      {"time": "...", "msg": "..."}          -- a log line
      {"done": true, "status": "completed"}  -- final sentinel
    """
    offset = int(request.args.get("offset", 0))

    def _generate():
        sent = offset
        while True:
            snap = batch_state.snapshot(offset=sent)
            for entry in snap["logs"]:
                yield f"data: {json.dumps(entry)}\n\n"
                sent += 1
            if snap["status"] not in ("idle", "running"):
                yield f"data: {json.dumps({'done': True, 'status': snap['status']})}\n\n"
                return
            time.sleep(0.4)

    return Response(
        stream_with_context(_generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/batch/jobs", methods=["GET"])
def api_batch_jobs():
    return jsonify({"jobs": _load_job_history()})


# ---------------------------------------------------------------------------
# Routes: Job Packs
# ---------------------------------------------------------------------------
#
# Job packs live under JOBS_DIR. A valid pack is any sub-directory that
# contains at least agent/instruction.md. Loading copies the pack's agent/
# and input/ trees into the working AGENT_DIR / INPUT_DIR so a Batch run can
# execute without any manual upload.

def _list_jobpacks() -> list:
    packs = []
    if not JOBS_DIR.is_dir():
        return packs
    for candidate in sorted(JOBS_DIR.iterdir()):
        if not candidate.is_dir():
            continue
        instruction = candidate / "agent" / "instruction.md"
        if not instruction.is_file():
            continue
        agent_files = list((candidate / "agent").rglob("*"))
        input_files = list((candidate / "input").rglob("*")) if (candidate / "input").is_dir() else []
        packs.append({
            "name": candidate.name,
            "agent_files": [f.name for f in agent_files if f.is_file()],
            "input_files": [f.name for f in input_files if f.is_file()],
        })
    return packs


@app.route("/api/jobpacks", methods=["GET"])
def api_list_jobpacks():
    return jsonify({"packs": _list_jobpacks(), "jobs_dir": str(JOBS_DIR)})


@app.route("/api/jobpacks/load", methods=["POST"])
def api_load_jobpack():
    """Copy a job pack's agent/ and input/ trees into the working directories.

    Body (JSON):
      pack   -- job pack name (directory name under JOBS_DIR)  [required]
      clear  -- if true (default), clear AGENT_DIR / INPUT_DIR first
      target -- "both" | "agent" | "input"  (default "both")
    """
    if chat_session.status == "running":
        return jsonify({"error": "Cannot load a job pack while a chat turn is running"}), 409
    if batch_state.status == "running":
        return jsonify({"error": "Cannot load a job pack while a batch run is in progress"}), 409

    data = request.get_json(silent=True) or {}
    pack_name = data.get("pack", "").strip()
    if not pack_name:
        return jsonify({"error": "Missing 'pack'"}), 400

    pack_dir = (JOBS_DIR / pack_name).resolve()
    if not str(pack_dir).startswith(str(JOBS_DIR.resolve())):
        return jsonify({"error": "Path traversal denied"}), 400
    if not pack_dir.is_dir():
        return jsonify({"error": f"Job pack not found: {pack_name}"}), 404
    if not (pack_dir / "agent" / "instruction.md").is_file():
        return jsonify({"error": f"Pack missing agent/instruction.md: {pack_name}"}), 400

    clear = data.get("clear", True)
    target = data.get("target", "both")
    copied: dict = {"agent": [], "input": []}

    def _copy_tree(src: Path, dst: Path, label: str) -> None:
        if clear and dst.is_dir():
            for item in dst.iterdir():
                if item.name in HIDDEN_FILES:
                    continue
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
        if not src.is_dir():
            return
        for src_file in src.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(src)
            dst_file = dst / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied[label].append(str(rel))

    if target in ("both", "agent"):
        _copy_tree(pack_dir / "agent", AGENT_DIR, "agent")
    if target in ("both", "input"):
        _copy_tree(pack_dir / "input", INPUT_DIR, "input")

    log.info("Loaded job pack '%s': %d agent, %d input files",
              pack_name, len(copied["agent"]), len(copied["input"]))

    # instruction.md may have just changed — reset the Chat session to match
    if target in ("both", "agent"):
        chat_session.reset(_read_instruction())

    return jsonify({"pack": pack_name, "copied": copied})


# ---------------------------------------------------------------------------
# Routes: Files (unified across agent / input / output)
# ---------------------------------------------------------------------------

@app.route("/api/<any('agent','input','output'):folder>", methods=["GET"])
def api_list_folder(folder):
    return jsonify({"files": _list_dir(FOLDERS[folder])})


@app.route("/api/<any('input','output'):folder>", methods=["DELETE"])
def api_clear_folder(folder):
    base = FOLDERS[folder]
    for item in base.iterdir():
        if item.name in HIDDEN_FILES:
            continue
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)
    log.info("%s cleared", folder)
    return jsonify({"cleared": True})


@app.route("/api/file/<any('agent','input','output'):folder>/<path:filename>", methods=["GET", "PUT", "DELETE"])
def api_file(folder, filename):
    base = FOLDERS[folder]

    if request.method == "GET":
        try:
            target = _safe_path(base, filename)
            if not target.is_file():
                return jsonify({"error": f"File not found: {filename}"}), 404
            return jsonify({
                "name": filename,
                "content": target.read_text(encoding="utf-8", errors="replace"),
            })
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404

    if folder not in EDITABLE_FOLDERS:
        return jsonify({"error": "The output folder is read-only"}), 403

    if request.method == "PUT":
        data = request.get_json(silent=True) or {}
        if "content" not in data:
            return jsonify({"error": "Missing 'content'"}), 400
        content = data["content"]
        safe_name = _sanitise_filename(filename) if folder == "input" else filename
        try:
            target = _safe_path(base, safe_name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        log.info("Written %s/%s (%d chars)", folder, safe_name, len(content))
        result = {"name": safe_name, "size": target.stat().st_size}

        # Saving agent/instruction.md re-seeds the Chat system prompt — reset the session
        if folder == "agent" and safe_name == "instruction.md":
            chat_session.reset(content)
            result.update(chat_session.snapshot())
        return jsonify(result)

    if request.method == "DELETE":
        try:
            target = _safe_path(base, filename)
            if target.exists():
                target.unlink()
            log.info("Deleted %s/%s", folder, filename)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        result = {"deleted": filename}
        if folder == "agent" and filename == "instruction.md":
            # Never leave agent/ without an instruction.md — recreate the default.
            chat_session.reset(_read_instruction())
            result.update(chat_session.snapshot())
        return jsonify(result)


@app.route("/api/file/<any('agent','input'):folder>", methods=["POST"])
def api_create_file(folder):
    data = request.get_json(silent=True) or {}
    name = _sanitise_filename(data.get("name", "").strip())
    if not name:
        return jsonify({"error": "Missing or invalid 'name'"}), 400
    try:
        target = _safe_path(FOLDERS[folder], name)
        if target.exists():
            return jsonify({"error": f"File already exists: {name}"}), 409
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data.get("content", ""), encoding="utf-8")
        log.info("Created %s/%s", folder, name)
        return jsonify({"name": name, "size": target.stat().st_size})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/upload/<any('agent','input'):folder>", methods=["POST"])
def api_upload(folder):
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    safe_name = _sanitise_filename(file.filename)
    try:
        target = _safe_path(FOLDERS[folder], safe_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        file.save(target)
        log.info("Uploaded %s/%s (%d bytes)", folder, safe_name, target.stat().st_size)
        result = {"name": safe_name, "size": target.stat().st_size}
        if folder == "agent" and safe_name == "instruction.md":
            chat_session.reset(_read_instruction())
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


# ---------------------------------------------------------------------------
# Routes: App Logs (SSE)
# ---------------------------------------------------------------------------

@app.route("/api/app-logs", methods=["GET"])
def api_app_logs():
    offset = int(request.args.get("offset", 0))

    def _generate():
        sent = offset
        while True:
            for entry in _app_log_handler.snapshot(offset=sent):
                yield _sse(entry)
                sent += 1
            time.sleep(1.0)

    return Response(
        stream_with_context(_generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Routes: Provider & Model
# ---------------------------------------------------------------------------

_model_cache: dict = {}
_model_cache_lock = threading.Lock()
_MODEL_CACHE_TTL = 300.0


def _fetch_models(provider: str) -> list:
    with _model_cache_lock:
        cached = _model_cache.get(provider)
        if cached and time.monotonic() - cached[0] < _MODEL_CACHE_TTL:
            return cached[1]

    models = []
    try:
        if provider == "anthropic":
            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if key:
                resp = httpx.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                    timeout=10,
                )
                resp.raise_for_status()
                models = [
                    {"id": m["id"], "name": m.get("display_name", m["id"])}
                    for m in resp.json().get("data", [])
                ]
        elif provider == "openai":
            key = os.environ.get("OPENAI_API_KEY", "")
            if key:
                resp = httpx.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=10,
                )
                resp.raise_for_status()
                models = [
                    {"id": m["id"], "name": m["id"]}
                    for m in resp.json().get("data", [])
                    if any(m["id"].startswith(p) for p in ("gpt-", "o1", "o3", "o4"))
                ]
                models.sort(key=lambda m: m["id"])
        elif provider == "openrouter":
            key = os.environ.get("OPENROUTER_API_KEY", "")
            if key:
                resp = httpx.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=15,
                )
                resp.raise_for_status()
                models = [
                    {"id": m["id"], "name": m.get("name", m["id"])}
                    for m in resp.json().get("data", [])
                    if "tools" in (m.get("supported_parameters") or [])
                ]
        elif provider == "openai-compatible":
            base = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1").rstrip("/")
            headers = {}
            key = os.environ.get("OPENAI_API_KEY", "")
            if key:
                headers["Authorization"] = f"Bearer {key}"
            resp = httpx.get(f"{base}/models", headers=headers, timeout=10)
            resp.raise_for_status()
            models = [{"id": m["id"], "name": m["id"]} for m in resp.json().get("data", [])]
    except Exception as exc:
        log.warning("Failed to fetch %s models: %s", provider, exc)

    with _model_cache_lock:
        _model_cache[provider] = (time.monotonic(), models)
    return models


@app.route("/api/providers", methods=["GET"])
def api_providers():
    return jsonify({
        "providers": list(agent_core.PROVIDERS),
        "current": os.environ.get("API_PROVIDER", agent_core.DEFAULT_PROVIDER),
    })


@app.route("/api/provider", methods=["GET"])
def api_get_provider():
    return jsonify({"provider": os.environ.get("API_PROVIDER", agent_core.DEFAULT_PROVIDER)})


@app.route("/api/provider", methods=["POST"])
def api_set_provider():
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "")
    if provider not in agent_core.PROVIDERS:
        return jsonify({"error": f"Unknown provider: {provider}"}), 400
    os.environ["API_PROVIDER"] = provider
    log.info("Provider set to: %s", provider)
    return jsonify({"provider": provider})


@app.route("/api/models", methods=["GET"])
def api_models():
    provider = request.args.get("provider") or os.environ.get("API_PROVIDER", agent_core.DEFAULT_PROVIDER)
    if provider not in agent_core.PROVIDERS:
        return jsonify({"error": f"Unknown provider: {provider}"}), 400
    return jsonify({"models": _fetch_models(provider), "provider": provider})


@app.route("/api/model", methods=["GET"])
def api_get_model():
    provider = os.environ.get("API_PROVIDER", agent_core.DEFAULT_PROVIDER)
    default_model = agent_core.DEFAULT_MODEL_BY_PROVIDER.get(provider, agent_core.DEFAULT_MODEL)
    return jsonify({
        "model": os.environ.get("MODEL", default_model),
        "provider": provider,
    })


@app.route("/api/model", methods=["POST"])
def api_set_model():
    data = request.get_json(silent=True) or {}
    model = data.get("model", "").strip()
    if not model:
        return jsonify({"error": "Missing 'model'"}), 400
    os.environ["MODEL"] = model
    log.info("Model set to: %s", model)
    return jsonify({"model": model})


# ---------------------------------------------------------------------------
# Routes: API Keys
# ---------------------------------------------------------------------------

@app.route("/api/keys", methods=["GET"])
def api_get_keys():
    return jsonify({
        provider: bool(os.environ.get(env_var))
        for provider, env_var in KEY_ENV_VARS.items()
    })


@app.route("/api/keys", methods=["POST"])
def api_set_key():
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "")
    key = data.get("key", "")
    if provider not in KEY_ENV_VARS:
        return jsonify({"error": f"Unknown provider: {provider}"}), 400
    if not key:
        return jsonify({"error": "Missing 'key'"}), 400
    os.environ[KEY_ENV_VARS[provider]] = key
    with _model_cache_lock:
        _model_cache.pop(provider, None)
    log.info("API key set for provider: %s", provider)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Routes: Tools
# ---------------------------------------------------------------------------

@app.route("/api/tools", methods=["GET"])
def api_get_tools():
    disabled = agent_core.disabled_tool_names()
    return jsonify({
        "tools": [
            {**t, "enabled": t["name"] not in disabled}
            for t in agent_core.TOOL_CATALOG
        ]
    })


@app.route("/api/tools", methods=["POST"])
def api_set_tools():
    data = request.get_json(silent=True) or {}
    valid_names = {t["name"] for t in agent_core.TOOL_CATALOG}
    disabled = {name for name, enabled in data.items() if name in valid_names and not enabled}
    os.environ["DISABLED_TOOLS"] = ",".join(sorted(disabled))
    log.info("Disabled tools updated: %s", disabled or "none")
    return api_get_tools()


# ---------------------------------------------------------------------------
# Routes: Settings
# ---------------------------------------------------------------------------

@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify({
        "max_turns": int(os.environ.get("MAX_TURNS", "50") or 50),
        "max_output_tokens": int(
            os.environ.get("MAX_OUTPUT_TOKENS", str(agent_core.DEFAULT_MAX_OUTPUT_TOKENS))
            or agent_core.DEFAULT_MAX_OUTPUT_TOKENS
        ),
        "allow_shell": os.environ.get("ALLOW_SHELL", "true").lower() not in ("0", "false", "no", "off"),
        "shell_timeout": int(os.environ.get("SHELL_TIMEOUT", "60") or 60),
        "openai_base_url": os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1"),
    })


@app.route("/api/settings", methods=["POST"])
def api_set_settings():
    data = request.get_json(silent=True) or {}
    if "max_turns" in data:
        try:
            os.environ["MAX_TURNS"] = str(max(1, int(data["max_turns"])))
        except (TypeError, ValueError):
            return jsonify({"error": "max_turns must be an integer"}), 400
    if "max_output_tokens" in data:
        try:
            os.environ["MAX_OUTPUT_TOKENS"] = str(max(1024, int(data["max_output_tokens"])))
        except (TypeError, ValueError):
            return jsonify({"error": "max_output_tokens must be an integer"}), 400
    if "allow_shell" in data:
        os.environ["ALLOW_SHELL"] = "true" if data["allow_shell"] else "false"
    if "shell_timeout" in data:
        try:
            os.environ["SHELL_TIMEOUT"] = str(max(1, int(data["shell_timeout"])))
        except (TypeError, ValueError):
            return jsonify({"error": "shell_timeout must be an integer"}), 400
    if "openai_base_url" in data:
        os.environ["OPENAI_BASE_URL"] = str(data["openai_base_url"]).strip()
        with _model_cache_lock:
            _model_cache.pop("openai-compatible", None)
    return api_get_settings()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    provider = os.environ.get("API_PROVIDER", agent_core.DEFAULT_PROVIDER)
    default_model = agent_core.DEFAULT_MODEL_BY_PROVIDER.get(provider, agent_core.DEFAULT_MODEL)
    model = os.environ.get("MODEL", default_model)

    print()
    print("  Pydantic Assistant - Web UI")
    print("  ----------------------------")
    print(f"  URL      : http://localhost:{PORT}")
    print(f"  Provider : {provider}")
    print(f"  Model    : {model}")
    print(f"  Agent    : {AGENT_DIR}")
    print(f"  Input    : {INPUT_DIR}")
    print(f"  Output   : {OUTPUT_DIR}")
    print(f"  Jobs     : {JOBS_DIR}{'' if JOBS_DIR.is_dir() else ' (not found)'}")
    print("  ----------------------------")
    missing = [
        env for prov, env in KEY_ENV_VARS.items()
        if prov not in NO_KEY_PROVIDERS and not os.environ.get(env)
    ]
    if len(missing) >= len(KEY_ENV_VARS) - len(NO_KEY_PROVIDERS):
        print("  NOTE: no API key set — add one via the web UI or environment.")
    print()

    log.info("Pydantic Assistant starting on %s:%d", HOST, PORT)
    log.info("Provider=%s  Model=%s", provider, model)
    log.info("Agent=%s  Input=%s  Output=%s", AGENT_DIR, INPUT_DIR, OUTPUT_DIR)

    instruction = _read_instruction()
    chat_session.reset(instruction)
    if instruction:
        log.info("instruction.md loaded (%d chars)", len(instruction))
    else:
        log.info("No instruction.md yet — create one via the agent/ panel, or load a Job Pack")

    app.run(host=HOST, port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
