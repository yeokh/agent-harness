# Demo D3 — Brain Swapping: Model Selection

**Demo type:** Live demonstration | **Time:** ~10 min

---

## What this demonstrates

Changing the AI model (the "brain") has a direct, observable impact on:
- **Capability**: what the agent can reason about
- **Speed**: how fast it completes the task
- **Cost**: API tokens consumed per run

This demonstrates why model selection is an architectural decision, not just
a configuration detail.

---

## Step 1 — Add model selector to the UI

Edit `web_app.py` to expose the current model and allow it to be changed:

```python
# Add to the AgentState class or as a global variable
_current_model = os.environ.get("CLAUDE_MODEL", "claude-opus-4-5")

@app.route("/api/model", methods=["GET"])
def api_get_model():
    return jsonify({"model": _current_model})

@app.route("/api/model", methods=["POST"])
def api_set_model():
    global _current_model
    data = request.get_json()
    model = data.get("model", "")
    ALLOWED_MODELS = [
        "claude-opus-4-5",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ]
    if model not in ALLOWED_MODELS:
        return jsonify({"error": f"Unknown model: {model}"}), 400
    _current_model = model
    os.environ["CLAUDE_MODEL"] = model
    return jsonify({"model": model})
```

### Add a model selector to `index.html`

In the controls bar, add:
```html
<select id="modelSelect" onchange="setModel(this.value)">
  <option value="claude-opus-4-5">Opus 4.5 (most capable)</option>
  <option value="claude-sonnet-4-6">Sonnet 4.6 (balanced)</option>
  <option value="claude-haiku-4-5-20251001">Haiku 4.5 (fast, cheap)</option>
</select>
```

And the JavaScript:
```javascript
async function setModel(model) {
  const res = await fetch('/api/model', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({model})
  });
  const data = await res.json();
  if (data.error) toast(data.error, true);
  else toast(`Model: ${data.model}`);
}
```

---

## Step 2 — The multi-step benchmark task

Use this instruction to expose model capability differences:

```markdown
# Task: Multi-step Data Analysis Challenge

1. Read `sample_data.csv`.
2. Compute: average salary, highest earner, department with most staff.
3. Write a Markdown report with a salary distribution histogram (text-based).
4. Add a section recommending three HR policy changes based on the data,
   with justification for each.
5. Translate the executive summary into formal business language.
6. Write everything to `outbox/analysis.md`.
Write DONE when done.
```

---

## Step 3 — Run with each model and compare

| Model | Expected result |
|-------|----------------|
| `claude-opus-4-5` | Full analysis, nuanced recommendations, polished writing |
| `claude-sonnet-4-6` | Good analysis, reasonable recommendations |
| `claude-haiku-4-5-20251001` | May skip steps, simpler recommendations, faster |

**Observe:**
- Number of agentic turns (shown in the `[result]` log line)
- Quality of the text-based histogram
- Depth of HR recommendations
- Cost (shown in the log as `cost=$X.XXXX`)

---

## Discussion points

- **"Brain swapping"**: the *same harness, same tools, same instruction* — only
  the model changes. This is the power of the agent abstraction.
- **Cost vs. capability**: Haiku costs ~20× less than Opus. For simple tasks,
  Haiku is sufficient. For complex multi-step reasoning, Opus is worth the cost.
- **API gateway pattern**: in a real system, model selection could be enforced
  by an API gateway (e.g., based on user role or task type).
- **Model routing**: advanced systems automatically route tasks to the right
  model based on complexity classification.

---

## Automation: run the benchmark programmatically

```bash
for model in claude-opus-4-5 claude-sonnet-4-6 claude-haiku-4-5-20251001; do
  echo "=== $model ==="
  CLAUDE_MODEL=$model python agent_harness.py
  echo "---"
  echo "Output:"
  cat outbox/analysis.md | head -20
  echo ""
done
```
