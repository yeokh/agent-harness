# Exercise 02 — Modify Task Instructions

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Learn how changes to `instruction.md` change agent behaviour, and understand
the difference between *what* (instruction) and *how* (skill).

---

## Background

In this harness, the agent's task is entirely defined by `instruction.md`.
The file is read by the agent at runtime — you can change it between runs
without restarting anything.

The same agent, same skill, same tools — but a completely different outcome
depending on what you write in `instruction.md`.

---

## Steps

### 1. Clear the outbox

Click **Clear Outbox** in the web UI, or from the terminal:

```bash
rm -f outbox/*.md outbox/*.csv outbox/*.json outbox/*.txt
```

### 2. Try a different task: employee report

Replace `inbox/instruction.md` with:

```markdown
# Agent Task: Employee Report

Analyse the CSV file in ./inbox/ and produce two outputs:

1. `./outbox/by_department.md` — a Markdown table showing:
   - Department name
   - Headcount
   - Average salary
   - Average years of experience

2. `./outbox/top_earners.md` — a list of the top 3 earners across all
   departments, with their name, department, salary, and location.

Include a brief interpretation of each table (2–3 sentences).
```

Click **Run Agent** in the web UI.

Compare the output to the previous run. The agent produced completely different
files from the same payload — because the instructions changed.

### 3. Try a more open-ended task

Replace `instruction.md` with:

```markdown
# Agent Task: Open-Ended Analysis

You are a data analyst. Look at the files in ./inbox/ and decide for yourself
what the most interesting insights are. Produce a single report in
./outbox/insights.md with at least three findings you consider noteworthy.
```

Click **Run Agent** again and observe what it chooses to focus on.

### 4. Try a structured output task

```markdown
# Agent Task: JSON Export

Read the CSV in ./inbox/ and write ./outbox/employees.json containing
an array of employee objects. Each object must have these exact keys:
  name, department, salary, years_experience, location

Then write ./outbox/stats.json with:
  total_employees, average_salary, departments (array of unique names)
```

Inspect the JSON output from the Outbox panel, or from the terminal:

```bash
cat outbox/employees.json | python3 -m json.tool
```

---

## Understanding instruction quality

Run these two versions and compare the results:

**Vague instruction:**
```markdown
Summarise the data.
```

**Precise instruction:**
```markdown
Read ./inbox/sample_data.csv and write ./outbox/summary_table.md
containing a Markdown table with one row per department showing:
headcount, min salary, max salary, average salary (rounded to nearest $1000).
Sort rows by headcount descending.
```

The second version produces a deterministic, auditable result. The first
leaves the agent's interpretation unconstrained.

---

## Reflection questions

1. What is the difference between writing `instruction.md` and writing a
   regular prompt in a chat interface? What extra constraints does the
   file-processing context impose?

2. The agent was given open-ended freedom in step 3. Did it find insights
   you expected? Did it miss anything obvious?

3. How would you write an instruction that is both flexible (handles any
   CSV schema) and precise (produces a consistent output format)?

4. What happens if `instruction.md` contradicts `skill.md`? Which takes
   precedence — and why?

---

## Key takeaways

- `instruction.md` is the *what*; `skill.md` is the *how*.
- Precise instructions produce reliable, auditable outputs.
- Open-ended instructions reveal what the model considers important — useful
  for exploration, risky for production.
- Instructions can reference specific output paths and schemas to enforce
  consistency across runs.
