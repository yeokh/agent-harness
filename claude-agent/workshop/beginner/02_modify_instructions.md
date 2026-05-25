# Exercise 02 — Modify the Instructions

**Track:** Beginner | **Time:** ~15 min

---

## Objective

Understand how the agent's behaviour is entirely controlled by the instruction
file, and practise writing effective agent instructions.

---

## Background

The instruction file is the agent's "job description". It is the primary lever
for controlling what the agent does. Good agent instructions are:

- **Specific** — vague instructions lead to inconsistent output
- **Structured** — numbered steps help the agent plan
- **Bounded** — tell the agent when it is "done"
- **Format-aware** — tell the agent what output format you expect

---

## Steps

### 1. Replace the instruction file

Upload a new `instruction.md` via the web UI, or edit `inbox/instruction.md`
directly. Try each of the examples below and observe how the agent behaves.

---

### Example A — Simple summarisation

```markdown
# Task: Summarise

Read the file `sample_data.csv`.
Write a 3-sentence summary of the data to `outbox/summary.txt`.
End with the word DONE.
```

**Run the agent.** What did it produce? Is it what you expected?

---

### Example B — Structured analysis

```markdown
# Task: Salary Analysis

Read `sample_data.csv`.
Compute:
1. Average salary across all employees
2. Average salary per department
3. The highest-paid and lowest-paid employee (name and salary)

Format your output as a Markdown table in `outbox/salary_analysis.md`.
Write DONE on the last line when finished.
```

**Run the agent.** Compare the output quality to Example A.

---

### Example C — Multi-file output

```markdown
# Task: Split by Department

Read `sample_data.csv`.
For each unique department, create a separate file in the outbox:
  `outbox/<department_name>.md`

Each file should contain a table of employees in that department.
When all files are written, write a final `outbox/index.md` listing all
departments and their employee counts.
Write DONE as the last line of `outbox/index.md`.
```

**Run the agent.** Check the outbox — how many files were created?

---

### Example D — Constraint testing

```markdown
# Task: Count Only

Read every file in the inbox.
For each file, count the number of lines.
Write the result to outbox/line_counts.txt in the format:
  <filename>: <count> lines

Do NOT read the actual content of the files — only count lines.
Write DONE when finished.
```

> **Can the agent follow the constraint?** Note that the agent's `read_inbox_file`
> tool returns the full content. How would you enforce the line-count constraint
> at the tool level?

---

## Reflection questions

1. Which instruction style produced the most consistent, useful output?

2. What happened when you gave the agent ambiguous instructions (e.g., no
   output filename specified)?

3. How would you write an instruction that processes files added *after* the
   instruction was written (i.e., without knowing the filenames in advance)?
   *(Hint: `list_inbox_files`)*

4. What is the risk of an instruction that says "do anything the user asks"?
   How would you mitigate it?

---

## Key takeaways

- The instruction file is powerful — it defines the entire task scope.
- Structured, numbered instructions lead to better, more reproducible results.
- Always include a "done" signal so the agent knows when to stop.
- Tool design constrains what the agent *can* do; instructions constrain what
  it *should* do.
