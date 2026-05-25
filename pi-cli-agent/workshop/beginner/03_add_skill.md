# Exercise 03 — Add Skill Instructions

**Track:** Beginner | **Time:** ~20 min

---

## Objective

Learn how to extend `skill.md` to give the agent new capabilities and
behavioural constraints — without writing any Python code.

---

## Background

In the claude-agent harness, adding a new tool required writing a Python
function with the `@tool` decorator, then restarting the app.

In the pi CLI approach, the agent already has all the tools it needs
(`read`, `write`, `bash`, `grep`, `find`, `ls`). Extending capability
means writing *instructions* in `skill.md` that tell the agent how to
use those tools for a new purpose.

Think of `skill.md` as a **capability card**: it describes what the agent
knows how to do and gives it the vocabulary for a specific domain.

---

## Steps

### 1. Add a bash-based data processing recipe

Open `inbox/skill.md` and add this section at the end:

```markdown
## Python Data Processing

When the task requires aggregation, sorting, or transformation of CSV data,
use bash to invoke Python:

```bash
python3 - <<'EOF'
import csv, json, sys
from collections import defaultdict

with open('./inbox/sample_data.csv') as f:
    rows = list(csv.DictReader(f))

# group by department
by_dept = defaultdict(list)
for r in rows:
    by_dept[r['department']].append(int(r['salary']))

stats = {dept: {'count': len(salaries), 'avg': sum(salaries)//len(salaries)}
         for dept, salaries in by_dept.items()}

print(json.dumps(stats, indent=2))
EOF
```

Write the output to `./outbox/dept_stats.json`.
```

Now update `instruction.md` to use this new recipe:

```markdown
# Agent Task: Department Statistics

Use the Python data processing recipe from your skill to compute per-department
statistics from ./inbox/sample_data.csv.

Write the results to ./outbox/dept_stats.json.
Then write a human-readable summary to ./outbox/dept_summary.md.
```

Click **Run Agent** in the web UI and check the log stream to confirm the
agent used bash/Python to produce the JSON.

### 2. Add an output-format constraint

Add to `skill.md`:

```markdown
## Report Format Standard

All Markdown reports must follow this structure:
1. `# Title` — one-line title
2. `## Executive Summary` — 2–3 sentences
3. `## Findings` — tables, bullet points, or numbered lists
4. `## Conclusion` — one sentence

Do not add any other top-level sections.
```

Click **Run Agent** with the original `instruction.md`. Does the output now
follow the standard structure?

### 3. Add a file-naming convention

Add to `skill.md`:

```markdown
## File Naming

Name output files using this pattern:
  <task_type>_<YYYYMMDD>.md   e.g. report_20260509.md

Use today's date. Do not use spaces or special characters in filenames.
```

After the run, check the **Outbox** panel to see what filenames the agent chose.

### 4. Add a domain-specific capability

Try adding a skill section for a completely different domain. For example,
if your inbox contains log files:

```markdown
## Log File Analysis

When processing .log files:
- Parse lines with format: `YYYY-MM-DD HH:MM:SS [LEVEL] message`
- Group by severity level: ERROR, WARN, INFO, DEBUG
- Count occurrences of each level
- Extract the first and last timestamp
- Flag any ERROR lines in a separate section of the report
```

Create a sample `inbox/app.log` with some lines (you can upload it via the
web UI), then update `instruction.md` to ask for log analysis.

---

## Comparing approaches

| Capability | claude-agent | pi-cli-agent |
|-----------|-------------|--------------|
| Add a word-count tool | Write Python `@tool` function | Add bash recipe to skill.md |
| Enforce output format | Modify system prompt in Python | Add format section to skill.md |
| Add domain knowledge | Modify system prompt | Add domain section to skill.md |
| Restart required | Yes | No |
| Code changes required | Yes | No |

---

## Reflection questions

1. What are the limits of the skill-as-instructions approach? What kinds of
   capabilities genuinely require writing code?

2. The agent reads `skill.md` as text — it is not executed. What could go
   wrong if your skill instructions contain an error (e.g., a wrong file path)?

3. How would you version-control skill files for a team? What workflow would
   you use to review and approve skill changes?

4. Could a malicious user override the skill by writing conflicting instructions
   in `instruction.md`? How would you defend against this?

---

## Key takeaways

- `skill.md` is the extensibility mechanism: new capabilities require new text,
  not new code.
- Bash recipes inside skill.md let the agent run Python, shell scripts, or any
  host tool — this is both powerful and a security consideration.
- Format and naming conventions in `skill.md` make agent outputs consistent
  and auditable across runs.
- Skills are portable: the same `skill.md` works on any machine with pi installed.
