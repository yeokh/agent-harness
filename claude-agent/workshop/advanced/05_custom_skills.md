# Exercise 05 — Dynamic Skill Loading

**Track:** Advanced | **Time:** ~30 min

---

## Objective

Implement `load_skills()` so the agent can load new tools at runtime from
Python files uploaded to `inbox/skills/`. This allows non-developers to extend
the agent without modifying or redeploying the harness.

---

## Background

Hard-coding tools in `agent_harness.py` requires a code change and restart for
every new capability. **Dynamic skill loading** lets you:

- Upload a `inbox/skills/my_tool.py` file
- The harness imports it automatically at run start
- The agent gains the new tool — no restart needed

This is similar to how plugin systems work in production applications.

---

## Steps

### 1. Implement `load_skills()` in `agent_harness.py`

Find the `load_skills()` placeholder and replace the body:

```python
import importlib.util

skills, names = [], []
skills_dir = inbox_dir / "skills"

if not skills_dir.exists():
    log.info("No skills/ directory in inbox — skipping skill load")
    return [], []

for skill_file in sorted(skills_dir.glob("*.py")):
    log.info("Loading skill file: %s", skill_file.name)
    spec = importlib.util.spec_from_file_location(skill_file.stem, skill_file)
    mod  = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        log.warning("Failed to load skill %s: %s", skill_file.name, exc)
        continue

    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        # The @tool decorator stores metadata on the function
        if callable(obj) and hasattr(obj, "__tool_name__"):
            tool_name = obj.__tool_name__
            skills.append(obj)
            names.append(f"mcp__agent-tools__{tool_name}")
            log.info("Registered skill: %s", tool_name)

return skills, names
```

> **Note:** The exact attribute name for tool metadata depends on the SDK version.
> If `__tool_name__` doesn't work, inspect the decorated function with
> `dir(my_tool_function)` to find the right attribute.

### 2. Create a skill file

Create `inbox/skills/csv_stats.py`:

```python
"""
Skill: CSV Statistics
Provides tools for computing basic statistics on CSV text content.
"""
import csv
import io
from claude_agent_sdk import tool


@tool(
    "csv_row_count",
    "Count the number of data rows in a CSV string (excludes header).",
    {"csv_text": str},
)
async def csv_row_count(args: dict) -> dict:
    reader = csv.reader(io.StringIO(args["csv_text"]))
    rows   = list(reader)
    count  = max(0, len(rows) - 1)   # exclude header
    return {"content": [{"type": "text", "text": str(count)}]}


@tool(
    "csv_column_names",
    "Return the column names (header row) of a CSV string as a JSON array.",
    {"csv_text": str},
)
async def csv_column_names(args: dict) -> dict:
    import json
    reader  = csv.reader(io.StringIO(args["csv_text"]))
    headers = next(reader, [])
    return {"content": [{"type": "text", "text": json.dumps(headers)}]}
```

### 3. Write a skill-aware instruction

```markdown
# Task: CSV Deep Analysis

Use the `csv_row_count` and `csv_column_names` skills to analyse all CSV
files in the inbox.

For each file:
1. Get the column names.
2. Count the rows.
3. Read the full content and compute statistics per column where possible.

Write a detailed report to `outbox/csv_analysis.md`.
Write DONE on the last line.
```

### 4. Upload and run

Upload `inbox/skills/csv_stats.py` via the web UI.
Run the agent. Check the log for `Registered skill: csv_row_count`.

---

## Security considerations

Dynamic code loading is powerful and dangerous. In a production system you should:

- **Validate skill files** before importing:
  ```python
  # Simple heuristic: reject files with dangerous imports
  source = skill_file.read_text()
  for dangerous in ["subprocess", "os.system", "eval(", "exec("]:
      if dangerous in source:
          log.warning("Rejected skill %s: contains '%s'", skill_file.name, dangerous)
          continue
  ```

- **Sandbox execution**: run skill code in a restricted namespace
  (this is complex — use a proper sandbox library for production).

- **Allowlist tools**: require skill tools to be listed in an explicit manifest
  file rather than auto-detecting all decorated functions.

---

## Going further

Write skill files for:

1. **Markdown table formatter** — takes a list of dicts, returns a Markdown table
2. **JSON flattener** — reads nested JSON and flattens it to a CSV
3. **Text sentiment** — calls the Anthropic API to score text sentiment
4. **Zip inspector** — lists files inside a zip without extracting (see Demo D2)

---

## Reflection questions

1. What is the attack surface of dynamic code loading? List three specific risks.

2. If a skill file imports `requests` and makes an outbound HTTP call, does
   the container's sandbox protect the host? Why or why not?

3. How would you implement a "skill registry" so that skill files must be
   pre-approved by an admin before they can be used?

4. What happens if two skill files define tools with the same name?
   How would you detect and handle this?
