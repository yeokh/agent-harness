---
name: ansible-lint
description: Scan Ansible playbooks and roles for best practices, security issues, and style violations using the deterministic ansible-lint tool. Provides structured JSON output with rule IDs, severity levels, and remediation guidance.
license: Apache-2.0
user_invocable: true
model: inherit
color: orange
---

# Ansible Lint Skill

A deterministic, rule-based tool for validating Ansible playbooks and roles against 100+ built-in rules covering security, best practices, performance, and maintainability.

## Prerequisites

- **ansible-lint** installed on system
- YAML/playbook files to scan
- Read access to playbook directories

## When to Use This Skill

When you need to:
- Validate Ansible playbooks for quality and best practices
- Check for security violations in playbooks
- Enforce consistent coding standards
- Generate compliance reports
- Identify deprecated modules before they break
- Prepare playbooks for production use

## Workflow

1. **Scan playbooks** - Run ansible-lint with JSON output format
2. **Parse results** - Extract rule ID, severity, file, line number, message
3. **Categorize findings** - Group by severity (CRITICAL, HIGH, MEDIUM, LOW, NOTICE)
4. **Analyze patterns** - Identify recurring issues and trends
5. **Generate reports** - Create structured findings and remediation guides

## Dependencies

- Bash shell access
- `ansible-lint` command available (v6.0+)
- YAML parsing capability

## Command Usage

### Basic scan:
```bash
ansible-lint <playbook.yaml>
```

### Scan with JSON output:
```bash
ansible-lint <playbook.yaml> --format json
```

### Scan entire directory:
```bash
ansible-lint roles/ --format json
```

### Scan with specific rules:
```bash
ansible-lint <playbook.yaml> --select E701,E602
```

### Get rule documentation:
```bash
ansible-lint --help-list
```

## Rule Categories

### Security Rules (E###)
- **E401**: Unexpected jinja2 in when condition
- **E402**: Jinja2 invalid escape sequence
- **E701**: run-once with loop
- **E704**: Command module, avoid shell
- **E405**: Unexpected jinja2 in variable default
- **E602**: No-tabs (indentation)
- **E701**: run-once
- **E703**: Key duplication

### Best Practices Rules (W###)
- **W502**: Deprecated module (e.g., docker_service, docker_swarm)
- **W503**: Deprecated module
- **W504**: Line too long
- **W505**: File too long
- **W601**: use-handler-rather-than-command
- **W602**: use-shell-only-when-necessary

### Style/Format Rules
- **E602**: no-tabs
- **E701**: indentation (run-once)
- **E704**: literal-compare
- **E503**: package-latest
- **E501**: max-module-name-length

### Task/Handler Rules
- **E401**: meta-incorrect
- **E402**: meta-no-info
- **E501**: max-task-name-length
- **E701**: run-once

## Output Format

### JSON Output Structure
```json
{
  "matches": [
    {
      "rule": {
        "id": "E701",
        "name": "run-once",
        "description": "run-once should not be used with loop"
      },
      "filename": "playbook.yaml",
      "linenumber": 15,
      "column": 8,
      "level": "MEDIUM",
      "message": "run-once should not be used with loop"
    }
  ]
}
```

### Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| **CRITICAL** | Playbook will fail or has major security issue | Fix immediately before deployment |
| **HIGH** | Best practice violation or security risk | Fix before production use |
| **MEDIUM** | Code quality or maintainability issue | Fix in next sprint |
| **LOW** | Style or minor formatting issue | Nice-to-fix |
| **NOTICE** | Informational, no action required | Review for awareness |

## Common Violations & Fixes

### E701: run-once with loop
**Problem:**
```yaml
- name: Task with loop
  debug:
    msg: "{{ item }}"
  loop: "{{ list }}"
  run_once: true  # ❌ Incorrect
```

**Fix:**
```yaml
- name: Task without loop
  debug:
    msg: "Run once"
  run_once: true  # ✅ Correct
```

### W502: Deprecated module
**Problem:**
```yaml
- name: Use docker service
  docker_service:  # ❌ Deprecated
    project_name: myapp
```

**Fix:**
```yaml
- name: Use containers collection
  containers.podman.podman_container:  # ✅ Current module
    name: myapp
```

### E704: Use shell module only when necessary
**Problem:**
```yaml
- name: Create directory
  shell: mkdir -p /opt/app  # ❌ Use file module instead
```

**Fix:**
```yaml
- name: Create directory
  file:  # ✅ Use appropriate module
    path: /opt/app
    state: directory
```

### E602: no-tabs
**Problem:**
```yaml
- name: Task
  debug:
→	msg: "hello"  # ❌ Tab character
```

**Fix:**
```yaml
- name: Task
  debug:
    msg: "hello"  # ✅ Two spaces
```

## Interpreting Results

### High Priority Fixes (CRITICAL + HIGH)
- Security vulnerabilities
- Deprecated modules
- Syntax errors
- Logic problems
- Performance issues

### Medium Priority Fixes (MEDIUM)
- Code quality improvements
- Best practice violations
- Maintainability issues
- Resource efficiency

### Low Priority Fixes (LOW + NOTICE)
- Style consistency
- Formatting
- Documentation
- Minor cleanup

## Integration with CI/CD

### GitHub Actions
```yaml
- name: Lint Ansible playbooks
  run: ansible-lint --strict
```

### Pre-commit hook
```yaml
- repo: https://github.com/ansible/ansible-lint
  rev: v6.0.0
  hooks:
    - id: ansible-lint
```

## Data Sources

- Ansible Documentation: `https://docs.ansible.com/`
- ansible-lint Rules: `https://ansible-lint.readthedocs.io/rules/`
- Ansible Best Practices: `https://docs.ansible.com/ansible/latest/user_guide/playbooks_best_practices.html`

## Output Recommendations

When reporting ansible-lint findings:

1. **For CRITICAL/HIGH:** Provide exact code fix with explanation
2. **For MEDIUM:** Explain impact and suggest improvements
3. **For LOW:** Note as nice-to-fix, not blocking
4. **Group by rule:** Show all instances of same violation together
5. **Include statistics:** % of rules violated, distribution by severity
6. **Provide compliance score:** Calculate as (1 - violations/total_tasks) * 100

## Limitations

- Cannot validate variables not visible in static analysis
- Cannot check runtime behavior (only syntax and best practices)
- Requires valid YAML syntax (cannot parse broken YAML)
- Some rules may be overly strict for specific use cases
- Does not validate against custom organizational standards beyond rules
