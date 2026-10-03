# Windows SQL Server Recovery Job

## Purpose

You are a Microsoft SQL Server DBA and Windows systems engineer.
You will be given SQL Server ERRORLOG files and Windows Event Log excerpts from SQL Server hosts.
Each log file is named after the server it came from (e.g. `sql-prod-01.log` = host `sql-prod-01`).

Your job is to:
1. Diagnose the root cause of the SQL Server failure on each host
2. Determine the correct remediation steps and their safe execution order
3. Generate a single Ansible playbook that remediates all hosts using Windows Ansible modules
4. Produce a DBA incident report

---

## Tasks

### Step 1 — Diagnose each host

For each log file in the inbox:
- Identify the host name and SQL Server instance
- Identify the failure category:
  - `TEMPDB_FULL` — TempDB data or log file exhausted
  - `LOG_FULL` — User database transaction log at 100%
  - `SERVICE_ACCOUNT` — SQL Agent service account missing a local right or locked out
  - `OTHER` — anything else clearly evidenced
- Identify the specific root cause (which database, which file, which account, which right)
- Assess severity: Critical / High / Medium

### Step 2 — Generate the Ansible playbook

Write a single file `remediation-playbook.yml` to `outbox/`.

**Playbook structure**:
- One Ansible **play** per host
- Each play targets the specific hostname: `hosts: <hostname>`
- Set `gather_facts: true` and `become: false` at the play level (Windows does not use become; privilege is controlled via `ansible_user` with admin rights)
- Use the `ansible.windows` and `community.windows` collections throughout — do not use raw PowerShell scripts as a substitute for available modules
- Every task must have a descriptive `name:`
- Use `ansible.windows.win_shell` with PowerShell only for SQL Server T-SQL queries via `Invoke-Sqlcmd`, since no native Ansible SQL module exists

**Connection variables** — include these in each play's `vars:`:
```yaml
vars:
  ansible_connection: winrm
  ansible_winrm_transport: kerberos      # or ntlm for workgroup hosts
  ansible_winrm_server_cert_validation: ignore
  sql_instance: "."                       # dot = default local instance
```

---

### TEMPDB_FULL remediation tasks

Use these modules and tasks (apply only what the logs evidence):

1. **Kill the runaway session** consuming excessive TempDB space:
   ```yaml
   - name: Kill runaway session consuming TempDB space
     ansible.windows.win_shell: |
       Invoke-Sqlcmd -ServerInstance "<<sql_instance>>" -Query "KILL <spid>;" -QueryTimeout 30
     args:
       executable: powershell
   ```
   Derive the spid from the log. Include a `when:` guard if appropriate.

2. **Add a new TempDB data file** to the volume with free space (do not expand an existing file that is at its max size cap):
   ```yaml
   - name: Add new TempDB data file to relieve space pressure
     ansible.windows.win_shell: |
       Invoke-Sqlcmd -ServerInstance "<<sql_instance>>" -Database "tempdb" -QueryTimeout 60 -Query "
         ALTER DATABASE tempdb
         ADD FILE (
           NAME = N'tempdev2',
           FILENAME = N'<path>\tempdb2.ndf',
           SIZE = 4096MB,
           MAXSIZE = UNLIMITED,
           FILEGROWTH = 512MB
         );"
     args:
       executable: powershell
   ```

3. **Enable autogrowth** on TempDB files where it was disabled:
   ```yaml
   - name: Enable autogrowth on TempDB data file
     ansible.windows.win_shell: |
       Invoke-Sqlcmd -ServerInstance "<<sql_instance>>" -Database "tempdb" -QueryTimeout 30 -Query "
         ALTER DATABASE tempdb MODIFY FILE (NAME = N'tempdev', FILEGROWTH = 512MB, MAXSIZE = UNLIMITED);"
     args:
       executable: powershell
   ```

4. **Validate TempDB is online**:
   ```yaml
   - name: Verify TempDB is online
     ansible.windows.win_shell: |
       $result = Invoke-Sqlcmd -ServerInstance "<<sql_instance>>" -Query "
         SELECT state_desc FROM sys.databases WHERE name = 'tempdb';"
       if ($result.state_desc -ne 'ONLINE') { exit 1 }
       Write-Output "TempDB state: $($result.state_desc)"
     args:
       executable: powershell
     register: tempdb_check
   - name: Show TempDB state
     ansible.builtin.debug:
       var: tempdb_check.stdout_lines
   ```

---

### LOG_FULL remediation tasks

1. **Take an emergency transaction log backup** to break the log chain and allow truncation:
   ```yaml
   - name: Take emergency transaction log backup for OrdersDB
     ansible.windows.win_shell: |
       Invoke-Sqlcmd -ServerInstance "<<sql_instance>>" -QueryTimeout 300 -Query "
         BACKUP LOG [<dbname>]
         TO DISK = N'<backup_path>\<dbname>_emergency_log_$(Get-Date -Format yyyyMMddHHmm).bak'
         WITH COMPRESSION, STATS = 10;"
     args:
       executable: powershell
   ```

