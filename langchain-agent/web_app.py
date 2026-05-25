#!/usr/bin/env python3
"""
LangChain Agent — Web Application
==================================
Flask web UI that drives the agent harness defined in agent_harness.py.
Same inbox/outbox pattern as the claude-agent project.

Endpoints:
  GET  /                       -> web UI (index.html)
  GET  /api/inbox              -> list inbox files
  GET  /api/outbox             -> list outbox files
  GET  /api/file/inbox/<path>  -> read an inbox file
  GET  /api/file/outbox/<path> -> read an outbox file
  POST /api/upload             -> upload a file to the inbox
  DEL  /api/inbox/<path>       -> delete an inbox file
  DEL  /api/inbox              -> clear all inbox files
  DEL  /api/outbox             -> clear all outbox files
  GET  /api/model              -> get current model
  POST /api/model              -> set active model (any model string accepted)
  POST /api/agent/run          -> start an agent run
  POST /api/agent/reset        -> reset agent state to idle
  GET  /api/agent/status       -> current status + log snapshot
  GET  /api/agent/logs         -> SSE stream of real-time log entries

Environment variables:
  ANTHROPIC_API_KEY    API key for Anthropic (e.g. anthropic:claude-sonnet-4-6)
  OPENROUTER_API_KEY   API key for OpenRouter (any model via openrouter.ai)
  DEFAULT_MODEL        default: anthropic:claude-sonnet-4-6
  INBOX_DIR            default: ./inbox
  OUTBOX_DIR           default: ./outbox
  PORT                 default: 8080
  HOST                 default: 0.0.0.0

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
import re
import shutil
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from agent_harness import run_agent

# ─── Configuration ─────────────────────────────────────────────────────────────
INBOX_DIR  = Path(os.environ.get("INBOX_DIR",  "./inbox")).resolve()
OUTBOX_DIR = Path(os.environ.get("OUTBOX_DIR", "./outbox")).resolve()
PORT       = int(os.environ.get("PORT", "8080"))
HOST       = os.environ.get("HOST", "0.0.0.0")

INBOX_DIR.mkdir(parents=True, exist_ok=True)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
log = logging.getLogger("web_app")

_current_model: str = os.environ.get("DEFAULT_MODEL", "anthropic:claude-sonnet-4-6")

# ─── Model list cache ──────────────────────────────────────────────────────────
_models_cache: list[str] = []
_models_cache_ts: float  = 0.0
_MODELS_TTL: int         = 300  # seconds


def _fetch_anthropic_models() -> list[str]:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return []
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return [f"anthropic:{m['id']}" for m in data.get("data", [])]
    except Exception as exc:
        log.warning("Failed to fetch Anthropic models: %s", exc)
        return []


def _fetch_openrouter_models() -> list[str]:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return []
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return [f"openrouter:{m['id']}" for m in data.get("data", [])]
    except Exception as exc:
        log.warning("Failed to fetch OpenRouter models: %s", exc)
        return []


def _get_models(force: bool = False) -> list[str]:
    global _models_cache, _models_cache_ts
    if not force and _models_cache and (time.time() - _models_cache_ts) < _MODELS_TTL:
        return _models_cache
    models: list[str] = []
    models.extend(_fetch_anthropic_models())
    models.extend(_fetch_openrouter_models())
    if models:
        _models_cache    = models
        _models_cache_ts = time.time()
    return models or _models_cache


# ─── Agent State ────────────────────────────────────────────────────────────────
class AgentState:
    """Thread-safe container for one agent run's state and log history."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.status: str = "idle"
        self.logs: deque[dict] = deque(maxlen=2000)
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.error: str | None = None

    def start(self) -> None:
        with self._lock:
            self.status      = "running"
            self.logs.clear()
            self.started_at  = _now()
            self.finished_at = None
            self.error       = None

    def finish(self, error: str | None = None) -> None:
        with self._lock:
            self.status      = "error" if error else "completed"
            self.finished_at = _now()
            self.error       = error

    def reset(self) -> None:
        with self._lock:
            self.status      = "idle"
            self.logs.clear()
            self.started_at  = None
            self.finished_at = None
            self.error       = None

    def add_log(self, message: str) -> None:
        with self._lock:
            self.logs.append({"time": _now(), "msg": message})

    def snapshot(self, offset: int = 0) -> dict:
        with self._lock:
            return {
                "status":      self.status,
                "started_at":  self.started_at,
                "finished_at": self.finished_at,
                "error":       self.error,
                "log_count":   len(self.logs),
                "logs":        list(self.logs)[offset:],
            }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


state = AgentState()


# ─── Agent thread ──────────────────────────────────────────────────────────────
def _agent_thread(model_name: str) -> None:
    """Background thread: delegate to agent_harness.run_agent and stream logs."""
    state.start()

    try:
        run_agent(INBOX_DIR, OUTBOX_DIR, model_name, state.add_log)

        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        log_path = OUTBOX_DIR / "agent.log"
        with log_path.open("w", encoding="utf-8") as log_fh:
            with state._lock:
                for entry in state.logs:
                    log_fh.write(f"{entry['time']}  {entry['msg']}\n")

        state.finish()

    except ImportError as exc:
        msg = (
            f"Import error: {exc}. "
            "Install dependencies: pip install deepagents langchain-anthropic langchain-openai"
        )
        state.add_log(f"[error] {msg}")
        state.finish(error=str(exc))
    except FileNotFoundError as exc:
        state.add_log(f"[error] {exc}")
        state.finish(error=str(exc))
    except Exception as exc:
        state.add_log(f"FATAL: {exc}")
        state.finish(error=str(exc))


