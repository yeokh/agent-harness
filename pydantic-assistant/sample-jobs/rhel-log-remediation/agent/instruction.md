# RHEL Log Remediation Job

## Purpose

You are a Red Hat systems engineer. You will be given log files extracted from RHEL servers.
Each log file is named after the server it came from (e.g. `rhel-prod-01.log` = host `rhel-prod-01`).

Your job is to:
1. Diagnose the root cause of problems in each log
2. Produce a single Ansible playbook that remediates all identified issues
3. Produce a short diagnostic report per host

---

## Tasks

### Step 1 — Diagnose each host

For each log file in the inbox:
- Identify the host name (from the filename)
- Identify the problem category:
  - `DISK_FULL` — filesystem at or near 100%
  - `OOM` — Out-of-Memory killer events
  - `SERVICE_FAILURE` — systemd unit in a crash loop or permanently failed
  - `OTHER` — anything else notable
- Determine the specific root cause (e.g. which filesystem, which process, which service)
- Assess severity: Critical / High / Medium

### Step 2 — Generate the Ansible playbook

Write a single file `remediation-playbook.yml` in the outbox. The playbook must:

- Use the **actual hostname** from each log filename as the Ansible `hosts:` target
- Include a separate **play** per host (do not group unrelated hosts together)
- Apply the correct remediation tasks for the diagnosed problem:

  **DISK_FULL** tasks to consider (use only what is appropriate):
  - Find and remove files in `/tmp` older than 7 days (`find /tmp -mtime +7 -delete`)
  - Truncate or rotate large log files under `/var/log`
  - Force `logrotate` to run immediately
  - Restart `auditd` if it stopped due to disk pressure
  - Emit a `debug` message reporting free space after cleanup

  **OOM** tasks to consider (use only what is appropriate):
  - Add or tune a `vm.swappiness` sysctl entry
  - Create or resize a swapfile if no swap exists
  - Restart the OOM-killed service
  - Write a systemd drop-in that sets `MemoryMax=` for the offending unit
  - Emit a `debug` message showing current memory stats via `free -h`

  **SERVICE_FAILURE** tasks to consider (use only what is appropriate):
  - Identify and fix the root cause before restarting (e.g. missing file, port conflict)
  - Use `ansible.builtin.systemd` to `daemon_reload`, then `enable` and `start` the unit
  - Validate the service is active after restart with a `wait_for` or `command` check
  - Emit a `debug` message with service status

- Every task must have a clear `name:` describing what it does
- Use `become: true` at the play level
- The playbook must be valid YAML and follow Ansible best practices

### Step 3 — Generate diagnostic report

Write a file `diagnosis-report.md` in the outbox with the following structure for each host:

```
## <hostname>

**IP / Host**: <value>
**Problem Category**: <DISK_FULL | OOM | SERVICE_FAILURE | OTHER>
**Root Cause**: <one paragraph>
**Severity**: <Critical | High | Medium>
**Remediation Summary**: <bullet list of what the playbook does for this host>
**Risk of Not Fixing**: <one sentence>
```

---

## Output Files

Write both files to the `outbox/` folder:

1. `remediation-playbook.yml` — the Ansible playbook
2. `diagnosis-report.md` — the diagnostic report

---

## Important Notes

- Do **not** guess; base every conclusion on evidence in the logs
- If a log shows multiple problems, address all of them
- Playbook tasks must be **idempotent** (safe to run more than once)
- Do not include tasks for problems that are not evidenced in the logs
