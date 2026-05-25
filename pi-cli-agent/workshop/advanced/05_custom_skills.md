# Exercise 05 — Build and Load Custom Pi Skills

**Track:** Advanced | **Time:** ~30 min

---

## Objective

Learn how to create formal pi skills — reusable capability packages with
proper metadata — and load them via `web_app.py` instead of (or in addition to)
the inbox `skill.md`.

---

## Background

There are two ways to give the agent skill files in this harness:

| Method | When to use |
|--------|------------|
| `inbox/skill.md` | Run-specific behaviour; travels with the task |
| `--skill <path>` (formal pi skill) | Reusable across many runs; shareable across machines |
| Global skill in `~/.pi/agent/skills/` | Always available; no `--skill` flag needed |

A formal pi skill is a Markdown file with a YAML frontmatter block:

```markdown
---
name: skill-name          # lowercase, hyphens only
description: >            # shown to the agent in every run — be specific
  Use this skill when...
---

# Skill body
(full instructions, loaded only when the skill is relevant)
```

Pi uses the `description` for matching — the agent sees all descriptions
in its system prompt and loads the full body only when the task matches.

---

## Steps

### 1. Create a domain-specific skill

Create a new file `skills/csv-analyst/SKILL.md`:

```bash
mkdir -p skills/csv-analyst
```

```markdown
---
name: csv-analyst
description: >
  Use this skill when the task involves reading, analysing, or transforming
  CSV files. Provides recipes for common data operations using Python and bash.
---

# CSV Analyst Skill

## Reading CSV files

Use bash + Python for reliable parsing:

```bash
python3 - <<'EOF'
import csv
with open('./inbox/data.csv') as f:
    rows = list(csv.DictReader(f))
print(f"Rows: {len(rows)}, Columns: {list(rows[0].keys())}")
EOF
```

## Aggregation recipes

```bash
# Group by column and count
python3 -c "
import csv
from collections import Counter
with open('./inbox/data.csv') as f:
    c = Counter(r['department'] for r in csv.DictReader(f))
print(dict(c))
"
```

## Output format

Write results as JSON to `./outbox/<name>.json` and a summary table
as Markdown to `./outbox/<name>.md`.

## Validation

After writing JSON, validate it parses:
```bash
python3 -m json.tool ./outbox/result.json > /dev/null && echo "valid JSON"
```
```

### 2. Load the skill via `_agent_thread()` in `web_app.py`

Open `web_app.py` and find `_agent_thread()`. Add skill discovery before the
`cmd` list is built:

```python
    model      = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    skill_file = INBOX_DIR / "skill.md"

    # ── Discover skills/ directory ─────────────────────────────────────────────
    skill_dir = Path(__file__).parent / "skills"
    skill_flags: list[str] = []
    if skill_dir.exists():
        for skill_path in sorted(skill_dir.rglob("SKILL.md")):
            skill_flags += ["--skill", str(skill_path)]
            state.add_log(f"Loading skill: {skill_path.parent.name}")

    cmd: list[str] = [
        "pi", "-p", _build_prompt(INBOX_DIR, OUTBOX_DIR),
        "--no-session",
        "--model", model,
    ]
    cmd += skill_flags                          # add discovered skills
    if skill_file.exists():
        cmd += ["--skill", str(skill_file)]    # inbox skill last
```

Also add `from pathlib import Path` at the top if it is not already imported
(it is — `web_app.py` already imports `Path`).

### 3. Verify the skill loads

Restart `web_app.py`, then click **Run Agent**. The log stream should include:

```
Loading skill: csv-analyst
```

followed by the agent using the Python recipes from your skill.

### 4. Create a second skill: report formatter

```bash
mkdir -p skills/report-formatter
```

```markdown
---
name: report-formatter
description: >
  Use this skill to format any analysis output as a structured Markdown report
  following the organisation's standard template.
---

# Report Formatter Skill

## Standard report structure

Every report must follow this template exactly:

```markdown
# [Title]

**Date:** YYYY-MM-DD  
**Source files:** [list]  
**Agent model:** [model used]

## Executive Summary
[2–3 sentence overview of key findings]

## Findings
[tables, lists, or sections — one per finding]

## Appendix
[raw data or methodology notes, if needed]
```

## File naming

Use: `./outbox/report_YYYYMMDD.md`  
Example: `./outbox/report_20260509.md`
```

Restart the app and re-run. Check whether the output now follows the template.

### 5. Distribute a skill as a zip

Skills are portable — copy the entire `skills/csv-analyst/` directory to
another machine and load it with `--skill /path/to/csv-analyst/SKILL.md`.

You can also host skills in a git repository and load them by cloning in
`_agent_thread()`:

```python
import subprocess, tempfile
# Clone a skill repo temporarily
with tempfile.TemporaryDirectory() as tmp_dir:
    subprocess.run(["git", "clone", "--depth", "1", skill_url, tmp_dir], check=True)
    skill_flags += ["--skill", str(Path(tmp_dir) / "SKILL.md")]
```

---

## Skill vs instruction: when to use each

| Content type | Put it in… |
|-------------|-----------|
| "What to do this run" | `instruction.md` |
| "How to use tools for this domain" | `skill.md` or skills/ |
| "Organisation-wide standards" | global `~/.pi/agent/skills/` |
| "Reusable capability for many projects" | formal SKILL.md in its own directory |

---

## Reflection questions

1. The skill `description` field is always in the agent's context. How would
   you write a description that triggers loading at exactly the right time
   — neither too broad nor too narrow?

2. Two skills give conflicting instructions about output format. How does the
   agent resolve this? How would you prevent conflicts?

3. Could a skill file itself be a prompt injection vector? What would a
   malicious skill look like, and how would you defend against it?

4. Compare writing a formal pi skill to writing a Python `@tool` function.
   What can each approach do that the other cannot?
