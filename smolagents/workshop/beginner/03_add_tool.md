# Exercise 03 — Add a Python Tool

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Learn how Smolagents tool functions work and extend the agent's capabilities by
adding a new tool to `smolagent_agent.py` — without changing `web_app.py` or
the web UI.

---

## Background

### What is a Smolagents tool?

In Smolagents, a **tool** is a Python function wrapped with the `@tool` decorator
(or the `tool()` function call).  The framework inspects the function and builds
a schema for the LLM:

```
Python function (+ @tool)                  What Smolagents gives the LLM
──────────────────────────                 ──────────────────────────────
@tool                                      name:        "word_count"
def word_count(filepath: str) -> str:      description: "Count lines, words…"
    """Count lines, words, and chars."""   inputs:      {filepath: {type: string, …}}
    ...                                    output_type: "string"
```

The LLM decides *when* to call a tool based on:
1. The **function name** — should be a clear verb phrase
2. The **docstring** — the LLM reads this to understand when/how to use it
3. The **type annotations** — define what arguments the LLM must supply

### KEY DIFFERENCE from ADK

| Aspect | ADK | Smolagents |
|--------|-----|-----------|
| Tool definition | Plain function, no decoration needed | Must wrap with `@tool` or `tool()` |
| Return type | Any str (raw Python) | Must return `str`; tool() sets `output_type="string"` |
| LLM schema | ADK inspects automatically | Smolagents `tool()` builds the schema |
| Adding to agent | List of plain functions | List of Tool objects |

In this harness, tools are closures inside `_make_tools()`.  Since `@tool` is a
decorator applied at *definition* time and our closures capture runtime paths, we
apply `tool()` as a *function call* after defining the closure:

```python
def word_count(filepath: str) -> str:   # closure — captures inbox_r/outbox_r
    """..."""
    ...

_tool(word_count)   # → converts the closure into a Tool object
```

---

## Steps

### 1. Understand the tool pattern

Open `smolagent_agent.py` and find `_make_tools()`.  Notice that each tool:
- Is defined as a nested function (a closure) capturing `inbox_r` and `outbox_r`
- Has a clear one-line docstring (the LLM reads this)
- Has type-annotated parameters
- Returns a `str` in all code paths (including error cases)
- Is wrapped with `_tool()` in the `return [...]` list

### 2. Add a `word_count` tool

Inside `_make_tools()`, after the `run_bash` function definition and before
the `# WORKSHOP PLACEHOLDER` comment, add:

```python
def word_count(filepath: str) -> str:
    """Count lines, words, and characters in a text file.

    Useful for quickly understanding the size and structure of a text payload
    before deciding how to process it.

    Args:
        filepath: Path to the file (relative to inbox, or absolute).
    """
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
                return f"{filepath}: {lines} lines, {words} words, {chars} chars"
            except Exception as exc:
                return f"Error reading {filepath}: {exc}"
    return f"File not found: {filepath}"
```

Then update the `return` list at the bottom of `_make_tools()`:

```python
return [
    _tool(read_file),
    _tool(write_file),
    _tool(list_files),
    _tool(run_bash),
    _tool(word_count),   # ← add this line
]
```

### 3. Write an instruction that uses the new tool

Replace `inbox/instruction.md` with:

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

Because you modified `smolagent_agent.py`, restart the server:

```bash
# Ctrl+C to stop, then:
python web_app.py
```

Open the browser, click **Run Agent**, and watch the log stream.  You should see:

```
[tool_use] word_count(filepath='file1.txt')
[result] file1.txt: 0 lines, 1 words, 5 chars
```

Check `outbox/file_stats.md` in the Outbox panel.

### 5. Add a `convert_csv_to_json` tool

For a more substantial tool, add this after `word_count`:

```python
def convert_csv_to_json(filepath: str) -> str:
    """Parse a CSV file and return its contents as a JSON string.

    Converts the CSV into a JSON array of objects, one object per row with
    column names as keys.  Use when the task requires structured tabular data.

    Args:
        filepath: Path to the CSV file (relative to inbox, or absolute).
    """
    import csv, json as _json  # noqa: E401

    candidates = [Path(filepath), inbox_r / filepath]
    for c in candidates:
        resolved = c.resolve()
        if _in_allowed(resolved) and resolved.is_file():
            try:
                with resolved.open(encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                return _json.dumps(rows, indent=2)
            except Exception as exc:
                return f"Error parsing CSV {filepath}: {exc}"
    return f"File not found: {filepath}"
```

Add it to the return list:

```python
return [
    _tool(read_file), _tool(write_file), _tool(list_files),
    _tool(run_bash), _tool(word_count), _tool(convert_csv_to_json),
]
```

### 6. Explore tool call patterns in the log

After the run, look carefully at the log:
- The agent first calls `list_files` to discover what is available
- Then it calls your new tool
- The `[result]` line shows the first 300 chars of the return value
- If the tool returns an error string, the agent typically tries an alternative

---

## Design guidelines for good tools

| Guideline | Why |
|-----------|-----|
| Short, verb-phrase name | The LLM picks tools by name — be specific |
| One-line docstring first | This is what the LLM reads to decide when to call it |
| `Args:` section in docstring | Smolagents parses this for parameter descriptions |
| All paths return `str` | tool() requires string returns; never raise, never return None |
| Validate paths with `_in_allowed()` | Prevent reading/writing outside inbox/outbox |
| Descriptive error messages | The agent reads errors and may retry differently |

---

## Reflection questions

1. Why does the docstring's `Args:` section matter for smolagents but not ADK?
   What does the LLM receive differently when arguments are described?

2. The `word_count` tool returns a plain string with counts.  What would happen
   if you returned a Python dict instead?  Would the LLM understand it?

3. Compare `_tool(word_count)` (dynamic application) vs using `@tool` as a class
   decorator.  When would `@tool` as a decorator be simpler?  Why can't we use
   it directly for closures that capture runtime paths?

4. The tool's return value is truncated to 300 chars in the log display
   (`_format_step` in `smolagent_agent.py`), but the full value is sent to the
   LLM.  What could go wrong if a tool returns a very large string?

5. Could you write a tool that makes an HTTP request to an external API?
   What security and reliability concerns would this introduce?

---

## Key takeaways

- Smolagents tools must be `Tool` objects — wrap plain functions with `tool()`.
- The name, docstring (`Args:` section), and type annotations are what the LLM
  reads to understand how and when to use a tool.
- Adding a tool: define the function, wrap with `_tool()`, restart the server.
- The `_tool()` wrapper turns a Python function into a smolagents Tool object
  with `.name`, `.description`, and `.inputs` schema attributes.
- Tools can import libraries, access the filesystem, and run subprocesses —
  the LLM sees only strings in and strings out.