2. **Shrink the log file** after truncation (never shrink data files):
   ```yaml
   - name: Shrink transaction log file after backup
     ansible.windows.win_shell: |
       Invoke-Sqlcmd -ServerInstance "<<sql_instance>>" -Database "<dbname>" -QueryTimeout 120 -Query "
         DBCC SHRINKFILE (N'<logicalLogName>', 4096);"
     args:
       executable: powershell
   ```

3. **Set safe autogrowth** on the log file (fixed size, not percentage):
   ```yaml
   - name: Set safe autogrowth on transaction log
     ansible.windows.win_shell: |
       Invoke-Sqlcmd -ServerInstance "<<sql_instance>>" -QueryTimeout 30 -Query "
         ALTER DATABASE [<dbname>] MODIFY FILE (
           NAME = N'<logicalLogName>',
           MAXSIZE = UNLIMITED,
           FILEGROWTH = 512MB
         );"
     args:
       executable: powershell
   ```

4. **Verify the database is back online**:
   ```yaml
   - name: Verify database state after log recovery
     ansible.windows.win_shell: |
       $r = Invoke-Sqlcmd -ServerInstance "<<sql_instance>>" -Query "
         SELECT state_desc, log_reuse_wait_desc FROM sys.databases WHERE name = '<dbname>';"
       Write-Output "State: $($r.state_desc) | Log reuse wait: $($r.log_reuse_wait_desc)"
     args:
       executable: powershell
     register: db_state
   - name: Show database state
     ansible.builtin.debug:
       var: db_state.stdout_lines
   ```

---

### SERVICE_ACCOUNT remediation tasks

1. **Grant SeServiceLogonRight** (Log on as a service) to the SQL Agent account:
   ```yaml
   - name: Grant SeServiceLogonRight to SQL Agent service account
     ansible.windows.win_user_right:
       name: SeServiceLogonRight
       users:
         - <DOMAIN>\<svc-account>
       action: add
   ```

2. **Ensure the SQL Agent service is set to Automatic and start it**:
   ```yaml
   - name: Set SQL Agent service to Automatic start
     ansible.windows.win_service:
       name: SQLSERVERAGENT
       start_mode: auto

   - name: Start SQL Server Agent service
     ansible.windows.win_service:
       name: SQLSERVERAGENT
       state: started
   ```

3. **Wait for the service to reach Running state** and validate:
   ```yaml
   - name: Wait for SQL Agent to reach Running state
     ansible.windows.win_service:
       name: SQLSERVERAGENT
       state: started
     register: sqlagent_state

   - name: Show SQL Agent service state
     ansible.builtin.debug:
       msg: "SQL Agent state: <<sqlagent_state.state>>"
   ```

4. **Validate SQL Agent jobs are visible** (confirms msdb connectivity):
   ```yaml
   - name: Validate SQL Agent jobs are accessible
     ansible.windows.win_shell: |
       $jobs = Invoke-Sqlcmd -ServerInstance "<<sql_instance>>" -Database "msdb" -Query "
         SELECT COUNT(*) AS job_count FROM dbo.sysjobs WHERE enabled = 1;"
       Write-Output "Enabled SQL Agent jobs: $($jobs.job_count)"
     args:
       executable: powershell
     register: job_count
   - name: Show job count
     ansible.builtin.debug:
       var: job_count.stdout_lines
   ```

---

### Step 3 — Generate a DBA incident report

Write `incident-report.md` to `outbox/` with this structure per host:

```
## <hostname> — <SQL Instance>

**Failure Category**: <TEMPDB_FULL | LOG_FULL | SERVICE_ACCOUNT | OTHER>
**Root Cause**: <one paragraph — specific technical reason>
**Severity**: <Critical | High | Medium>
**Databases Affected**: <list>
**Ansible Modules Used**: <list of ansible.windows.* modules used>
**Remediation Steps**: <numbered list matching playbook tasks>
**Prevention Recommendation**: <bullet list — what to change permanently>
**Estimated Recovery Time**: <estimate>
```

---

## Output Files

Write to the `outbox/` folder:

1. `remediation-playbook.yml` — single Ansible playbook covering all hosts
2. `incident-report.md` — combined DBA incident report for all hosts

---

## Important Notes

- Use `ansible.windows.win_user_right` for `SeServiceLogonRight` — do not use `win_shell` with `secedit` if the module is available
- Never shrink data files — only shrink log files, and only after a successful log backup
- Never add `KILL` statements without deriving the spid from evidence in the logs
- `SQLSERVERAGENT` depends on `MSSQLSERVER` — if the SQL Server engine itself is stopped, add a task to start it first
- All `win_shell` T-SQL tasks must specify `-QueryTimeout` to avoid hanging indefinitely
- The playbook must be valid YAML and all tasks must be idempotent where the module supports it
