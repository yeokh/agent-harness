# Exercise 03 — Add a Python Tool

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Learn how Strands `@tool` functions work and extend the agent's capabilities
by adding a new tool to `strands_agent.py` — without changing `web_app.py`
or the web UI.

---

## Background

### What is a Strands tool?

In Amazon Strands, a **tool** is a Python function decorated with `@tool`.
The framework inspects the function and automatically builds a JSON schema for the LLM:

```
Python function with @tool              What Strands gives the LLM
─────────────────────                   ──────────────────────────
@tool                                   name:        "word_count"
def word_count(filepath: str) → str:    description: "Count words in a file."
    """Count words in a file."""         parameters:  {filepath: string}
    ...
```

The LLM decides *when* to call a tool based on:
1. The **function name** — should be a clear verb phrase
2. The **docstring** — the LLM reads this to understand when and how to use it
3. The **type annotations** — define what arguments the LLM must supply

The function's **return value** must always be a `str` — it becomes the tool
result that the LLM reads before continuing the agentic loop.

### Strands closures — applying @tool after definition

In `_make_tools()`, tools are inner functions (closures) that capture `inbox_r`,
`outbox_r`, and `log_callback`.  The `@tool` decorator is applied *after* the
function is defined using `strands_tool(fn)`:

```python
from strands import tool as strands_tool

def _make_tools(inbox, outbox, log_callback):
    inbox_r = inbox.resolve()

    def my_tool(filepath: str) -> str:
        """Tool description the LLM reads."""
        log_callback(f"[tool_use] my_tool(filepath={filepath!r})")
        # ...
        return "result"

    return [strands_tool(my_tool), ...]   # ← apply @tool here
```

This is equivalent to `@tool` at the top of a module-level function, but lets
the closure capture the inbox/outbox paths and log_callback.

---

## Steps

### 1. Understand the tool pattern

Open `strands_agent.py` and find `_make_tools()`.  Notice that each tool:
- Is defined as a nested function (closure) capturing `inbox_r`, `outbox_r`,
  `log_callback` — no global state needed
- Has a clear one-line docstring (the LLM reads this)
- Has type-annotated parameters
- Logs its call with `log_callback(f"[tool_use] ...")` at the start
- Logs its result with `log_callback(f"[result] ...")` before returning
- Returns a `str` in all code paths (including error cases)
- Is wrapped with `strands_tool()` in the final return list

### 2. Add a `word_count` tool

Inside `_make_tools()`, in the `# ── WORKSHOP PLACEHOLDER (Exercise 03)` section,
add this function:

```python
def word_count(filepath: str) -> str:
    """Count lines, words, and characters in a text file.

    Useful for quickly understanding the size and structure of a text payload
    before deciding how to process it.

    Args:
        filepath: Path to the file (relative to inbox, or absolute).

    Returns:
        A summary string with line, word, and character counts.
    """
    log_callback(f"[tool_use] word_count(filepath={filepath!r})")
    candidates = [
        Path(filepath),
        inbox_r / filepath,
        outbox_r / filepath,
    ]
    for c in candidates:
        resolved = c.resolve()
        if _in_allowed(resolved) and resolved.is_file():
            try:
                text  = resolved.read_text(encoding="utf-8")
                lines = text.count("\n")
                words = len(text.split())
                chars = len(text)
                result = f"{filepath}: {lines} lines, {words} words, {chars} chars"
                log_callback(f"[result] word_count: {result}")
                return result
            except Exception as exc:
                result = f"Error reading {filepath}: {exc}"
                log_callback(f"[result] word_count: {result}")
                return result
    result = f"File not found: {filepath}"
    log_callback(f"[result] word_count: {result}")
    return result
```

Then add it to `base_tools` in the PLACEHOLDER section:

```python
base_tools.append(word_count)
```

### 3. Write an instruction that uses the new tool

Use the browser editor to replace `inbox/instruction.md` with:

```markdown
# Task: File Statistics

For each .txt file in the inbox (file1.txt, file2.txt, file3.txt):
1. Use the word_count tool to get its size statistics.
2. Read the file content.

Then write `outbox/file_stats.md` with a Markdown table:

| Filename | Lines | Words | Characters | Content |
|----------|-------|-------|------------|---------|
| ...      | ...   | ...   | ...        | ...     |

Sort rows alphabetically by filename.
```

### 4. Restart and run

Because you modified `strands_agent.py`, restart the server:

