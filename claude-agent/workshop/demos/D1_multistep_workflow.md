# Demo D1 — Multi-step Agentic Workflow

**Demo type:** Live demonstration | **Time:** ~10 min

---

## What this demonstrates

A **ReAct (Reasoning + Acting) agent** that autonomously:
1. Decides what data to download
2. Fetches it
3. Analyses it
4. Produces text-based charts — all without human intervention

This is a multi-step workflow where each step's output feeds the next.

---

## Instruction file: `instruction.md`

Upload this as your instruction:

```markdown
# Task: Titanic Survival Analysis

## Step 1 — Acquire data
Use the `fetch_url` tool to download the Titanic dataset CSV from:
  https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv

Save it to the outbox as `titanic.csv`.

## Step 2 — Analyse survival by class
Read `titanic.csv`. Compute survival rate (Survived=1) broken down by:
- Passenger class (Pclass: 1, 2, 3)
- Sex (male/female)
- Age group (child <18, adult 18-60, senior 60+)

## Step 3 — Text-based charts
Use Python-style ASCII art to produce bar charts for each breakdown.
Do NOT use matplotlib or any graphical library.
Use characters like ▓, ░, █ or simple ASCII |###| bars.

Example format:
  Class 1: ████████████████████ 63%
  Class 2: ████████████ 47%
  Class 3: ██████ 24%

## Step 4 — Write report
Write everything to `outbox/titanic_analysis.md` with clear headings.
Write DONE on the last line.
```

---

## Required tool: `fetch_url`

Add this to `agent_harness.py` in `CUSTOM_TOOLS`:

```python
@tool(
    "fetch_url",
    "Fetch the text content of a public URL. Returns up to 50000 characters.",
    {"url": str},
)
async def fetch_url(args: dict) -> dict:
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get(args["url"], timeout=30, follow_redirects=True)
    return {"content": [{"type": "text", "text": r.text[:50000]}]}
```

And in `requirements.txt`: `httpx>=0.27.0`

---

## Expected output

The agent will autonomously:
- Call `fetch_url` to download the CSV (one tool call)
- Call `write_output` to save it (one tool call)
- Read and analyse the data using its built-in reasoning
- Produce ASCII bar charts without any charting library

Sample output in `outbox/titanic_analysis.md`:
```
# Titanic Survival Analysis

## Survival by Passenger Class
  Class 1 ████████████████████ 63%  (136/216)
  Class 2 ████████████         47%  ( 87/184)
  Class 3 ██████               24%  (119/491)

## Survival by Sex
  Female  ████████████████████████████████ 74%
  Male    ████                             19%
...
```

---

## Discussion points

- **ReAct loop**: the agent reasons ("I need to download data first") then acts
  (calls `fetch_url`), then reasons again ("now I have the data, I should analyse").
- **No code execution**: the agent does all arithmetic in its context window,
  not by running Python.
- **Jailbreak risk**: notice that the instruction asks the agent to fetch a URL
  and *save it to outbox*. Without the guardrail (Exercise 4), could a malicious
  user change the URL to exfiltrate data? Yes — implement the guardrail!
- **Plotext alternative**: if you want actual terminal charts, add
  `pip install plotext` and instruct the agent to use it via the Python skill.

---

## Iris dataset variant

Replace the instruction with:

```markdown
Use fetch_url to download the Iris dataset from:
  https://archive.ics.uci.edu/ml/machine-learning-databases/iris/iris.data

The columns are: sepal_length, sepal_width, petal_length, petal_width, species

Compute mean and standard deviation for each measurement, per species.
Display as a text table. Write to outbox/iris_stats.md.
Write DONE when finished.
```
