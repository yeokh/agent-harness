#!/usr/bin/env python3
"""
ADK Assistant — FastAPI Web Server

Serves one UI that drives two execution modes against the same agent/ /
input/ / output/ folders and the same scoped tool set, both running on the
Google ADK Runner (see adk_core.py):

    Chat  — interactive, multi-turn conversation (POST /api/chat, SSE)
    Batch — one-shot autonomous run (POST /api/batch/run, SSE log stream)

A Job Pack loader (GET /api/jobpacks, POST /api/jobpacks/load) can stage a
pack's agent/ + input/ files from the JOBS_DIR library before a Batch run.

File access is unified across both modes: any file in agent/, input/, or
output/ can be viewed (GET /api/file/<folder>/<name>); only agent/ and
input/ files are editable (PUT/POST/DELETE) — output/ is read-only.

Environment variables:
    API_PROVIDER          openai-compatible | gemini | vertex | anthropic | openai | openrouter
    MODEL                 model id (default varies by provider)
    GOOGLE_API_KEY        Gemini API key (provider "gemini"; GEMINI_API_KEY also accepted)
    GOOGLE_CLOUD_PROJECT  GCP project for provider "vertex" (uses Application Default Credentials)
    GOOGLE_CLOUD_LOCATION Vertex AI region (default us-central1)
    ANTHROPIC_API_KEY     Anthropic provider key
    OPENAI_API_KEY        OpenAI provider key
    OPENAI_COMPATIBLE_API_KEY  optional bearer token for the openai-compatible endpoint (separate from OPENAI_API_KEY)
    OPENROUTER_API_KEY    OpenRouter provider key
    OPENAI_BASE_URL       OpenAI-compatible endpoint (default http://localhost:11434/v1)
    MAX_TURNS             max model calls per Chat turn or Batch run (default 50)
    MAX_OUTPUT_TOKENS     token budget per model response (default 16384)
    ALLOW_SHELL           set false to disable run_command entirely (default true)
    SHELL_TIMEOUT         max seconds per shell command (default 60)
    SHELL_GUARD           set off to disable the destructive-command deny-list (default on)
    LLM_TIMEOUT / LLM_RETRIES  per-request timeout seconds (default 120) / retries (default 1) for LiteLLM providers
    ALLOW_PRIVATE_FETCH   set true to let web_fetch reach private/loopback addresses (default false)
    ALLOW_MCP_STDIO       allow stdio MCP servers from agent/mcp.json (default: follows ALLOW_SHELL)
    DISABLED_TOOLS        comma-separated tool names to remove from the agent
    OTEL_EXPORTER_OTLP_ENDPOINT  enable OpenTelemetry export (needs the `otel` extra)
    AGENT_DIR / INPUT_DIR / OUTPUT_DIR   folder overrides (default ./agent, ./input, ./output)
    JOBS_DIR              job-pack library used by the Batch tab's Load button (default ./sample-jobs)
    PORT / HOST           web server bind (default 8081 / 0.0.0.0)
"""

import asyncio
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import adk_core

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
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
README_FILE = PROJECT_ROOT / "README.md"
INDEX_FILE = PROJECT_ROOT / "templates" / "index.html"
JOB_HISTORY_FILE = Path(os.environ.get("JOB_HISTORY_FILE", PROJECT_ROOT / ".job_history.json"))
JOB_HISTORY_MAX = 20
HIDDEN_FILES = {".job_history.json", ".gitkeep"}

# Map each provider to the env var name that holds its API key.
# openai-compatible and vertex need no key (local endpoint / Application Default Credentials).
KEY_ENV_VARS = {
    "gemini":            "GOOGLE_API_KEY",
    "anthropic":         "ANTHROPIC_API_KEY",
    "openai":            "OPENAI_API_KEY",
    "openrouter":        "OPENROUTER_API_KEY",
    "openai-compatible": "OPENAI_COMPATIBLE_API_KEY",
}
NO_KEY_PROVIDERS = {"openai-compatible", "vertex"}

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