```bash
# Ctrl+C to stop, then:
python web_app.py
```

Open the browser, click **Run Agent**, and watch the log stream.  You should see:

```
[tool_use] word_count(filepath='file1.txt')
[result] word_count: file1.txt: 1 lines, 1 words, 5 chars
```

Check `outbox/file_stats.md` in the Outbox panel.

### 5. Add a `convert_csv_to_json` tool

For a more substantial tool, add this in the PLACEHOLDER section:

```python
def convert_csv_to_json(filepath: str) -> str:
    """Parse a CSV file and return its contents as a JSON string.

    Converts the CSV at the given path into a JSON array of objects,
    one object per row with column names as keys.  Use this when the
    task requires working with structured tabular data.

    Args:
        filepath: Path to the CSV file (relative to inbox, or absolute).

    Returns:
        JSON string of the parsed rows, or an error message.
    """
    import csv as _csv, json as _json  # noqa: E401
    log_callback(f"[tool_use] convert_csv_to_json(filepath={filepath!r})")

    candidates = [Path(filepath), inbox_r / filepath]
    for c in candidates:
        resolved = c.resolve()
        if _in_allowed(resolved) and resolved.is_file():
            try:
                with resolved.open(encoding="utf-8") as f:
                    rows = list(_csv.DictReader(f))
                result = _json.dumps(rows, indent=2)
                log_callback(f"[result] convert_csv_to_json: parsed {len(rows)} rows")
                return result
            except Exception as exc:
                result = f"Error parsing CSV {filepath}: {exc}"
                log_callback(f"[result] convert_csv_to_json: {result}")
                return result
    result = f"File not found: {filepath}"
    log_callback(f"[result] convert_csv_to_json: {result}")
    return result
```

Add it to `base_tools`:

```python
base_tools.extend([word_count, convert_csv_to_json])
```

Now update `instruction.md` to ask the agent to use this tool:

```markdown
# Task: CSV to JSON

Read sample_data.csv from the inbox using the convert_csv_to_json tool.
Write the raw JSON result to `outbox/employees.json`.
Then write a brief summary of what columns and rows were found to
`outbox/summary.md`.
```

### 6. Explore tool call patterns in the log

After the run, look at the log stream carefully.  Notice:

- The agent first calls `list_files` to discover what is available
- Then it calls your new tool
- The `[result]` line shows the return value (truncated in the log)
- If the tool returns an error string, the agent typically tries an alternative

---

## Design guidelines for good Strands tools

| Guideline | Why |
|-----------|-----|
| Short, verb-phrase name | The LLM picks tools by name — be specific |
| One-line docstring describing the use case | This is what the LLM reads to decide when to call it |
| `Args:` section in the docstring | Tells the LLM what each parameter does |
| All paths return `str` | Strands requires string returns; never raise, never return `None` |
| Validate paths with `_in_allowed()` | Prevent the tool from reading outside inbox/outbox |
| Log call + result via `log_callback` | Provides the `[tool_use]` / `[result]` entries in the terminal |
| Descriptive error messages | The agent reads errors and may retry differently |

---

## Reflection questions

1. In step 2, the docstring says "Useful for quickly understanding the size
   and structure…"  Why is the intended use case important?  What happens if
   you write a vague docstring like "Count stuff"?

2. The `word_count` tool logs with `log_callback` directly.  In the ADK version,
   tool results were captured from framework `Event` objects instead.  What are
   the trade-offs of each approach?

3. Compare adding `word_count` here to adding the same capability in a prompt-only
   harness using `instruction.md`.  Which approach is easier?  Which is safer?

4. What would happen if your tool returned a very large string (e.g. a 100 KB
   JSON file)?  Check what Strands does when the tool result is very long — does
   it truncate it before sending to the LLM?

5. Could you write a tool that makes an HTTP request to an external API?
   What security and reliability concerns would this introduce?

---

## Key takeaways

- Strands tools are Python functions: name, docstring, and type annotations
  are what the LLM reads to understand how to use them.
- Apply `@tool` (or `strands_tool()`) to turn a Python function into a tool —
  even closures work as long as they have proper docstrings and type hints.
- Adding a tool is a code change: add the function, add it to `base_tools`, restart.
- Embedding logging in each tool (rather than parsing framework events) gives
  the same visibility with simpler code.
- Good tool design matters: clear names and docstrings produce better agent
  behaviour than clever implementations.
