#!/usr/bin/env python3
"""
Claude Agent Harness — Web Application
========================================
A minimal Flask web application that provides a browser UI for:

  • Uploading instruction.md, skill files, and payload files to the inbox
  • Browsing and viewing files in the inbox and outbox
  • Triggering the agent to process the current inbox
  • Streaming the agent's log output in real-time

Endpoints:
  GET  /                      → web UI (index.html)
  GET  /api/inbox             → list inbox files
  GET  /api/outbox            → list outbox files
  GET  /api/file/inbox/<path> → read an inbox file
  GET  /api/file/outbox/<path>→ read an outbox file
  POST /api/upload            → upload a file to the inbox
  DEL  /api/inbox/<path>      → delete an inbox file
  DEL  /api/inbox             → clear all inbox files
  DEL  /api/outbox            → clear all outbox files
  POST /api/agent/run         → start an agent run
  POST /api/agent/reset       → reset agent state to idle
  GET  /api/agent/status      → current agent status + log snapshot
  GET  /api/agent/logs        → SSE stream of real-time log entries

Environment variables:
  INBOX_DIR   default: /app/inbox
  OUTBOX_DIR  default: /app/outbox
  PORT        default: 8080
  HOST        default: 0.0.0.0
"""

import json
import logging
import os
import re
import shutil
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import anyio
import httpx
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from agent_harness import run_agent

# ─── Configuration ─────────────────────────────────────────────────────────────
INBOX_DIR  = Path(os.environ.get("INBOX_DIR",  "/app/inbox"))
OUTBOX_DIR = Path(os.environ.get("OUTBOX_DIR", "/app/outbox"))
PORT       = int(os.environ.get("PORT", "8080"))
HOST       = os.environ.get("HOST", "0.0.0.0")

# ─── Provider & Model State ───────────────────────────────────────────────────
_PROVIDERS = ("anthropic", "openrouter")
_current_provider: str = os.environ.get("API_PROVIDER", "anthropic")
_model_cache: dict[str, tuple[list[dict], float]] = {}
_MODEL_CACHE_TTL = 300.0  # seconds


def _fetch_models(provider: str) -> list[dict]:
    """Fetch available models from the provider API, with a 5-minute in-process cache."""
    cached, ts = _model_cache.get(provider, (None, 0.0))
    if cached is not None and time.time() - ts < _MODEL_CACHE_TTL:
        return cached

    if provider == "anthropic":
        r = httpx.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key":          os.environ.get("ANTHROPIC_API_KEY", ""),
                "anthropic-version":  "2023-06-01",
            },
            timeout=10.0,
        )
        r.raise_for_status()
        models = [
            {"id": m["id"], "name": m.get("display_name", m["id"])}
            for m in r.json().get("data", [])
        ]
    elif provider == "openrouter":
        r = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"},
            timeout=10.0,
        )
        r.raise_for_status()
        models = sorted(
            [
                {"id": m["id"], "name": m.get("name", m["id"])}
                for m in r.json().get("data", [])
            ],
            key=lambda m: m["name"].lower(),
        )
    else:
        models = []

    _model_cache[provider] = (models, time.time())
    return models

INBOX_DIR.mkdir(parents=True, exist_ok=True)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
log = logging.getLogger("web_app")