# ─── Helpers ────────────────────────────────────────────────────────────────────
def _safe_path(base: Path, rel: str) -> Path:
    target = (base / rel).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise ValueError(f"Path traversal denied: {rel}")
    return target


def _list_dir(directory: Path) -> list[dict]:
    result = []
    if not directory.exists():
        return result
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            stat = path.stat()
            result.append({
                "name":     str(path.relative_to(directory)),
                "size":     stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
    return result


def _sanitise_filename(raw: str) -> str:
    name = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    return re.sub(r"[^\w.\-/]", "_", name) or "upload"


# ─── Routes: Pages ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ─── Routes: File Browser API ──────────────────────────────────────────────────
@app.route("/api/inbox", methods=["GET"])
def api_list_inbox():
    return jsonify({"files": _list_dir(INBOX_DIR)})


@app.route("/api/outbox", methods=["GET"])
def api_list_outbox():
    return jsonify({"files": _list_dir(OUTBOX_DIR)})


@app.route("/api/file/inbox/<path:filename>", methods=["GET"])
def api_read_inbox(filename):
    try:
        target = _safe_path(INBOX_DIR, filename)
        return jsonify({"name": filename, "content": target.read_text(encoding="utf-8")})
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 404


@app.route("/api/file/outbox/<path:filename>", methods=["GET"])
def api_read_outbox(filename):
    try:
        target = _safe_path(OUTBOX_DIR, filename)
        return jsonify({"name": filename, "content": target.read_text(encoding="utf-8")})
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 404


# ─── Routes: File Management ──────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    safe_name = _sanitise_filename(file.filename)
    try:
        target = _safe_path(INBOX_DIR, safe_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        file.save(target)
        log.info("Uploaded %s (%d bytes)", safe_name, target.stat().st_size)
        return jsonify({"name": safe_name, "size": target.stat().st_size})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/inbox/<path:filename>", methods=["DELETE"])
def api_delete_inbox(filename):
    try:
        target = _safe_path(INBOX_DIR, filename)
        if target.exists():
            target.unlink()
        return jsonify({"deleted": filename})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/inbox", methods=["DELETE"])
def api_clear_inbox():
    for item in INBOX_DIR.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)
    log.info("Inbox cleared")
    return jsonify({"cleared": True})


@app.route("/api/outbox", methods=["DELETE"])
def api_clear_outbox():
    for item in OUTBOX_DIR.iterdir():
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)
    log.info("Outbox cleared")
    return jsonify({"cleared": True})


# ─── Routes: Model Selection ──────────────────────────────────────────────────
@app.route("/api/model", methods=["GET"])
def api_get_model():
    return jsonify({"model": _current_model})


@app.route("/api/model", methods=["POST"])
def api_set_model():
    global _current_model
    data  = request.get_json(silent=True) or {}
    model = (data.get("model") or "").strip()
    if not model:
        return jsonify({"error": "model is required"}), 400
    _current_model = model
    log.info("Model changed to: %s", model)
    return jsonify({"model": _current_model})


@app.route("/api/models", methods=["GET"])
def api_list_models():
    """Return available models from configured API providers."""
    force  = request.args.get("refresh", "").lower() in ("1", "true", "yes")
    models = _get_models(force=force)
    providers = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        providers.append("anthropic")
    if os.environ.get("OPENROUTER_API_KEY"):
        providers.append("openrouter")
    return jsonify({"models": models, "providers": providers})


# ─── Routes: Agent Control ────────────────────────────────────────────────────
@app.route("/api/agent/run", methods=["POST"])
def api_run_agent():
    if state.status == "running":
        return jsonify({"error": "Agent is already running"}), 409
    if not (INBOX_DIR / "instruction.md").exists():
        return jsonify({"error": "instruction.md not found in inbox — upload it first"}), 400

    thread = threading.Thread(
        target=_agent_thread, args=(_current_model,), daemon=True, name="agent"
    )
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/agent/reset", methods=["POST"])
def api_reset():
    if state.status == "running":
        return jsonify({"error": "Cannot reset while agent is running"}), 409
    state.reset()
    return jsonify({"status": "idle"})


@app.route("/api/agent/status", methods=["GET"])
def api_agent_status():
    offset = int(request.args.get("offset", 0))
    return jsonify(state.snapshot(offset=offset))


# ─── Routes: Real-time Log Stream (SSE) ──────────────────────────────────────
@app.route("/api/agent/logs", methods=["GET"])
def api_agent_logs():
    """SSE stream of real-time log entries.

    Each payload is JSON:
      {"time": "...", "msg": "..."}          — a log line
      {"done": true, "status": "completed"}  — terminal event
    """
    offset = int(request.args.get("offset", 0))

    def _generate():
        sent = offset
        while True:
            snap = state.snapshot(offset=sent)
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


# ─── Entry Point ─────────────────────────────────────────────────────────────
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    print(f"\n  LangChain Agent Web UI")
    print(f"  ─────────────────────────────────────")
    print(f"  URL    : http://localhost:{PORT}")
    print(f"  Inbox  : {INBOX_DIR}")
    print(f"  Outbox : {OUTBOX_DIR}")
    print(f"  Model  : {_current_model}\n")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
