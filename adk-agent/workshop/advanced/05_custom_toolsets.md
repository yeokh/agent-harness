# Exercise 05 — Build Custom Toolsets

**Track:** Advanced | **Time:** ~30 min

---

## Objective

Organise related tool functions into domain-specific Python modules, load them
conditionally in `adk_agent.py`, and understand when to use modules vs. inline
tool functions.

---

## Background

### The toolset problem

As you add more tools in Exercise 03, `_make_tools()` grows long.  When tools
share helper logic (e.g. CSV parsing functions used by three different tools),
duplicating them inline becomes a maintenance problem.

The solution is to group related tools into **toolset modules** — plain Python
files in a `tools/` directory.  `_make_tools()` imports and combines them.

### How this differs from pi skills

In the pi-cli-agent, capability was extended by writing Markdown instructions
in `skill.md`.  The agent read those instructions as text and used its own
reasoning to apply them.

In the ADK agent, capability is extended by writing Python functions.  The
difference is fundamental:

| Dimension | pi skill.md | ADK Python toolset |
|-----------|-------------|-------------------|
| Execution | Interpreted by the LLM | Run directly on the host |
| Reliability | Varies — LLM may misinterpret | Deterministic Python |
| Portability | Markdown file, no dependencies | Requires Python + imports |
| Testability | Hard to unit-test | Standard pytest |
| Discoverability | Agent reads the text | Type annotations + docstrings |
| Adding host capabilities | Via bash instructions | Native Python or subprocess |

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
CSV Toolset
-----------
Domain-specific tools for reading and transforming CSV files.
Imported conditionally by _make_tools() in adk_agent.py.
"""

import csv
import json
from pathlib import Path


def make_csv_tools(inbox: Path, outbox: Path) -> list:
    """Return CSV-specific tool functions bound to the given paths."""
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
        of an unknown CSV without loading all rows.

        Args:
            filepath: Path to the CSV file (relative to inbox, or absolute).

        Returns:
            Comma-separated column names and a row count, or an error.
        """
        target = _resolve(filepath)
        if target is None:
            return f"File not found: {filepath}"
        try:
            with target.open(encoding="utf-8") as f:
                reader  = csv.DictReader(f)
                columns = reader.fieldnames or []
                rows    = sum(1 for _ in reader)
            return f"Columns: {', '.join(columns)}\nRows: {rows}"
        except Exception as exc:
            return f"Error reading {filepath}: {exc}"

    def csv_to_json(filepath: str) -> str:
        """Parse a CSV file and return all rows as a JSON array.

        Each row becomes a JSON object with column names as keys.  Use when
        the task requires structured manipulation of tabular data.

        Args:
            filepath: Path to the CSV file (relative to inbox, or absolute).

        Returns:
            JSON string of all rows, or an error message.
        """
        target = _resolve(filepath)
        if target is None:
            return f"File not found: {filepath}"
        try:
            with target.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            return json.dumps(rows, indent=2)
        except Exception as exc:
            return f"Error parsing {filepath}: {exc}"

    def csv_group_by(filepath: str, column: str) -> str:
        """Group CSV rows by a column and return counts as JSON.

        Useful for quick frequency analysis without loading the full dataset.

        Args:
            filepath: Path to the CSV file.
            column:   Name of the column to group by.

        Returns:
            JSON object mapping each unique value to its row count.
        """
        target = _resolve(filepath)
        if target is None:
            return f"File not found: {filepath}"
        try:
            from collections import Counter
            with target.open(encoding="utf-8") as f:
                counts = Counter(row.get(column, "") for row in csv.DictReader(f))
            return json.dumps(dict(counts.most_common()), indent=2)
        except Exception as exc:
            return f"Error: {exc}"

    return [csv_schema, csv_to_json, csv_group_by]
```

### 3. Write a report toolset module

Create `tools/report_tools.py`:

```python
"""
Report Toolset
--------------
Tools for formatting and validating Markdown reports.
"""

import re
from pathlib import Path


