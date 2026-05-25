# Exercise 03 — Add a Simple Tool

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Add a new tool to the harness so the agent gains a capability it didn't have
before. You will implement a `word_count` tool that counts words in a string.

---

## Background

Tools are the agent's interface to the outside world. Each tool:
- Has a **name** (what the agent calls it)
- Has a **description** (what the agent thinks it does)
- Has **parameters** (typed inputs)
- Returns a **result** (text the agent reads and acts on)

The agent decides *when* and *how* to call tools autonomously. Your job is
just to define what the tool does.

---

## Steps

### 1. Open `agent_harness.py`

Find the section marked:

```python
# WORKSHOP EXERCISE 3 — Add Custom Tools
```

### 2. Add a word count tool

Paste the following code **above** the `CUSTOM_TOOLS = []` line:

```python
@tool(
    "word_count",
    "Count the number of words, lines, and characters in a text string.",
    {"text": str},
)
async def word_count(args: dict) -> dict:
    text   = args["text"]
    words  = len(text.split())
    lines  = len(text.splitlines())
    chars  = len(text)
    result = f"Words: {words}\nLines: {lines}\nCharacters: {chars}"
    return {"content": [{"type": "text", "text": result}]}
```

### 3. Register the tool

Update `CUSTOM_TOOLS` and `CUSTOM_TOOL_NAMES`:

```python
CUSTOM_TOOLS      = [word_count]
CUSTOM_TOOL_NAMES = ["mcp__agent-tools__word_count"]
```

### 4. Write an instruction that uses the tool

Create a new `instruction.md`:

```markdown
# Task: Word Count Report

For each file in the inbox (excluding instruction.md):
1. Read the file content.
2. Use the `word_count` tool to count words, lines, and characters.
3. Add a row to a Markdown table in `outbox/word_counts.md`:
   | Filename | Words | Lines | Characters |
   |----------|-------|-------|------------|

Write DONE as the last line when all files are counted.
```

### 5. Restart the app and run

If running locally:
```bash
ANTHROPIC_API_KEY=... python web_app.py
```

If using the container:
```bash
./run.sh
```

Click **▶ Run Agent**. Check the log — do you see `[tool_use] word_count`?

Check the outbox for `word_counts.md`.

---

## Going further

Try implementing one of these tools:

### A. Timestamp tool

```python
@tool(
    "current_timestamp",
    "Return the current UTC date and time as an ISO 8601 string.",
    {},
)
async def current_timestamp(_args: dict) -> dict:
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    return {"content": [{"type": "text", "text": ts}]}
```

### B. URL fetch tool  *(requires: `pip install httpx`)*

```python
@tool(
    "fetch_url",
    "Fetch the text content of a public URL (max 4000 chars).",
    {"url": str},
)
async def fetch_url(args: dict) -> dict:
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get(args["url"], timeout=15, follow_redirects=True)
    text = r.text[:4000]
    return {"content": [{"type": "text", "text": text}]}
```

Then write an instruction:
```markdown
Use fetch_url to download the Wikipedia article for "Python (programming language)".
Summarise the first three paragraphs in outbox/python_summary.md.
Write DONE when done.
```

---

## Reflection questions

1. What happens if the agent calls a tool that isn't in `CUSTOM_TOOL_NAMES`?
   Try removing it from the list and re-running.

2. What are the security implications of a `fetch_url` tool? What constraints
   would you add to a production version?

3. How would you make a tool that calls an external API with authentication?
   Where would you store the API credentials?

4. The `word_count` tool receives text as a parameter. Could the agent abuse this
   to send data *out* of the container? How would you prevent it?

---

## Key takeaways

- Adding a tool = defining a Python function + registering it in two lists.
- The agent decides when to use your tool — you only control *what* it can do.
- Tool descriptions matter: write them clearly so the agent understands the tool's purpose.
- Every tool is a potential security boundary — validate inputs carefully.
