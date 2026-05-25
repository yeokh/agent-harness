#!/usr/bin/env python3
"""
Pi CLI Agent — Web Application
================================
Flask web app with the same interface as claude-agent/web_app.py,
but drives the pi CLI via subprocess instead of the Claude Agent SDK.

Endpoints:
  GET  /                      → web UI (index.html)
  GET  /api/inbox             → list inbox files
  GET  /api/outbox            → list outbox files
  GET  /api/file/inbox/<path> → read an inbox file
  GET  /api/file/outbox/<path>→ read an outbox file
  POST /api/upload            → upload a file to the inbox
  DEL  /api/inbox/<path>      → delete an inbox file
  DEL  /api/outbox            → clear all outbox files
  GET  /api/model             → get/list allowed models
  POST /api/model             → set active model
  POST /api/agent/run         → start an agent run
  POST /api/agent/reset       → reset agent state to idle
  GET  /api/agent/status      → current status + log snapshot
  GET  /api/agent/logs        → SSE stream of real-time log entries

Environment variables:
  ANTHROPIC_API_KEY   required for anthropic/* models
  OPENROUTER_API_KEY  required for openrouter/* models
  INBOX_DIR           default: ./inbox
  OUTBOX_DIR          default: ./outbox
  AGENT_MODEL         default: anthropic/claude-sonnet-4-6
  PORT                default: 8080
  HOST                default: 0.0.0.0

Model format: "<provider>/<model_id>"
  anthropic/claude-sonnet-4-6
  openrouter/deepseek/deepseek-r1-0528
"""

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

# ─── Configuration ─────────────────────────────────────────────────────────────
INBOX_DIR  = Path(os.environ.get("INBOX_DIR",  "./inbox")).resolve()
OUTBOX_DIR = Path(os.environ.get("OUTBOX_DIR", "./outbox")).resolve()
PORT       = int(os.environ.get("PORT", "8080"))
HOST       = os.environ.get("HOST", "0.0.0.0")

ALLOWED_MODELS = [
    # Anthropic direct
    "anthropic/claude-opus-4-7",
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-haiku-4-5-20251001",
    # OpenRouter — Anthropic
    "openrouter/anthropic/claude-opus-4.7",
    "openrouter/anthropic/claude-sonnet-4.6",
    "openrouter/anthropic/claude-haiku-4.5",
    # OpenRouter — DeepSeek
    "openrouter/deepseek/deepseek-r1-0528",
    "openrouter/deepseek/deepseek-chat",
    # OpenRouter — Google
    "openrouter/google/gemini-2.5-pro",
    "openrouter/google/gemini-2.5-flash",
    # OpenRouter — Meta
    "openrouter/meta-llama/llama-3.3-70b-instruct",
    "openrouter/meta-llama/llama-4-scout",
]

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


# ─── Pi subprocess agent ───────────────────────────────────────────────────────

def _build_prompt(inbox: Path, outbox: Path) -> str:
    return (
        f"Read {inbox}/instruction.md for your task instructions, then execute them fully. "
        f"All payload files to process are in {inbox}/. "
        f"Write every output file to {outbox}/. "
        f"Do not read from or write to any path outside {inbox}/ and {outbox}/."
    )


