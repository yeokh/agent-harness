# Agent instructions

Date: Oct-2026

## Tone and style
- Be concise and professional. No fluff, filler, or unnecessary preamble.
- Prefer short, direct answers. Expand only when the task needs detail.
- Do not restate the task or pad responses with obvious next steps.

## Project context

This is an agent harness project repository root containing the setup and deployment artifacts of agent harnesses built using SDK and frameworks from Pydantic AI, Google, Claude etc.  

## File access guardrails
- **Default scope:** Do not read or write files outside the current project root context unless explicitly requested.
- **Reading outside project root:** Allowed without user confirmation if explicitly requested, provided the target is within the user's home directory. Reading outside the user's home directory requires user confirmation.
- **Writing outside project root:** Strictly prohibited without explicit user confirmation. Writing outside the user's home directory requires strict/additional user confirmation before proceeding.

## Git hygiene
- Never stage or commit secrets: API keys, tokens, passwords, private keys, `.env`, credential JSON, or similar.
- Before `git add`, `git commit`, or `git push`, scan the change set for secrets and sensitive data. If found, stop and warn; do not proceed.
- Do not add build artifacts, local DBs, caches, virtualenvs, or temp paths. Prefer updating `.gitignore` when a recurring pattern appears.

### Do not commit
- Dotenv / secrets: `.env`, `.env.*`, `*.pem`, `*.key`, `credentials.json`, `secrets.*`
- Virtualenvs / tool caches: `.venv/`, `venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.tox/`
- Editor / OS junk: `.idea/`, `.vscode/` (unless the team explicitly tracks shared settings), `.DS_Store`, `Thumbs.db`
- Go / build output: `bin/`, `dist/`, `*.exe`, `*.test`, `*.out`, `coverage.*`
- Local data: `*.db`, `*.sqlite`, `*.sqlite3`
- Temp / cache: `tmp/`, `temp/`, `.cache/`, `node_modules/`

### When unsure whether a path is safe to commit, ask before staging it.

## Coding defaults
- Match existing style in the target implementation folder if this is an existing project.
- Keep changes scoped to the request; no drive-by refactors or unsolicited docs.
- Do not commit unless explicitly asked.
- Do not push unless explicitly asked.
