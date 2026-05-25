# Exercise 03 — Add a Python Tool

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Learn how ADK tool functions work and extend the agent's capabilities by
adding a new tool to `adk_agent.py` — without changing `web_app.py` or the
web UI.

---

## Background

### What is an ADK tool?

In Google ADK, a **tool** is an ordinary Python function.  The framework
inspects the function and automatically builds a JSON schema for the LLM:

```
Python function                     What ADK gives the LLM
──────────────                      ──────────────────────
def word_count(filepath: str) → str   name:        "word_count"
    """Count words in a file."""       description: "Count words in a file."
                                       parameters:  {filepath: string}
```

The LLM decides *when* to call a tool based on:
1. The **function name** — should be a clear verb phrase
2. The **docstring** — the LLM reads this to understand when and how to use it
3. The **type annotations** — define what arguments the LLM must supply

The function's **return value** must be a `str` — it becomes the tool result
that the LLM reads before continuing.

### Comparing tool approaches

| Approach | In pi-cli-agent | In ADK agent |
|----------|----------------|--------------|
| Add a new capability | Write instructions in `skill.md` | Write a Python function in `adk_agent.py` |
| Restart required | No | Yes |
| Host system access | Via bash instructions | Via `run_bash` tool or native Python |
| Portable across machines | Yes (Markdown file) | Requires Python + dependencies |
| Type-safe schema | No | Yes (via type annotations) |

---

## Steps

### 1. Understand the tool pattern

Open `adk_agent.py` and find `_make_tools()`.  Notice that each tool:
- Is defined as a nested function (a closure) so it can access `inbox_r` and
  `outbox_r` without global state
- Has a clear one-line docstring (the LLM reads this)
- Has type-annotated parameters
- Returns a `str` in all code paths (including error cases)
- Is added to the `return [...]` list at the bottom

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

    Returns:
        A summary string with line, word, and character counts.
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
return [read_file, write_file, list_files, run_bash, word_count]
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

Because you modified `adk_agent.py`, restart the server:

```bash
# Ctrl+C to stop, then:
python web_app.py
```

Open the browser, click **Run Agent**, and watch the log stream.  You should see:

```
[tool_use] word_count(filepath='inbox/file1.txt')
[result] word_count: file1.txt: 1 lines, 1 words, 5 chars
```

Check `outbox/file_stats.md` in the Outbox panel.

### 5. Add a `convert_csv_to_json` tool

For a more substantial tool, add this after `word_count`:

```python
def convert_csv_to_json(filepath: str) -> str:
    """Parse a CSV file and return its contents as a JSON string.

    Converts the first CSV found at the given path into a JSON array of
    objects, one object per row with column names as keys.  Use this when
    the task requires working with structured tabular data.

    Args:
        filepath: Path to the CSV file (relative to inbox, or absolute).

    Returns:
        JSON string of the parsed rows, or an error message.
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
return [read_file, write_file, list_files, run_bash, word_count, convert_csv_to_json]
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
- The `[result]` line shows the first 300 chars of the return value
- If the tool returns an error string, the agent typically tries an alternative

---

## Design guidelines for good tools

| Guideline | Why |
|-----------|-----|
| Short, verb-phrase name | The LLM picks tools by name — be specific |
| One-line docstring describing the use case | This is what the LLM reads to decide when to call it |
| All paths return `str` | ADK requires string returns; never raise, never return None |
| Validate paths with `_in_allowed()` | Prevent the tool from reading outside inbox/outbox |
| Descriptive error messages | The agent reads errors and may retry differently |
| Avoid side effects in read tools | Keep read and write tools separate |

---

## Reflection questions

1. In step 2, the docstring says "Useful for quickly understanding the size
   and structure…"  Why is the intended use case important in the docstring?
   What happens if you write a vague docstring like "Count stuff"?

2. The `word_count` tool imports `Path` and uses the `_in_allowed()` closure.
   What would happen if you added a tool that reads an absolute path like
   `/etc/passwd`?

3. Compare adding `word_count` here to adding the same capability in the
   pi-cli-agent using `skill.md`.  Which approach is easier?  Which is safer?

4. The tool's return value is truncated to 300 chars in the log display
   (`_format_event` in `adk_agent.py`), but the full value is sent to the LLM.
   What could go wrong if a tool returns a very large string (e.g. a 100 KB
   JSON file parsed from CSV)?

5. Could you write a tool that makes an HTTP request to an external API?
   What security and reliability concerns would this introduce?

---

## Key takeaways

- ADK tools are plain Python functions: the name, docstring, and type
  annotations are what the LLM reads to understand how to use them.
- Adding a tool is a code change: add the function, add it to the return list,
  restart the server.
- Good tool design matters: clear names and docstrings produce better agent
  behaviour than clever implementations.
- Tools can import libraries, access the filesystem, and run subprocesses —
  the LLM itself only sees strings in and strings out.
