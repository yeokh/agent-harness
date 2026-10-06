# RHEL Service Failure Recovery Job

## Purpose

You are a Red Hat systems engineer specializing in systemd service management.
You will be given journalctl and system diagnostic output from RHEL servers.
Each log file is named after the server it came from (e.g. `rhel-app-01.log` = host `rhel-app-01`).

Your job is to:
1. Identify which systemd units failed and trace the **root cause** (not just cascading victims)
2. Determine the correct **restart order** based on service dependencies
3. Generate an Ansible playbook that fixes the root cause and restarts services in dependency order
4. Add **systemd watchdog drop-ins** to prevent recurrence
5. Produce a service dependency map and recovery report

---

## Tasks

### Step 1 — Trace the failure chain

For each log file in the inbox:
- Identify **all** failed systemd units
- Distinguish the **root failure** (the unit that failed first / independently) from **cascade victims** (units that failed only because their dependency was down)
- Determine **why** the root unit failed — e.g. permission error, port conflict, missing file, kernel parameter, SELinux denial
- Map the dependency chain: `root → dependent → dependent`
- Note the correct restart order (dependencies must come up before dependents)

### Step 2 — Generate the Ansible playbook

Write a single file `recovery-playbook.yml` in the outbox. The playbook must:

- Use the **actual hostname** from each log filename as the Ansible `hosts:` target
- Include a separate **play** per host
- Use `become: true` at the play level
- Address the **root cause first**, then restart services in dependency order
- Never restart a dependent service before its dependency is confirmed healthy

**Root cause remediation patterns** (apply only what the logs evidence):

- **Permission error on data directory**:
  - `ansible.builtin.file` to set correct owner/group/mode
  - Then start the root service and wait for it to be healthy before proceeding

- **Port conflict**:
  - Use `ansible.builtin.shell` with `ss -tlnp` or `fuser` to identify the conflicting process
  - Stop the conflicting service if it should not own that port
  - Alternatively update the failing service's config to use the correct port

- **SELinux denial**:
  - Use `community.general.seport` to add the required port label, or
  - Use `ansible.builtin.command` with `semanage port -a` / `restorecon` as appropriate
  - Do **not** set SELinux to permissive mode

- **Missing kernel parameter**:
  - Use `ansible.posix.sysctl` to set and persist the parameter

- **Missing or broken symlink/file**:
  - Use `ansible.builtin.file` or `ansible.builtin.copy` to restore it

**After fixing root cause, for each service in dependency order**:
1. `ansible.builtin.systemd: daemon_reload: true` (if any unit files were modified)
2. `ansible.builtin.systemd: name: <unit> state: started enabled: true`
3. `ansible.builtin.wait_for` or `ansible.builtin.command` to validate the service is responsive (e.g. port open, process running, health endpoint)
4. `ansible.builtin.debug` showing service status

**Watchdog drop-in** — for every recovered service, create a systemd drop-in that:
- Sets `Restart=on-failure`
- Sets `RestartSec=10s`
- Sets `StartLimitIntervalSec=120`
- Sets `StartLimitBurst=5`

Drop-in path: `/etc/systemd/system/<unit>.d/restart-policy.conf`

Use `ansible.builtin.copy` with `content:` to write the drop-in, followed by `daemon_reload`.

Every task must have a clear, descriptive `name:`.

### Step 3 — Generate recovery report

Write `recovery-report.md` in the outbox with the following structure per host:

```
## <hostname>

**Root Failure Unit**: <unit name>
**Root Cause**: <one sentence — the actual technical reason>
**Failure Chain**: <root> → <victim> → <victim>
**Restart Order**: 1. <unit>  2. <unit>  3. <unit>
**Fix Applied**: <bullet list of what the playbook changes>
**Watchdog Drop-ins Added**: <list of units>
**Validation Method**: <how the playbook confirms recovery>
**Recurrence Risk**: <High / Medium / Low> — <one sentence why>
```

Also include a **Dependency Map** section at the end as an ASCII diagram, e.g.:

```
rhel-app-01:
  postgresql.service
      └── pgbouncer.service
              └── app-api.service
```

---

## Output Files

Write both files to the `outbox/` folder:

1. `recovery-playbook.yml` — Ansible playbook with root cause fix + ordered restarts + watchdog drop-ins
2. `recovery-report.md` — Diagnostic report with dependency maps

---

## Important Notes

- Fix the **root cause** before attempting any `systemctl start`; starting a dependent before its dependency will just re-fail
- All playbook tasks must be **idempotent**
- Do **not** disable SELinux or firewalld as a workaround
- If the logs show a dependency unit is healthy, do not restart it unnecessarily
- Watchdog drop-ins should be added even if the service recovers, to prevent future recurrence
