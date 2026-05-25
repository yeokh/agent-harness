# Exercise 02 — Modify Task Instructions

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Learn how changes to `instruction.md` change agent behaviour, and explore
how model choice affects output quality, style, and speed.

---

## Background

In this harness, the agent's task is defined entirely by `inbox/instruction.md`.
The file is read by the agent at runtime using the `read_file` tool — you can
change it between runs without restarting the server or editing any Python.

The same agent, the same tools, the same task template — but a completely
different outcome depending on what you write in `instruction.md`.

Upload a new `instruction.md` from the **Inbox** panel (drag-and-drop or the
upload button), or edit it directly on disk, then click **Run Agent**.

**Note for ADK workshop alumni:** This exercise is intentionally identical
to the ADK version.  The takeaway is that `instruction.md` is framework-agnostic
— the same file drives behaviour in both ADK and Smolagents.

---

## Steps

### 1. Add a CSV payload file

Upload `inbox/sample_data.csv` with this content:

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

Click **Clear Outbox** in the sidebar.

### 3. Try a department report task

Replace `inbox/instruction.md` with:

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

Click **Run Agent**.  Compare the output to the ASCII art from Exercise 01.

### 4. Try an open-ended analysis task

```markdown
# Task: Open-Ended Analysis

You are a data analyst.  Look at the files in the inbox folder and decide
for yourself what the most interesting insights are.

Produce a single report in `outbox/insights.md` with at least three findings
you consider noteworthy.  Include a brief methodology note.
```

Click **Run Agent** and observe what the agent chooses to focus on.

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

### 7. Compare models

Try the same instruction with two different models from the dropdown.  Observe:
- Which is faster?
- Which writes better prose in the summary sections?
- Do they compute the same salary figures?

---

## Understanding instruction quality

| Instruction quality | Result |
|--------------------|--------|
| Vague | Agent interprets freely; output varies between runs |
| Precise paths + schema | Deterministic file names and structure |
| Explicit computation method | Agent uses `run_bash` Python instead of mental arithmetic |

---

## Reflection questions

1. What is the difference between writing `instruction.md` and writing a
   prompt in a chat interface?  What extra constraints does the file-processing
   context add?

2. In step 4 (open-ended task), did the agent find insights you expected?
   Did it miss anything obvious in the CSV?

3. How would you write an instruction that is both flexible (works with any
   CSV schema) and precise (produces a consistent output structure)?

4. The agent's `_TASK_TEMPLATE` (in `smolagent_agent.py`) says "only write
   to outbox".  What happens if `instruction.md` asks it to write somewhere else?

5. Could you instruct the agent to read its own source code (`web_app.py`)?
   What would the `read_file` tool return?  Is this a security concern?

---

## Key takeaways

- `instruction.md` is the *what*; `_TASK_TEMPLATE` is the *how*.
- Precise instructions produce reliable, auditable outputs.
- Open-ended instructions reveal what the model considers important.
- Model choice affects speed, cost, and output quality independently of instructions.
- `instruction.md` is framework-agnostic — the same file works in ADK and Smolagents.
