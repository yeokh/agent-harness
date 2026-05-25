# Exercise 05 — Build Custom Toolsets

**Track:** Advanced | **Time:** ~30 min

---

## Objective

Organise related tool functions into domain-specific Python modules, load
them conditionally in `strands_agent.py`, and understand when to use modules
vs. inline tool functions.

---

## Background

### The toolset problem

As you add more tools in Exercise 03, `_make_tools()` grows long.  When tools
share helper logic (e.g. CSV parsing functions used by three different tools),
duplicating them inline becomes a maintenance problem.

The solution is to group related tools into **toolset modules** — plain Python
files in a `tools/` directory.  `_make_tools()` imports and combines them.

### Strands @tool with modular factories

Each toolset module exports a `make_*_tools(inbox, outbox, log_callback)` factory
that returns a list of `strands_tool()`-wrapped closures.  This keeps the tool
functions pure (no global state) while keeping `_make_tools()` clean:

```python
# strands_agent.py
from tools.csv_tools import make_csv_tools
extra_tools = make_csv_tools(inbox, outbox, log_callback)
return base_tools + extra_tools
```

---

## Steps

### 1. Create the tools directory

```bash
mkdir -p tools
touch tools/__init__.py
```

### 2. Write a CSV toolset module

Create `tools/csv_tools.py`:

```python
"""
CSV Toolset for Strands Agent
─────────────────────────────
Domain-specific tools for reading and transforming CSV files.
Each tool logs its call and result via log_callback so the browser
terminal shows [tool_use] / [result] lines like the built-in tools.

Imported conditionally by _make_tools() in strands_agent.py.
"""

import csv
import json
from pathlib import Path
from typing import Callable


def make_csv_tools(
    inbox:        Path,
    outbox:       Path,
    log_callback: Callable[[str], None],
) -> list:
    """Return CSV-specific Strands tool functions bound to the given paths."""
    from strands import tool as strands_tool  # noqa: PLC0415

    inbox_r  = inbox.resolve()
    outbox_r = outbox.resolve()

    def _in_allowed(path: Path) -> bool:
        p = path.resolve()
        return str(p).startswith(str(inbox_r)) or str(p).startswith(str(outbox_r))

    def _resolve(filepath: str) -> Path | None:
        for base in [Path(filepath), inbox_r / filepath]:
            p = base.resolve()
            if _in_allowed(p) and p.is_file():
                return p
        return None

    def csv_schema(filepath: str) -> str:
        """Return the column names and row count of a CSV file.

        Use this before csv_to_json when you want to understand the structure
        of an unknown CSV without loading all rows into memory.

        Args:
            filepath: Path to the CSV file (relative to inbox, or absolute).

        Returns:
            Comma-separated column names and a row count, or an error.
        """
        log_callback(f"[tool_use] csv_schema(filepath={filepath!r})")
        target = _resolve(filepath)
        if target is None:
            result = f"File not found: {filepath}"
            log_callback(f"[result] csv_schema: {result}")
            return result
        try:
            with target.open(encoding="utf-8") as f:
                reader  = csv.DictReader(f)
                columns = reader.fieldnames or []
                rows    = sum(1 for _ in reader)
            result = f"Columns: {', '.join(columns)}\nRows: {rows}"
            log_callback(f"[result] csv_schema: {result}")
            return result
        except Exception as exc:
            result = f"Error reading {filepath}: {exc}"
            log_callback(f"[result] csv_schema: {result}")
            return result

    def csv_to_json(filepath: str) -> str:
        """Parse a CSV file and return all rows as a JSON array.

        Each row becomes a JSON object with column names as keys.  Use when
        the task requires structured manipulation of tabular data.

        Args:
            filepath: Path to the CSV file (relative to inbox, or absolute).

        Returns:
            JSON string of all rows, or an error message.
        """
        log_callback(f"[tool_use] csv_to_json(filepath={filepath!r})")
        target = _resolve(filepath)
        if target is None:
            result = f"File not found: {filepath}"
            log_callback(f"[result] csv_to_json: {result}")
            return result
        try:
            with target.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            result = json.dumps(rows, indent=2)
            log_callback(f"[result] csv_to_json: parsed {len(rows)} rows")
            return result
        except Exception as exc:
            result = f"Error parsing {filepath}: {exc}"
            log_callback(f"[result] csv_to_json: {result}")
            return result

    def csv_group_by(filepath: str, column: str) -> str:
        """Group CSV rows by a column and return counts as JSON.

        Useful for quick frequency analysis without loading the full dataset.

        Args:
            filepath: Path to the CSV file.
            column:   Name of the column to group by.

        Returns:
            JSON object mapping each unique value to its row count.
        """
        log_callback(f"[tool_use] csv_group_by(filepath={filepath!r}, column={column!r})")
        target = _resolve(filepath)
        if target is None:
            result = f"File not found: {filepath}"
            log_callback(f"[result] csv_group_by: {result}")
            return result
        try:
            from collections import Counter
            with target.open(encoding="utf-8") as f:
                counts = Counter(row.get(column, "") for row in csv.DictReader(f))
            result = json.dumps(dict(counts.most_common()), indent=2)
            log_callback(f"[result] csv_group_by: {result[:200]}")
            return result
        except Exception as exc:
            result = f"Error: {exc}"
            log_callback(f"[result] csv_group_by: {result}")
            return result

    return [strands_tool(f) for f in [csv_schema, csv_to_json, csv_group_by]]
```