log = logging.getLogger("web_app")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _err(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def _json(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse_response(gen) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream", headers=SSE_HEADERS)


# Keep references to background tasks so they are not garbage-collected mid-run.
_background: set = set()


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


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
    """Conversation state: UI display messages plus the backing ADK session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.instruction: str = ""
        self.adk: adk_core.AdkSession | None = None
        self.display_messages: list = []
        self.status: str = "idle"
        self.cancel_event = threading.Event()

    def reset(self, instruction: str) -> None:
        with self._lock:
            self.status = "idle"
            self.instruction = instruction
            self.adk = adk_core.AdkSession()  # fresh ADK session == cleared history
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
            "llm_calls": stats.get("llm_calls"),
            "total_cost_usd": stats.get("total_cost_usd"),
            "total_input_tokens": stats.get("total_input_tokens"),
            "total_output_tokens": stats.get("total_output_tokens"),
            "tool_counts": stats.get("tool_counts"),
            "guardrail_blocks": stats.get("guardrail_blocks"),
            "injection_flags": stats.get("injection_flags"),
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
    entry = {
        "run_id": snap.get("started_at"),
        "status": snap.get("status"),
        "provider": adk_core.current_provider(),
        "model": adk_core.current_model(),
        "duration_seconds": metrics.get("duration_seconds"),
        "total_turns": metrics.get("total_turns"),
        "llm_calls": metrics.get("llm_calls"),
        "total_cost_usd": metrics.get("total_cost_usd"),
        "total_input_tokens": metrics.get("total_input_tokens"),
        "total_output_tokens": metrics.get("total_output_tokens"),
        "guardrail_blocks": metrics.get("guardrail_blocks"),
        "injection_flags": metrics.get("injection_flags"),
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
    base_r = base.resolve()
    target = (base_r / rel).resolve()
    if target != base_r and base_r not in target.parents:
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


def _clear_dir(base: Path) -> None:
    for item in base.iterdir():
        if item.name in HIDDEN_FILES:
            continue
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)


# ---------------------------------------------------------------------------
# Chat turn / Batch run tasks (run on the server's event loop)
# ---------------------------------------------------------------------------

async def _chat_turn(user_message: str, instruction: str, event_queue: asyncio.Queue) -> None:
    ai_text_parts: list[str] = []
    tool_events: list[dict] = []

    def on_event(ev: dict) -> None:
        if ev["type"] == "delta":
            ai_text_parts.append(ev["content"])
        elif ev["type"] in ("tool_use", "tool_result"):
            tool_events.append(ev)
        event_queue.put_nowait(ev)

    try:
        stats = await adk_core.run_chat_turn(
            user_message=user_message,
            session=chat_session.adk,
            agent_dir=AGENT_DIR,
            input_dir=INPUT_DIR,
            output_dir=OUTPUT_DIR,
            instruction=instruction,
            event_callback=on_event,
            cancel_event=chat_session.cancel_event,
        )
        ai_msg = {
            "id": str(uuid.uuid4()),
            "role": "ai",
            "type": "text",
            "content": "".join(ai_text_parts),
            "tool_events": tool_events,
            "usage": stats,
            "timestamp": _now(),
        }
        chat_session.add_display_message(ai_msg)
        event_queue.put_nowait({"type": "done", "message": ai_msg})
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
        event_queue.put_nowait({"type": "error", "content": str(exc), "message": err_msg})
    finally:
        chat_session.set_status("idle")


async def _batch_run() -> None:
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

            await adk_core.run_batch(
                AGENT_DIR, INPUT_DIR, OUTPUT_DIR, instruction,
                log_callback=_log, stats_out=stats_out, cancel_event=_batch_cancel_event,
            )

        batch_state.finish(stats=stats_out)
        batch_state.add_log("=== Batch run completed successfully ===")
    except RuntimeError as exc:
        batch_state.finish(str(exc), stats=stats_out)
        batch_state.add_log(f"FATAL: {exc}")
    except Exception as exc:
        log.exception("Batch run failed")
        batch_state.finish(f"Unexpected error: {exc}", stats=stats_out)
        batch_state.add_log(f"FATAL: Unexpected error: {exc}")

    _append_job_history(batch_state.snapshot())


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Pre-import the heavy LLM libraries off the event loop so the first run is not slow.
    _spawn(asyncio.to_thread(_prewarm))
    yield


def _prewarm() -> None:
    try:
        import google.adk.runners  # noqa: F401
        import litellm  # noqa: F401
    except Exception:
        pass


app = FastAPI(title="ADK Assistant", lifespan=lifespan, docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# Routes: Pages
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(INDEX_FILE, media_type="text/html")


@app.get("/api/readme")
async def api_readme():
    if not README_FILE.is_file():
        return {"found": False}
    content = README_FILE.read_text(encoding="utf-8", errors="replace")
    return {"found": True, "content": content, "size": README_FILE.stat().st_size}


# ---------------------------------------------------------------------------
# Routes: Chat session
# ---------------------------------------------------------------------------

@app.get("/api/session")
async def api_session():
    return chat_session.snapshot()


@app.post("/api/chat/reset")
async def api_chat_reset():
    if chat_session.status == "running":
        return _err("Cannot reset while a turn is running", 409)
    chat_session.reset(_read_instruction())
    log.info("Chat session reset")
    return chat_session.snapshot()


@app.post("/api/chat/cancel")
async def api_chat_cancel():
    if chat_session.status != "running":
        return _err("No turn in progress", 409)
    chat_session.cancel_event.set()
    return {"status": "cancelling"}


# ---------------------------------------------------------------------------
# Routes: Chat (SSE)
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def api_chat(request: Request):
    data = await _json(request)
    message = str(data.get("message", "")).strip()

    if not message:
        return _err("Empty message", 400)
    if chat_session.status == "running":
        return _err("A turn is already in progress", 409)

    # /skills command — push all skill .md files into the conversation context
    if message.lower() in ("/skills", "/skill"):
        skills_text, skill_files = _load_skills()
        if not skills_text:
            content, skill_files = "No skill files found in the agent folder.", []
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
            await chat_session.adk.add_user_context(
                "The following skill reference documents are now available:\n\n" + skills_text
            )

        async def _skills_stream():
            yield _sse({"type": "done", "message": display_msg})

        return _sse_response(_skills_stream())

    # Regular message
    user_msg = {
        "id": str(uuid.uuid4()),
        "role": "you",
        "type": "user",
        "content": message,
        "timestamp": _now(),
    }
    chat_session.add_display_message(user_msg)
    chat_session.set_status("running")
    chat_session.cancel_event.clear()

    event_q: asyncio.Queue = asyncio.Queue()
    task = _spawn(_chat_turn(message, chat_session.get_instruction(), event_q))

    async def _generate():
        yield _sse({"type": "user_message", "message": user_msg})
        while True:
            try:
                ev = await asyncio.wait_for(event_q.get(), timeout=15)
            except asyncio.TimeoutError:
                if task.done() and event_q.empty():
                    return
                yield _sse({"type": "ping"})
                continue
            yield _sse(ev)
            if ev.get("type") in ("done", "error"):
                return

    return _sse_response(_generate())


# ---------------------------------------------------------------------------
# Routes: Batch control
# ---------------------------------------------------------------------------

def _provider_config_error(provider: str) -> str | None:
    if provider == "vertex":
        if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
            return "No project configured for vertex. Set GOOGLE_CLOUD_PROJECT (and Application Default Credentials)."
        return None
    if provider in NO_KEY_PROVIDERS:
        return None
    env_var = KEY_ENV_VARS.get(provider)
    if env_var and not (os.environ.get(env_var) or (provider == "gemini" and os.environ.get("GEMINI_API_KEY"))):
        return f"No API key configured for {provider}. Set {env_var}."
    return None


@app.post("/api/batch/run")
async def api_batch_run():
    if batch_state.status == "running":
        return _err("A batch run is already in progress", 409)
    if not INSTRUCTION_FILE.is_file():
        return _err("instruction.md not found in agent/ — create it first", 400)
    problem = _provider_config_error(adk_core.current_provider())
    if problem:
        return _err(problem, 400)

    batch_state.start()  # claim the slot synchronously so a second click sees "running"
    _spawn(_batch_run())
    return {"status": "started"}


@app.post("/api/batch/stop")
async def api_batch_stop():
    if batch_state.status != "running":
        return _err("No batch run in progress", 409)
    _batch_cancel_event.set()
    return {"status": "cancelling"}


@app.post("/api/batch/reset")
async def api_batch_reset():
    if batch_state.status == "running":
        return _err("Cannot reset while a batch run is in progress", 409)
    batch_state.reset()
    return {"status": "idle"}


@app.get("/api/batch/status")
async def api_batch_status(offset: int = 0):
    return batch_state.snapshot(offset=offset)


@app.get("/api/batch/logs")
async def api_batch_logs(offset: int = 0):
    """SSE stream of batch run log lines.

    Each payload is JSON:
      {"time": "...", "msg": "..."}          -- a log line
      {"done": true, "status": "completed"}  -- final sentinel
    """
    async def _generate():
        sent = offset
        while True:
            snap = batch_state.snapshot(offset=sent)
            for entry in snap["logs"]:
                yield f"data: {json.dumps(entry)}\n\n"
                sent += 1
            if snap["status"] not in ("idle", "running"):
                yield f"data: {json.dumps({'done': True, 'status': snap['status']})}\n\n"
                return
            await asyncio.sleep(0.4)

    return _sse_response(_generate())


@app.get("/api/batch/jobs")
async def api_batch_jobs():
    return {"jobs": _load_job_history()}


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
        if not (candidate / "agent" / "instruction.md").is_file():
            continue
        agent_files = list((candidate / "agent").rglob("*"))
        input_files = list((candidate / "input").rglob("*")) if (candidate / "input").is_dir() else []
        packs.append({
            "name": candidate.name,
            "agent_files": [f.name for f in agent_files if f.is_file()],
            "input_files": [f.name for f in input_files if f.is_file()],
        })
    return packs


@app.get("/api/jobpacks")
async def api_list_jobpacks():
    return {"packs": _list_jobpacks(), "jobs_dir": str(JOBS_DIR)}


@app.post("/api/jobpacks/load")
async def api_load_jobpack(request: Request):
    """Copy a job pack's agent/ and input/ trees into the working directories.

    Body (JSON):
      pack   -- job pack name (directory name under JOBS_DIR)  [required]
      clear  -- if true (default), clear AGENT_DIR / INPUT_DIR first
      target -- "both" | "agent" | "input"  (default "both")
    """
    if chat_session.status == "running":
        return _err("Cannot load a job pack while a chat turn is running", 409)
    if batch_state.status == "running":
        return _err("Cannot load a job pack while a batch run is in progress", 409)

    data = await _json(request)
    pack_name = str(data.get("pack", "")).strip()
    if not pack_name:
        return _err("Missing 'pack'", 400)

    jobs_r = JOBS_DIR.resolve()
    pack_dir = (jobs_r / pack_name).resolve()
    if jobs_r not in pack_dir.parents:
        return _err("Path traversal denied", 400)
    if not pack_dir.is_dir():
        return _err(f"Job pack not found: {pack_name}", 404)
    if not (pack_dir / "agent" / "instruction.md").is_file():
        return _err(f"Pack missing agent/instruction.md: {pack_name}", 400)

    clear = data.get("clear", True)
    target = data.get("target", "both")
    copied: dict = {"agent": [], "input": []}

    def _copy_tree(src: Path, dst: Path, label: str) -> None:
        if clear and dst.is_dir():
            _clear_dir(dst)
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

    return {"pack": pack_name, "copied": copied}


# ---------------------------------------------------------------------------
# Routes: Files (unified across agent / input / output)
# ---------------------------------------------------------------------------

def _register_folder_routes(folder: str) -> None:
    # Registered per folder (not as /api/{folder}) so they never shadow other /api/<name> routes.
    async def list_folder():
        return {"files": _list_dir(FOLDERS[folder])}

    async def clear_folder():
        if folder not in ("input", "output"):
            return _err("The agent folder cannot be cleared", 405)
        _clear_dir(FOLDERS[folder])
        log.info("%s cleared", folder)
        return {"cleared": True}

    app.add_api_route(f"/api/{folder}", list_folder, methods=["GET"])
    app.add_api_route(f"/api/{folder}", clear_folder, methods=["DELETE"])


for _folder in FOLDERS:
    _register_folder_routes(_folder)


@app.api_route("/api/file/{folder}/{filename:path}", methods=["GET", "PUT", "DELETE"])
async def api_file(folder: str, filename: str, request: Request):
    if folder not in FOLDERS:
        return _err("Not found", 404)
    base = FOLDERS[folder]

    if request.method == "GET":
        try:
            target = _safe_path(base, filename)
            if not target.is_file():
                return _err(f"File not found: {filename}", 404)
            return {"name": filename, "content": target.read_text(encoding="utf-8", errors="replace")}
        except ValueError as exc:
            return _err(str(exc), 404)

    if folder not in EDITABLE_FOLDERS:
        return _err("The output folder is read-only", 403)

    if request.method == "PUT":
        data = await _json(request)
        if "content" not in data:
            return _err("Missing 'content'", 400)
        content = str(data["content"])
        safe_name = _sanitise_filename(filename) if folder == "input" else filename
        try:
            target = _safe_path(base, safe_name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except ValueError as exc:
            return _err(str(exc), 400)

        log.info("Written %s/%s (%d chars)", folder, safe_name, len(content))
        result = {"name": safe_name, "size": target.stat().st_size}

        # Saving agent/instruction.md re-seeds the Chat system prompt — reset the session
        if folder == "agent" and safe_name == "instruction.md":
            chat_session.reset(content)
            result.update(chat_session.snapshot())
        return result

    # DELETE
    try:
        target = _safe_path(base, filename)
        if target.is_file():
            target.unlink()
        log.info("Deleted %s/%s", folder, filename)
    except ValueError as exc:
        return _err(str(exc), 400)

    result = {"deleted": filename}
    if folder == "agent" and filename == "instruction.md":
        # Never leave agent/ without an instruction.md — recreate the default.
        chat_session.reset(_read_instruction())
        result.update(chat_session.snapshot())
    return result


@app.post("/api/file/{folder}")
async def api_create_file(folder: str, request: Request):
    if folder not in EDITABLE_FOLDERS:
        return _err("Not found" if folder not in FOLDERS else "The output folder is read-only",
                    404 if folder not in FOLDERS else 403)
    data = await _json(request)
    name = _sanitise_filename(str(data.get("name", "")).strip())
    if not name:
        return _err("Missing or invalid 'name'", 400)
    try:
        target = _safe_path(FOLDERS[folder], name)
        if target.exists():
            return _err(f"File already exists: {name}", 409)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(data.get("content", "")), encoding="utf-8")
        log.info("Created %s/%s", folder, name)
        return {"name": name, "size": target.stat().st_size}
    except ValueError as exc:
        return _err(str(exc), 400)


@app.post("/api/upload/{folder}")
async def api_upload(folder: str, request: Request):
    if folder not in EDITABLE_FOLDERS:
        return _err("Not found" if folder not in FOLDERS else "The output folder is read-only",
                    404 if folder not in FOLDERS else 403)
    form = await request.form()
    file = form.get("file")
    if file is None or not hasattr(file, "filename"):
        return _err("No file part in request", 400)
    if not file.filename:
        return _err("Empty filename", 400)
    safe_name = _sanitise_filename(file.filename)
    try:
        target = _safe_path(FOLDERS[folder], safe_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(await file.read())
        log.info("Uploaded %s/%s (%d bytes)", folder, safe_name, target.stat().st_size)
        result = {"name": safe_name, "size": target.stat().st_size}
        if folder == "agent" and safe_name == "instruction.md":
            chat_session.reset(_read_instruction())
        return result
    except ValueError as exc:
        return _err(str(exc), 400)


# ---------------------------------------------------------------------------
# Routes: App Logs (SSE)
# ---------------------------------------------------------------------------

@app.get("/api/app-logs")
async def api_app_logs(offset: int = 0):
    async def _generate():
        sent = offset
        while True:
            for entry in _app_log_handler.snapshot(offset=sent):
                yield _sse(entry)
                sent += 1
            await asyncio.sleep(1.0)

    return _sse_response(_generate())


# ---------------------------------------------------------------------------
# Routes: Provider & Model
# ---------------------------------------------------------------------------

_model_cache: dict = {}
_MODEL_CACHE_TTL = 300.0

_VERTEX_MODELS = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
# OpenAI's /v1/models also lists non-chat models; hide only those that clearly cannot chat.
_NON_CHAT_MARKERS = ("embedding", "whisper", "tts", "dall-e", "moderation", "transcribe", "image", "realtime", "audio", "davinci", "babbage")


async def _get_json(client: httpx.AsyncClient, url: str, **kw) -> dict:
    resp = await client.get(url, **kw)
    resp.raise_for_status()
    return resp.json()


async def _fetch_models_uncached(provider: str) -> list:
    """List every model the provider's models endpoint returns (following pagination)."""
    async with httpx.AsyncClient(timeout=20) as client:
        if provider == "gemini":
            key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
            if not key:
                return []
            out, token = [], None
            while True:
                params = {"pageSize": 1000, **({"pageToken": token} if token else {})}
                data = await _get_json(client, "https://generativelanguage.googleapis.com/v1beta/models",
                                       params=params, headers={"x-goog-api-key": key})
                out += [
                    {"id": m["name"].removeprefix("models/"), "name": m.get("displayName") or m["name"]}
                    for m in data.get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                ]
                token = data.get("nextPageToken")
                if not token:
                    return out

        if provider == "vertex":
            try:  # needs Application Default Credentials + GOOGLE_CLOUD_PROJECT
                def _list():
                    from google import genai
                    c = genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                                     location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
                    return [m.name.split("/")[-1] for m in c.models.list()
                            if "generateContent" in (m.supported_actions or [])]
                ids = await asyncio.to_thread(_list)
                if ids:
                    return [{"id": i, "name": i} for i in ids]
            except Exception as exc:
                log.info("Vertex model listing unavailable, using defaults: %s", exc)
            return [{"id": m, "name": m} for m in _VERTEX_MODELS]

        if provider == "anthropic":
            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                return []
            out, after = [], None
            while True:
                params = {"limit": 1000, **({"after_id": after} if after else {})}
                data = await _get_json(client, "https://api.anthropic.com/v1/models", params=params,
                                       headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
                out += [{"id": m["id"], "name": m.get("display_name", m["id"])} for m in data.get("data", [])]
                if not data.get("has_more") or not data.get("last_id"):
                    return out
                after = data["last_id"]

        if provider == "openai":
            key = os.environ.get("OPENAI_API_KEY", "")
            if not key:
                return []
            data = await _get_json(client, "https://api.openai.com/v1/models",
                                   headers={"Authorization": f"Bearer {key}"})
            return sorted(
                ({"id": m["id"], "name": m["id"]} for m in data.get("data", [])
                 if not any(x in m["id"].lower() for x in _NON_CHAT_MARKERS)),
                key=lambda m: m["id"],
            )

        if provider == "openrouter":
            key = os.environ.get("OPENROUTER_API_KEY", "")
            if not key:
                return []
            data = await _get_json(client, "https://openrouter.ai/api/v1/models",
                                   headers={"Authorization": f"Bearer {key}"})
            return [{"id": m["id"], "name": m.get("name", m["id"])} for m in data.get("data", [])]

        if provider == "openai-compatible":
            base = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1").rstrip("/")
            ckey = os.environ.get("OPENAI_COMPATIBLE_API_KEY", "")
            headers = {"Authorization": f"Bearer {ckey}"} if ckey else {}
            data = await _get_json(client, f"{base}/models", headers=headers)
            return [{"id": m["id"], "name": m["id"]} for m in data.get("data", [])]
    return []


async def _fetch_models(provider: str) -> list:
    cached = _model_cache.get(provider)
    if cached and time.monotonic() - cached[0] < _MODEL_CACHE_TTL:
        return cached[1]
    try:
        models = await _fetch_models_uncached(provider)
    except Exception as exc:
        log.warning("Failed to fetch %s models: %s", provider, exc)
        return []  # failures are not cached, so the next selection retries
    if models:
        _model_cache[provider] = (time.monotonic(), models)
    return models


@app.get("/api/providers")
async def api_providers():
    return {"providers": list(adk_core.PROVIDERS), "current": adk_core.current_provider()}


@app.get("/api/provider")
async def api_get_provider():
    return {"provider": adk_core.current_provider()}


@app.post("/api/provider")
async def api_set_provider(request: Request):
    provider = (await _json(request)).get("provider", "")
    if provider not in adk_core.PROVIDERS:
        return _err(f"Unknown provider: {provider}", 400)
    os.environ["API_PROVIDER"] = provider
    # A MODEL left over from another provider would be invalid here.
    os.environ.pop("MODEL", None)
    log.info("Provider set to: %s", provider)
    return {"provider": provider}


@app.get("/api/models")
async def api_models(provider: str = ""):
    provider = provider or adk_core.current_provider()
    if provider not in adk_core.PROVIDERS:
        return _err(f"Unknown provider: {provider}", 400)
    return {"models": await _fetch_models(provider), "provider": provider}


@app.get("/api/model")
async def api_get_model():
    provider = adk_core.current_provider()
    return {"model": adk_core.current_model(provider), "provider": provider}


@app.post("/api/model")
async def api_set_model(request: Request):
    model = str((await _json(request)).get("model", "")).strip()
    if not model:
        return _err("Missing 'model'", 400)
    os.environ["MODEL"] = model
    log.info("Model set to: %s", model)
    return {"model": model}


# ---------------------------------------------------------------------------
# Routes: API Keys
# ---------------------------------------------------------------------------

@app.get("/api/keys")
async def api_get_keys():
    return {
        provider: bool(os.environ.get(env_var) or (provider == "gemini" and os.environ.get("GEMINI_API_KEY")))
        for provider, env_var in KEY_ENV_VARS.items()
    }


@app.post("/api/keys")
async def api_set_key(request: Request):
    data = await _json(request)
    provider = data.get("provider", "")
    key = data.get("key", "")
    if provider not in KEY_ENV_VARS:
        return _err(f"Unknown provider: {provider}", 400)
    if not key:
        return _err("Missing 'key'", 400)
    os.environ[KEY_ENV_VARS[provider]] = key
    _model_cache.pop(provider, None)
    log.info("API key set for provider: %s", provider)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Routes: Tools
# ---------------------------------------------------------------------------

@app.get("/api/tools")
async def api_get_tools():
    disabled = adk_core.disabled_tool_names()
    return {"tools": [{**t, "enabled": t["name"] not in disabled} for t in adk_core.TOOL_CATALOG]}


@app.post("/api/tools")
async def api_set_tools(request: Request):
    data = await _json(request)
    valid_names = {t["name"] for t in adk_core.TOOL_CATALOG}
    disabled = {name for name, enabled in data.items() if name in valid_names and not enabled}
    os.environ["DISABLED_TOOLS"] = ",".join(sorted(disabled))
    log.info("Disabled tools updated: %s", disabled or "none")
    return await api_get_tools()


# ---------------------------------------------------------------------------
# Routes: Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
async def api_get_settings():
    return {
        "max_turns": adk_core._env_int("MAX_TURNS", 50),
        "max_output_tokens": adk_core.max_output_tokens(),
        "allow_shell": adk_core.allow_shell(),
        "shell_timeout": adk_core.shell_timeout(),
        "openai_base_url": os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1"),
    }


@app.post("/api/settings")
async def api_set_settings(request: Request):
    data = await _json(request)
    for key, env, minimum in (
        ("max_turns", "MAX_TURNS", 1),
        ("max_output_tokens", "MAX_OUTPUT_TOKENS", 1024),
        ("shell_timeout", "SHELL_TIMEOUT", 1),
    ):
        if key in data:
            try:
                os.environ[env] = str(max(minimum, int(data[key])))
            except (TypeError, ValueError):
                return _err(f"{key} must be an integer", 400)
    if "allow_shell" in data:
        os.environ["ALLOW_SHELL"] = "true" if data["allow_shell"] else "false"
    if "openai_base_url" in data:
        os.environ["OPENAI_BASE_URL"] = str(data["openai_base_url"]).strip()
        _model_cache.pop("openai-compatible", None)
    return await api_get_settings()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    # basicConfig is a no-op if handlers exist; make sure the capture handler sees INFO.
    logging.getLogger().setLevel(logging.INFO)

    provider = adk_core.current_provider()
    model = adk_core.current_model(provider)

    print()
    print("  ADK Assistant - Web UI")
    print("  ----------------------------")
    print(f"  URL      : http://localhost:{PORT}")
    print(f"  Provider : {provider}")
    print(f"  Model    : {model}")
    print(f"  Agent    : {AGENT_DIR}")
    print(f"  Input    : {INPUT_DIR}")
    print(f"  Output   : {OUTPUT_DIR}")
    print(f"  Jobs     : {JOBS_DIR}{'' if JOBS_DIR.is_dir() else ' (not found)'}")
    print("  ----------------------------")
    if provider not in NO_KEY_PROVIDERS and _provider_config_error(provider):
        print(f"  NOTE: {_provider_config_error(provider)} (or add one via the web UI)")
    print()

    log.info("ADK Assistant starting on %s:%d", HOST, PORT)
    log.info("Provider=%s  Model=%s", provider, model)
    log.info("Agent=%s  Input=%s  Output=%s", AGENT_DIR, INPUT_DIR, OUTPUT_DIR)
    adk_core.setup_telemetry()

    instruction = _read_instruction()
    chat_session.reset(instruction)
    if instruction:
        log.info("instruction.md loaded (%d chars)", len(instruction))
    else:
        log.info("No instruction.md yet — create one via the agent/ panel, or load a Job Pack")

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