def make_report_tools(inbox: Path, outbox: Path) -> list:
    """Return report-formatting tool functions."""
    outbox_r = outbox.resolve()

    def validate_markdown_report(filepath: str) -> str:
        """Check that a Markdown report has the required sections.

        Verifies that the file contains at least one level-2 heading for
        'Executive Summary', 'Findings', and 'Conclusion'.  Use this after
        writing a report to confirm it meets the standard structure.

        Args:
            filepath: Path to the Markdown file (relative to outbox).

        Returns:
            'VALID' if all sections present, or a list of missing sections.
        """
        target = (outbox_r / filepath).resolve()
        if not str(target).startswith(str(outbox_r)) or not target.is_file():
            return f"File not found in outbox: {filepath}"
        try:
            text     = target.read_text(encoding="utf-8")
            required = ["Executive Summary", "Findings", "Conclusion"]
            missing  = [s for s in required if f"## {s}" not in text]
            if missing:
                return f"Missing sections: {', '.join(missing)}"
            return "VALID: all required sections present"
        except Exception as exc:
            return f"Error: {exc}"

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
        from datetime import date
        target = (outbox_r / filepath).resolve()
        if not str(target).startswith(str(outbox_r)) or not target.is_file():
            return f"File not found in outbox: {filepath}"
        try:
            original = target.read_text(encoding="utf-8")
            header   = (
                f"**Date:** {date.today()}  \n"
                f"**Source files:** {source_files}  \n"
                f"**Agent model:** {model}  \n\n"
                "---\n\n"
            )
            target.write_text(header + original, encoding="utf-8")
            return f"Header added to {filepath}"
        except Exception as exc:
            return f"Error: {exc}"

    return [validate_markdown_report, add_report_header]
```

### 4. Load toolsets conditionally in `adk_agent.py`

Open `adk_agent.py` and update the `# WORKSHOP PLACEHOLDER` comment and
the `return` line at the bottom of `_make_tools()`:

```python
    # ── WORKSHOP (Exercise 05) — Load external toolset modules ───────────────
    # Import domain toolsets from the tools/ directory.
    # Each module exposes a make_*_tools(inbox, outbox) factory function.
    # You can make loading conditional on inbox contents, environment vars,
    # or simply always include all toolsets.
    extra_tools: list = []

    try:
        from tools.csv_tools import make_csv_tools       # noqa: PLC0415
        extra_tools.extend(make_csv_tools(inbox, outbox))
        log.debug("Loaded CSV toolset (%d tools)", len(extra_tools))
    except ImportError:
        pass  # tools/csv_tools.py not present — skip silently

    try:
        from tools.report_tools import make_report_tools  # noqa: PLC0415
        report_tools = make_report_tools(inbox, outbox)
        extra_tools.extend(report_tools)
        log.debug("Loaded report toolset (%d tools)", len(report_tools))
    except ImportError:
        pass
    # ─────────────────────────────────────────────────────────────────────────

    return [read_file, write_file, list_files, run_bash] + extra_tools
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

Because tools are plain Python, you can test them independently.  Create
`tests/test_csv_tools.py`:

```python
import csv
import tempfile
from pathlib import Path
from tools.csv_tools import make_csv_tools

def test_csv_schema():
    with tempfile.TemporaryDirectory() as d:
        inbox  = Path(d) / "inbox"
        outbox = Path(d) / "outbox"
        inbox.mkdir(); outbox.mkdir()

        csv_file = inbox / "data.csv"
        csv_file.write_text("name,dept\nAlice,Eng\nBob,HR\n")

        tools = {t.__name__: t for t in make_csv_tools(inbox, outbox)}
        result = tools["csv_schema"]("data.csv")
        assert "name" in result
        assert "Rows: 2" in result

def test_csv_group_by():
    with tempfile.TemporaryDirectory() as d:
        inbox  = Path(d) / "inbox"
        outbox = Path(d) / "outbox"
        inbox.mkdir(); outbox.mkdir()

        csv_file = inbox / "data.csv"
        csv_file.write_text("name,dept\nAlice,Eng\nBob,HR\nCarol,Eng\n")

        tools   = {t.__name__: t for t in make_csv_tools(inbox, outbox)}
        result  = tools["csv_group_by"]("data.csv", "dept")
        import json
        counts  = json.loads(result)
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
| Tools shared across an organisation | Published Python package (`pip install my-org-tools`) |
| Tools that require secrets or config | Pass config via factory function args, not global state |
| Tools with heavy dependencies | Lazy import inside the tool function to keep startup fast |

---

## Reflection questions

1. The toolset modules use factory functions (`make_csv_tools(inbox, outbox)`)
   instead of module-level functions.  Why?  What would break if you used
   `inbox` as a module-level global variable instead?

2. The `try/except ImportError` pattern silently skips missing toolsets.
   What are the risks of silent degradation?  When would you prefer a hard
   failure instead?

3. You can now unit-test tools independently of the agent.  Write a test for
   `validate_markdown_report` that checks it correctly detects a missing
   "Findings" section.

4. Compare Exercise 03 (adding a single tool inline) with Exercise 05 (toolset
   modules).  What complexity threshold would make you switch from inline to
   a module?

5. If you published `tools/csv_tools.py` as a pip package, what would you need
   to add to make it production-ready?  (Think: error handling, logging, type
   hints, versioning, CI.)