### 3. Write a report toolset module

Create `tools/report_tools.py`:

```python
"""
Report Toolset for Strands Agent
──────────────────────────────────
Tools for formatting and validating Markdown reports.
"""

from datetime import date
from pathlib import Path
from typing import Callable


def make_report_tools(
    inbox:        Path,
    outbox:       Path,
    log_callback: Callable[[str], None],
) -> list:
    """Return report-formatting tool functions."""
    from strands import tool as strands_tool  # noqa: PLC0415

    outbox_r = outbox.resolve()

    def validate_markdown_report(filepath: str) -> str:
        """Check that a Markdown report has the required sections.

        Verifies that the file contains level-2 headings for
        'Executive Summary', 'Findings', and 'Conclusion'.  Use this
        after writing a report to confirm it meets the standard structure.

        Args:
            filepath: Path to the Markdown file (relative to outbox).

        Returns:
            'VALID' if all sections present, or a list of missing sections.
        """
        log_callback(f"[tool_use] validate_markdown_report(filepath={filepath!r})")
        target = (outbox_r / filepath).resolve()
        if not str(target).startswith(str(outbox_r)) or not target.is_file():
            result = f"File not found in outbox: {filepath}"
            log_callback(f"[result] validate_markdown_report: {result}")
            return result
        try:
            text     = target.read_text(encoding="utf-8")
            required = ["Executive Summary", "Findings", "Conclusion"]
            missing  = [s for s in required if f"## {s}" not in text]
            result   = f"Missing sections: {', '.join(missing)}" if missing else "VALID: all required sections present"
            log_callback(f"[result] validate_markdown_report: {result}")
            return result
        except Exception as exc:
            result = f"Error: {exc}"
            log_callback(f"[result] validate_markdown_report: {result}")
            return result

    def add_report_header(filepath: str, source_files: str, model: str) -> str:
        """Prepend a standard metadata header to a Markdown report file.

        Inserts date, source files, and model name at the top of an existing
        report in the outbox.  Call this after writing the main report content.

        Args:
            filepath:     Path to the Markdown file (relative to outbox).
            source_files: Comma-separated list of input files used.
            model:        Name of the model that produced the report.

        Returns:
            Confirmation message, or an error.
        """
        log_callback(f"[tool_use] add_report_header(filepath={filepath!r})")
        target = (outbox_r / filepath).resolve()
        if not str(target).startswith(str(outbox_r)) or not target.is_file():
            result = f"File not found in outbox: {filepath}"
            log_callback(f"[result] add_report_header: {result}")
            return result
        try:
            original = target.read_text(encoding="utf-8")
            header   = (
                f"**Date:** {date.today()}  \n"
                f"**Source files:** {source_files}  \n"
                f"**Agent model:** {model}  \n\n"
                "---\n\n"
            )
            target.write_text(header + original, encoding="utf-8")
            result = f"Header added to {filepath}"
            log_callback(f"[result] add_report_header: {result}")
            return result
        except Exception as exc:
            result = f"Error: {exc}"
            log_callback(f"[result] add_report_header: {result}")
            return result

    return [strands_tool(f) for f in [validate_markdown_report, add_report_header]]
```

### 4. Load toolsets conditionally in `strands_agent.py`

Open `strands_agent.py` and update the `# ── WORKSHOP PLACEHOLDER (Exercise 03)`
section and the `base_tools` list at the bottom of `_make_tools()`:

```python
    # ── WORKSHOP (Exercise 05) — Load external toolset modules ───────────────
    # Import domain toolsets from the tools/ directory.
    # Each module exports a make_*_tools(inbox, outbox, log_callback) factory.
    # Use try/except ImportError to silently skip modules that don't exist yet —
    # this lets you add toolsets incrementally without breaking the harness.
    extra_tools: list = []

    try:
        from tools.csv_tools import make_csv_tools       # noqa: PLC0415
        extra_tools.extend(make_csv_tools(inbox, outbox, log_callback))
        log.debug("Loaded CSV toolset")
    except ImportError:
        pass   # tools/csv_tools.py not present — skip silently

    try:
        from tools.report_tools import make_report_tools  # noqa: PLC0415
        extra_tools.extend(make_report_tools(inbox, outbox, log_callback))
        log.debug("Loaded report toolset")
    except ImportError:
        pass
    # ─────────────────────────────────────────────────────────────────────────

    return [strands_tool(fn) for fn in base_tools] + extra_tools
```

### 5. Write an instruction that uses the new tools

```markdown
# Task: CSV Analysis with Custom Tools

Read sample_data.csv from the inbox.

Step 1: Use csv_schema to understand the structure.
Step 2: Use csv_group_by to count employees per department.
Step 3: Use csv_to_json to get all employee records.
Step 4: Write a Markdown report to `outbox/report.md` with:
  ## Executive Summary
  ## Findings (include the department counts table)
  ## Conclusion
Step 5: Use add_report_header to add metadata to the report.
Step 6: Use validate_markdown_report to confirm the structure is correct.
```

Restart `web_app.py` and click **Run Agent**.  Watch for `[tool_use]` lines
using `csv_schema`, `csv_group_by`, etc. in the log stream.

### 6. Unit-test a toolset

Because tools are plain Python, you can test them independently.
Create `tests/test_csv_tools.py`:

```python
import tempfile
from pathlib import Path
from tools.csv_tools import make_csv_tools

def _noop(**kwargs): pass   # dummy log_callback for tests

def test_csv_schema():
    with tempfile.TemporaryDirectory() as d:
        inbox  = Path(d) / "inbox";  inbox.mkdir()
        outbox = Path(d) / "outbox"; outbox.mkdir()
        (inbox / "data.csv").write_text("name,dept\nAlice,Eng\nBob,HR\n")

        tools   = {t.__name__: t for t in make_csv_tools(inbox, outbox, _noop)}
        result  = tools["csv_schema"]("data.csv")
        assert "name" in result
        assert "Rows: 2" in result

def test_csv_group_by():
    with tempfile.TemporaryDirectory() as d:
        inbox  = Path(d) / "inbox";  inbox.mkdir()
        outbox = Path(d) / "outbox"; outbox.mkdir()
        (inbox / "data.csv").write_text("name,dept\nAlice,Eng\nBob,HR\nCarol,Eng\n")

        tools  = {t.__name__: t for t in make_csv_tools(inbox, outbox, _noop)}
        import json
        counts = json.loads(tools["csv_group_by"]("data.csv", "dept"))
        assert counts["Eng"] == 2
        assert counts["HR"]  == 1
```

Run with:
```bash
python -m pytest tests/test_csv_tools.py -v
```

---

## Organising toolsets for a team

| Scenario | Recommendation |
|----------|---------------|
| Tools used in one project | Inline in `_make_tools()` |
| Tools shared across 2–3 projects | `tools/` module in the project repo |
| Tools shared across an organisation | Published Python package |
| Tools that require secrets or config | Pass config via factory function args |
| Tools with heavy dependencies | Lazy import inside the tool function |

---

## Reflection questions

1. The toolset modules use factory functions (`make_csv_tools(inbox, outbox, log_callback)`)
   rather than module-level decorated functions.  Why?  What would break if you
   used a module-level global `INBOX` variable instead?

2. The `try/except ImportError` pattern silently skips missing toolsets.
   What are the risks of silent degradation?  When would you prefer a hard failure?

3. The Strands harness requires `log_callback` in every tool.  The ADK harness
   got tool-result visibility from framework `Event` objects instead.  Which
   approach is easier to test?  Which makes the tool functions simpler?

4. Could you write a toolset that is conditionally loaded only when a specific
   payload file type (e.g. `.xlsx`) exists in the inbox?  How would you detect
   this in `_make_tools()`?
