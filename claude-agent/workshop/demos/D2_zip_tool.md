# Demo D2 — Tool Calling: Safe Zip Inspection

**Demo type:** Live demonstration | **Time:** ~10 min

---

## What this demonstrates

1. **Tool calling**: the agent uses a custom tool to inspect a zip archive
2. **Agent autonomy**: the agent decides to *reject* suspicious content — no
   human involvement
3. **Security pattern**: inspect before extract (never auto-run uploaded files)

---

## Setup: add a zip inspection tool

Add to `agent_harness.py`:

```python
@tool(
    "inspect_zip",
    "List the contents of a zip file without extracting it. "
    "Returns a JSON array of {name, size, is_executable} objects.",
    {"path": str},
)
async def inspect_zip(args: dict) -> dict:
    import json
    import zipfile
    from pathlib import Path

    # Path must be in the inbox
    rel    = args["path"]
    target = (INBOX_DIR / rel).resolve()
    if not str(target).startswith(str(INBOX_DIR.resolve())):
        raise ValueError(f"Path traversal denied: {rel}")

    SUSPICIOUS_EXTENSIONS = {".exe", ".sh", ".bat", ".cmd", ".ps1", ".vbs",
                              ".dll", ".so", ".dylib", ".msi", ".pkg"}

    if not target.exists():
        raise FileNotFoundError(f"Not found: {rel}")

    results = []
    with zipfile.ZipFile(target, "r") as zf:
        for info in zf.infolist():
            ext = Path(info.filename).suffix.lower()
            results.append({
                "name":           info.filename,
                "size":           info.file_size,
                "is_executable":  ext in SUSPICIOUS_EXTENSIONS,
            })

    return {"content": [{"type": "text", "text": json.dumps(results, indent=2)}]}


@tool(
    "extract_zip",
    "Extract a zip file to the outbox. Only call this after inspect_zip "
    "confirms no suspicious files are present.",
    {"path": str},
)
async def extract_zip(args: dict) -> dict:
    import zipfile

    rel    = args["path"]
    target = (INBOX_DIR / rel).resolve()
    if not str(target).startswith(str(INBOX_DIR.resolve())):
        raise ValueError(f"Path traversal denied: {rel}")

    SUSPICIOUS_EXTENSIONS = {".exe", ".sh", ".bat", ".cmd", ".ps1", ".vbs",
                              ".dll", ".so", ".dylib", ".msi", ".pkg"}

    with zipfile.ZipFile(target, "r") as zf:
        for info in zf.infolist():
            from pathlib import Path as P
            ext = P(info.filename).suffix.lower()
            if ext in SUSPICIOUS_EXTENSIONS:
                raise ValueError(
                    f"Extraction refused: archive contains suspicious file '{info.filename}'"
                )
        zf.extractall(OUTBOX_DIR / "extracted")

    return {"content": [{"type": "text", "text": f"Extracted {rel} to outbox/extracted/"}]}
```

**Note:** You'll need to pass `INBOX_DIR` into the tool. One way is to use a
closure (wrap in `make_tools()`) — see how the existing tools access `inbox_dir`.

---

## Instruction: safe zip

```markdown
# Task: Inspect and Extract Zip

A zip file has been uploaded to the inbox. Before extracting anything:

1. Use `list_inbox_files` to find the zip file.
2. Use `inspect_zip` to list all files inside the zip.
3. Check if any files have suspicious extensions (.exe, .sh, .bat, etc.).
4. If ANY suspicious files are found:
   - Write a warning to `outbox/REJECTED.md` explaining which files were suspicious.
   - Do NOT call extract_zip.
5. If all files are safe:
   - Call `extract_zip` to extract the archive.
   - List the extracted files in `outbox/extracted_files.md`.

Write DONE when finished.
```

---

## Demo: clean zip

Create a clean zip:
```bash
mkdir demo_zip
echo "id,value" > demo_zip/data.csv
echo "1,100" >> demo_zip/data.csv
zip clean_data.zip demo_zip/
cp clean_data.zip inbox/
```

Upload `clean_data.zip` and run the agent. It should extract successfully.

---

## Demo: suspicious zip

```bash
mkdir evil_zip
echo "harmless csv" > evil_zip/data.csv
touch evil_zip/malware.exe
zip suspicious.zip evil_zip/
cp suspicious.zip inbox/
```

Upload `suspicious.zip` and run. The agent should:
1. Inspect and find `malware.exe`
2. Write `REJECTED.md` explaining the refusal
3. NOT call `extract_zip`

---

## Discussion points

- **Autonomous decision making**: the agent decides to reject the file based on
  the inspection result — this is the "agent autonomy" concept.
- **Tool as safety boundary**: `extract_zip` has its own security check, so even
  if the agent ignores the instruction to inspect first, it cannot extract
  suspicious files.
- **Defence in depth**: the container sandbox + tool restrictions + agent
  instruction + tool-level validation = multiple layers of protection.
- **MCP in production**: in a real system, `inspect_zip` might be an external
  MCP server provided by a security vendor.
