#!/usr/bin/env bash
# =============================================================================
# run.sh — Build and run the Claude Agent Harness web application.
#
# Usage:
#   ./run.sh [options]
#
# Options:
#   -k KEY     Anthropic API key       (default: $ANTHROPIC_API_KEY)
#   -m MODEL   Claude model            (default: claude-opus-4-5)
#   -n ITER    Max agentic iterations  (default: 50)
#   -p PORT    Host port to expose     (default: 8080)
#   -i DIR     Inbox directory         (default: ./inbox)
#   -o DIR     Outbox directory        (default: ./outbox)
#   -I IMAGE   Container image name    (default: claude-agent)
#   -h         Show this help and exit
#
# The web UI will be available at http://localhost:<PORT>
# =============================================================================
set -euo pipefail

# ─── Defaults ─────────────────────────────────────────────────────────────────
API_KEY="${ANTHROPIC_API_KEY:-}"
MODEL="${CLAUDE_MODEL:-claude-opus-4-5}"
MAX_TURNS="${MAX_TURNS:-50}"
PORT=8080
INBOX_DIR="$(pwd)/inbox"
OUTBOX_DIR="$(pwd)/outbox"
IMAGE_NAME="claude-agent"

# ─── Colours ──────────────────────────────────────────────────────────────────
CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
GRAY='\033[0;90m'; RESET='\033[0m'

step()     { echo -e "\n${CYAN}══  $*  ══${RESET}"; }
info()     { echo -e "  ${GRAY}$*${RESET}"; }
ok()       { echo -e "  ${GREEN}✔  $*${RESET}"; }
warn()     { echo -e "  ${YELLOW}⚠  $*${RESET}"; }

# ─── CLI parsing ──────────────────────────────────────────────────────────────
usage() {
    grep '^#' "$0" | grep -v '^#!/' | sed 's/^# \{0,2\}//'
    exit 0
}

while getopts ":k:m:n:p:i:o:I:h" opt; do
    case $opt in
        k) API_KEY="$OPTARG"   ;;
        m) MODEL="$OPTARG"     ;;
        n) MAX_TURNS="$OPTARG" ;;
        p) PORT="$OPTARG"      ;;
        i) INBOX_DIR="$(realpath "$OPTARG")"  ;;
        o) OUTBOX_DIR="$(realpath "$OPTARG")" ;;
        I) IMAGE_NAME="$OPTARG";;
        h) usage               ;;
        :) echo "ERROR: -$OPTARG requires an argument." >&2; exit 1 ;;
       \?) echo "ERROR: Unknown option -$OPTARG" >&2; exit 1 ;;
    esac
done

# ─── Pre-flight checks ────────────────────────────────────────────────────────
step "Pre-flight checks"

if [[ -z "$API_KEY" ]]; then
    echo "ERROR: ANTHROPIC_API_KEY is not set. Use -k or export the variable." >&2
    exit 1
fi
ok "API key found"

# Ensure inbox/outbox exist on the host
mkdir -p "$INBOX_DIR" "$OUTBOX_DIR"
ok "Inbox  : $INBOX_DIR"
ok "Outbox : $OUTBOX_DIR"

if [[ ! -f "$INBOX_DIR/instruction.md" ]]; then
    warn "instruction.md not found in inbox — upload it via the web UI."
fi

# ─── 1. Build image ───────────────────────────────────────────────────────────
step "Building container image: $IMAGE_NAME"
info "> podman build -t $IMAGE_NAME -f Containerfile ."
podman build -t "$IMAGE_NAME" -f Containerfile .
ok "Image built: $IMAGE_NAME"

# ─── 2. Run container ─────────────────────────────────────────────────────────
step "Starting web application"
info "Model    : $MODEL"
info "Max turns: $MAX_TURNS"
info "Port     : $PORT"

echo ""
echo -e "${GREEN}  ┌────────────────────────────────────────────────────┐${RESET}"
echo -e "${GREEN}  │  Web UI ready at: http://localhost:${PORT}             │${RESET}"
echo -e "${GREEN}  │  Press Ctrl+C to stop.                              │${RESET}"
echo -e "${GREEN}  └────────────────────────────────────────────────────┘${RESET}"
echo ""

podman run --rm \
    --name claude-agent \
    -e "ANTHROPIC_API_KEY=${API_KEY}" \
    -e "CLAUDE_MODEL=${MODEL}" \
    -e "MAX_TURNS=${MAX_TURNS}" \
    -e "PORT=8080" \
    -p "${PORT}:8080" \
    -v "${INBOX_DIR}:/app/inbox:Z" \
    -v "${OUTBOX_DIR}:/app/outbox:Z" \
    "$IMAGE_NAME"