def _parse_model(spec: str) -> tuple[str, str]:
    """Split 'provider/model_id' into (provider, model_id). Defaults to anthropic."""
    parts = spec.split("/", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "anthropic", spec


def _agent_thread() -> None:
    """Background thread: runs pi CLI and streams its output to AgentState."""
    state.start()
    state.add_log("=== Agent run started ===")

    raw_model  = os.environ.get("AGENT_MODEL", os.environ.get("CLAUDE_MODEL", "anthropic/claude-sonnet-4-6"))
    provider, model_id = _parse_model(raw_model)
    skill_file = INBOX_DIR / "skill.md"

    # Validate that the required API key is present before launching.
    key_var = "OPENROUTER_API_KEY" if provider == "openrouter" else "ANTHROPIC_API_KEY"
    if not os.environ.get(key_var):
        msg = f"{key_var} is not set — cannot use provider '{provider}'"
        state.finish(msg)
        state.add_log(f"ERROR: {msg}")
        return

    cmd: list[str] = [
        "pi", "-p", _build_prompt(INBOX_DIR, OUTBOX_DIR),
        "--no-session",
        "--provider", provider,
        "--model", model_id,
    ]
    if skill_file.exists():
        cmd += ["--skill", str(skill_file)]

    state.add_log(f"provider={provider}  model={model_id}  skill={'yes' if skill_file.exists() else 'no'}")
    cmd_str = " ".join(cmd)
    log.info("Starting pi: %s", cmd_str)
    state.add_log(f"Starting pi: {cmd_str}")

    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUTBOX_DIR / "agent.log"

    try:
        with log_path.open("w", encoding="utf-8") as log_fh:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for raw_line in proc.stdout:
                line = raw_line.rstrip("\n")
                if line:
                    state.add_log(line)
                    log_fh.write(line + "\n")
                    log_fh.flush()

            proc.wait()

        if proc.returncode == 0:
            state.finish()
            state.add_log("=== Agent run completed successfully ===")
        else:
            err = f"pi exited with code {proc.returncode}"
            state.finish(err)
            state.add_log(f"ERROR: {err}")

    except FileNotFoundError:
        msg = (
            "pi CLI not found. Install it with:\n"
            "  curl -fsSL https://pi.dev/install.sh | sh\n"
            "  (or: npm install -g @earendil-works/pi-coding-agent)"
        )
        state.finish(msg)
        state.add_log(f"ERROR: {msg}")
    except Exception as exc:
        state.finish(f"Unexpected error: {exc}")
        state.add_log(f"FATAL: {exc}")


# ─── Helpers ─────────────────────────────────────────────────────────────────
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


# ─── Routes: Model Selection ─────────────────────────────────────────────────
MODEL_GROUPS = [
    {
        "provider": "anthropic",
        "label": "Anthropic (direct)",
        "models": [
            {"id": "anthropic/claude-opus-4-7",          "label": "Claude Opus 4.7 (most capable)"},
            {"id": "anthropic/claude-sonnet-4-6",         "label": "Claude Sonnet 4.6 (balanced)"},
            {"id": "anthropic/claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5 (fast)"},
        ],
    },
    {
        "provider": "openrouter",
        "label": "OpenRouter — Anthropic",
        "models": [
            {"id": "openrouter/anthropic/claude-opus-4.7",    "label": "Claude Opus 4.7"},
            {"id": "openrouter/anthropic/claude-sonnet-4.6",  "label": "Claude Sonnet 4.6"},
            {"id": "openrouter/anthropic/claude-haiku-4.5",   "label": "Claude Haiku 4.5"},
        ],
    },
    {
        "provider": "openrouter",
        "label": "OpenRouter — DeepSeek",
        "models": [
            {"id": "openrouter/deepseek/deepseek-r1-0528", "label": "DeepSeek R1 (reasoning)"},
            {"id": "openrouter/deepseek/deepseek-chat",    "label": "DeepSeek V3 (fast)"},
        ],
    },
    {
        "provider": "openrouter",
        "label": "OpenRouter — Google",
        "models": [
            {"id": "openrouter/google/gemini-2.5-pro",   "label": "Gemini 2.5 Pro"},
            {"id": "openrouter/google/gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
        ],
    },
    {
        "provider": "openrouter",
        "label": "OpenRouter — Meta",
        "models": [
            {"id": "openrouter/meta-llama/llama-3.3-70b-instruct", "label": "Llama 3.3 70B"},
            {"id": "openrouter/meta-llama/llama-4-scout",          "label": "Llama 4 Scout"},
        ],
    },
]


@app.route("/api/model", methods=["GET"])
def api_get_model():
    current = os.environ.get("AGENT_MODEL", os.environ.get("CLAUDE_MODEL", "anthropic/claude-sonnet-4-6"))
    return jsonify({
        "model":   current,
        "allowed": ALLOWED_MODELS,
        "groups":  MODEL_GROUPS,
    })


@app.route("/api/model", methods=["POST"])
def api_set_model():
    data  = request.get_json(silent=True) or {}
    model = data.get("model", "")
    if model not in ALLOWED_MODELS:
        return jsonify({"error": f"Model not allowed: {model}", "allowed": ALLOWED_MODELS}), 400
    os.environ["AGENT_MODEL"] = model
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
    Server-Sent Events stream of real-time log entries.

    Each SSE payload is JSON:
      {"time": "...", "msg": "..."} — a log line from pi's stdout
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
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    model = os.environ.get("AGENT_MODEL", os.environ.get("CLAUDE_MODEL", "anthropic/claude-sonnet-4-6"))
    print(f"\n  Pi CLI Agent Web UI")
    print(f"  ─────────────────────────────")
    print(f"  URL    : http://localhost:{PORT}")
    print(f"  Inbox  : {INBOX_DIR}")
    print(f"  Outbox : {OUTBOX_DIR}")
    print(f"  Model  : {model}")
    ant_key = "set" if os.environ.get("ANTHROPIC_API_KEY") else "NOT SET"
    or_key  = "set" if os.environ.get("OPENROUTER_API_KEY") else "NOT SET"
    print(f"  ANTHROPIC_API_KEY   : {ant_key}")
    print(f"  OPENROUTER_API_KEY  : {or_key}\n")
    app.run(host=HOST, port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