# ─── Agent State ────────────────────────────────────────────────────────────────
class AgentState:
    """Thread-safe container for one agent run's state and log history."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.status      = "idle"   # idle | running | completed | error
        self.logs: deque[dict] = deque(maxlen=2000)
        self.started_at: str | None  = None
        self.finished_at: str | None = None
        self.error: str | None       = None

    # ── Mutations (always lock) ────────────────────────────────────────────────
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

    # ── Read snapshot (safe for serialisation) ─────────────────────────────────
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


# ─── Agent Background Thread ─────────────────────────────────────────────────
def _agent_thread() -> None:
    """Entry point for the background agent thread."""
    state.start()
    state.add_log("=== Agent run started ===")
    try:
        anyio.run(run_agent, INBOX_DIR, OUTBOX_DIR, state.add_log)
        state.finish()
        state.add_log("=== Agent run completed successfully ===")
    except FileNotFoundError as exc:
        state.finish(str(exc))
        state.add_log(f"ERROR: {exc}")
    except RuntimeError as exc:
        state.finish(str(exc))
        state.add_log(f"BLOCKED: {exc}")
    except Exception as exc:
        state.finish(f"Unexpected error: {exc}")
        state.add_log(f"FATAL: {exc}")


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _safe_path(base: Path, rel: str) -> Path:
    """Resolve rel under base; raise ValueError on path traversal."""
    target = (base / rel).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise ValueError(f"Path traversal denied: {rel}")
    return target


def _list_dir(directory: Path) -> list[dict]:
    """Return a sorted list of file metadata dicts for all files in directory."""
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
    """Allow letters, digits, dots, dashes, underscores, and forward slashes only."""
    return re.sub(r"[^\w.\-/]", "_", raw)


# ─── Routes: Pages ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ─── Routes: File Browser API ─────────────────────────────────────────────────
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


# ─── Routes: File Management ─────────────────────────────────────────────────
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


# ─── Routes: Provider & Model ─────────────────────────────────────────────────
@app.route("/api/providers", methods=["GET"])
def api_list_providers():
    return jsonify({"providers": list(_PROVIDERS), "current": _current_provider})


@app.route("/api/provider", methods=["GET"])
def api_get_provider():
    return jsonify({"provider": _current_provider})


@app.route("/api/provider", methods=["POST"])
def api_set_provider():
    global _current_provider
    data     = request.get_json(silent=True) or {}
    provider = data.get("provider", "").lower()
    if provider not in _PROVIDERS:
        return jsonify({"error": f"Unknown provider: {provider}",
                        "providers": list(_PROVIDERS)}), 400
    _current_provider = provider
    os.environ["API_PROVIDER"] = provider
    os.environ.pop("CLAUDE_MODEL", None)   # reset model when provider changes
    _model_cache.pop(provider, None)        # force fresh fetch
    log.info("Provider changed to: %s", provider)
    return jsonify({"provider": provider})


@app.route("/api/models", methods=["GET"])
def api_list_models():
    provider = request.args.get("provider", _current_provider)
    if provider not in _PROVIDERS:
        return jsonify({"error": f"Unknown provider: {provider}"}), 400
    try:
        models = _fetch_models(provider)
        return jsonify({"models": models, "provider": provider})
    except httpx.HTTPStatusError as exc:
        return jsonify({"error": f"Provider API error {exc.response.status_code}", "models": []}), 502
    except Exception as exc:
        log.exception("Failed to fetch models for %s", provider)
        return jsonify({"error": str(exc), "models": []}), 500


@app.route("/api/model", methods=["GET"])
def api_get_model():
    return jsonify({"model": os.environ.get("CLAUDE_MODEL", ""), "provider": _current_provider})


@app.route("/api/model", methods=["POST"])
def api_set_model():
    data  = request.get_json(silent=True) or {}
    model = data.get("model", "").strip()
    if not model:
        return jsonify({"error": "model is required"}), 400
    os.environ["CLAUDE_MODEL"] = model
    log.info("Model changed to: %s", model)
    return jsonify({"model": model})


# ─── Routes: Agent Control ────────────────────────────────────────────────────
@app.route("/api/agent/run", methods=["POST"])
def api_run_agent():
    if state.status == "running":
        return jsonify({"error": "Agent is already running"}), 409
    if not (INBOX_DIR / "instruction.md").exists():
        return jsonify({"error": "instruction.md not found in inbox — upload it first"}), 400

    thread = threading.Thread(target=_agent_thread, daemon=True, name="agent")
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
    """
    Server-Sent Events stream.

    The client connects here and receives log entries as they are produced.
    Query param: ?offset=N  (skip first N log entries already seen).

    Each SSE event payload is a JSON object:
      {"time": "...", "msg": "..."} — a log entry
      {"done": true, "status": "completed"|"error"} — final event
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
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    print(f"\n  Claude Agent Harness Web UI")
    print(f"  ─────────────────────────────")
    print(f"  URL    : http://localhost:{PORT}")
    print(f"  Inbox  : {INBOX_DIR}")
    print(f"  Outbox : {OUTBOX_DIR}\n")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
