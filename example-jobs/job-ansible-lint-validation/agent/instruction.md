# Ansible Lint Validation Job

## Purpose

You are a DevOps engineer responsible for validating Ansible playbooks and roles for quality, best practices, and security compliance. Use the Ansible Lint skill to scan all playbooks, analyze findings, and provide comprehensive remediation guidance.

## Tasks

1. **For each playbook/role in the inbox**:
   - Use the Ansible Lint skill to scan the file
   - Capture all findings with rule IDs, severity, and descriptions
   - Note line numbers and affected content
   - Categorize by severity level (CRITICAL, HIGH, MEDIUM, LOW, NOTICE)

2. **Parse and analyze results**:
   - Group findings by rule category (security, performance, style, best practices)
   - Count violations per playbook
   - Identify patterns and recurring issues
   - Calculate a compliance score (0-100)

3. **Generate actionable remediation guidance**:
   - For each unique rule violation, provide:
     - What the rule checks and why it matters
     - The current problematic code
     - Fixed/corrected code with explanation
     - References to Ansible documentation
   
4. **Create comprehensive reports**:
   - Summary report with statistics and trends
   - Detailed findings organized by severity
   - Remediation guide with before/after examples
   - Improvement roadmap with priorities
   - Individual playbook lint reports (JSON format)

## Output Format

Create the following files in the outbox:

1. **lint_summary.md** - Executive summary with key metrics
2. **findings_by_severity.json** - All findings categorized and structured
3. **remediation_guide.md** - Detailed fixes with code examples
4. **playbook_reports/** - Individual JSON reports per file
5. **improvement_roadmap.md** - Priority order for fixes
6. **compliance_score.txt** - Current compliance percentage

## Key Information to Include

For each finding, provide:
- Rule ID and category
- Severity level
- File and line number
- Current problematic code
- Corrected code example
- Explanation of the issue
- Link to Ansible documentation
- Time estimate to fix

## Analysis Examples

**Rule E701: "run-once" with "loop"**
- **Why:** Tasks with loops should not use run_once (usually a mistake)
- **Fix:** Remove run_once or refactor to avoid loop
- **Severity:** MEDIUM

**Rule W503: "deprecated module"**
- **Why:** Using older modules that are no longer recommended
- **Fix:** Migrate to new module (e.g., docker_service → containers)
- **Severity:** HIGH

**E602: "no-tabs"**
- **Why:** YAML files should use spaces, not tabs
- **Fix:** Replace tabs with 2-space indentation
- **Severity:** LOW

## Success Criteria

✅ All playbooks scanned without errors
✅ All violations identified and categorized
✅ Remediation guide includes concrete code examples
✅ Compliance score calculated for each playbook
✅ Improvement prioritized by severity and impact
