# Exercise 02 — Modify Task Instructions

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Learn how changes to `instruction.md` change agent behaviour, explore how
model choice affects output quality and speed, and practise using the new
**in-browser file editor** to iterate without uploading files.

---

## Background

In this harness, the agent's task is defined entirely by `inbox/instruction.md`.
The file is read by the agent at runtime using the `read_file` tool — you can
change it between runs without restarting the server or editing any Python.

The same agent, the same tools, the same system prompt — but a completely
different outcome depending on what you write in `instruction.md`.

### Two ways to edit instruction.md

**Option A — In-browser editor (new):**
1. Click `instruction.md` in the Inbox panel
2. Click **✏ Edit** in the viewer toolbar
3. Type your changes in the text area
4. Click **💾 Save** — changes are written immediately to the inbox file

**Option B — Upload:**
Save the file locally, then drag-and-drop it into the Inbox panel
(or click _Upload file_).

---

## Steps

### 1. Add a CSV payload file

First upload a data file the agent can process.  Create `inbox/sample_data.csv`
with this content (save it locally and drag it into the Inbox panel, or create
it with the New File button):

```csv
name,department,salary,years_experience,location
Alice Chen,Engineering,95000,5,Singapore
Bob Smith,Marketing,72000,3,London
Carol Jones,Engineering,110000,8,New York
David Kim,HR,65000,2,Singapore
Eve Wilson,Marketing,85000,6,London
Frank Lee,Engineering,98000,4,Singapore
Grace Park,HR,70000,4,New York
Henry Brown,Marketing,78000,5,London
```

### 2. Clear the outbox

Click **Clear Outbox** in the sidebar, or from the terminal:

```bash
rm -f outbox/*.md outbox/*.csv outbox/*.json outbox/*.txt outbox/*.html outbox/*.log
```

### 3. Try a department report task

Click `instruction.md` in the Inbox panel, click **✏ Edit**, and replace the
content with:

```markdown
# Task: Department Report

Read the file sample_data.csv in the inbox folder.

Produce two output files in the outbox:

1. `outbox/by_department.md` — a Markdown table with one row per department
   showing: Department, Headcount, Average Salary, Average Years Experience.
   Sort rows by headcount descending.

2. `outbox/top_earners.md` — a list of the top 3 earners across all departments
   with their Name, Department, Salary, and Location.

Add a 2–3 sentence interpretation below each table.
```

Click **💾 Save**, then click **Run Agent**.  Compare the output to the ASCII
art from Exercise 01.  The agent produced completely different files from the
same infrastructure because only the instructions changed.

### 4. Try an open-ended analysis task

Click **✏ Edit** on `instruction.md` and replace with:

```markdown
# Task: Open-Ended Analysis

You are a data analyst.  Look at the files in the inbox folder and decide
for yourself what the most interesting insights are.

Produce a single report in `outbox/insights.md` with at least three findings
you consider noteworthy.  Include a brief methodology note.
```

Click **💾 Save** and **Run Agent**.  Observe what the agent chooses to focus on.

### 5. Try a structured JSON export

```markdown
# Task: JSON Export

Read sample_data.csv from the inbox.

Write `outbox/employees.json` containing an array of employee objects.
Each object must have exactly these keys:
  name, department, salary, years_experience, location

Then write `outbox/stats.json` with:
  total_employees, average_salary, departments (array of unique names)

Use run_bash with a Python one-liner to compute the averages rather than
doing arithmetic in your reasoning.
```

Inspect the JSON from the Outbox panel, or from the terminal:

```bash
cat outbox/employees.json | python3 -m json.tool
```

### 6. Compare instruction precision

Run these two versions back-to-back and compare results:

**Vague:**
```markdown
Summarise the data.
```

**Precise:**
```markdown
Read `inbox/sample_data.csv` and write `outbox/summary_table.md` containing
a Markdown table with one row per department showing:
headcount, min salary, max salary, average salary (rounded to nearest $1000).
Sort rows by headcount descending.  Include no other content.
```

The precise version produces a deterministic, auditable result every time.
The vague version leaves interpretation to the model — useful for exploration,
risky for production pipelines where consistency matters.

### 7. Compare models

Try the same instruction with two different models from the dropdown.  Observe:
- Which is faster?
- Which writes better prose in the summary sections?
- Do they compute the same salary figures?
- Does model choice affect how many tool calls are made?

---

## Understanding instruction quality

| Instruction quality | Result |
|--------------------|--------|
| Vague | Agent interprets freely; output varies between runs |
| Precise paths + schema | Deterministic file names and structure |
| Explicit computation method | Agent uses `run_bash` Python instead of mental arithmetic |
| Contradicts system prompt | Agent follows system prompt (fixed) over instruction (runtime) |

---

## Reflection questions

1. The in-browser editor lets you change `instruction.md` between runs without
   restarting the server.  How does this compare to the workflow in a text editor?
   When would each approach be more convenient?

2. In step 4 (open-ended task), did the agent find insights you expected?
   Did it miss anything obvious in the CSV?

3. How would you write an instruction that is both flexible (works with any
   CSV schema) and precise (produces a consistent output structure)?

4. The agent's `_SYSTEM_PROMPT` (in `strands_agent.py`) says "only write to
   outbox".  What happens if `instruction.md` asks it to write a file
   somewhere else?  Try it and observe whether the tool's path check or the
   system prompt constraint fires first.

5. Could you instruct the agent to read its own source code (`strands_agent.py`)?
   What would the `read_file` tool return?  Is this a security concern?

---

## Key takeaways

- `instruction.md` is the *what*; `_SYSTEM_PROMPT` is the *how*.
- The in-browser editor lets you iterate on instructions without leaving the UI.
- Precise instructions produce reliable, auditable outputs.
- Open-ended instructions reveal what the model considers important — useful
  for exploration, risky for production.
- Model choice affects speed, cost, and output quality independently of instructions.
- Instructions are read by the agent as data — prompt injection is a real attack
  surface (covered in Exercise 04).
