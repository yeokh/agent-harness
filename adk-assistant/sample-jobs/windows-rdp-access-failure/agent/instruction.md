# Windows RDP Access Failure Recovery Job

## Purpose

You are a Windows systems engineer responsible for restoring Remote Desktop access to servers.
You will be given Windows Event Log excerpts and system diagnostic output from Windows servers.
Each log file is named after the server it came from (e.g. `win-srv-01.log` = host `win-srv-01`).

Your job is to:
1. Identify why RDP is failing on each host — the symptom is the same (RDP refused) but the root cause differs per host
2. Generate a single Ansible playbook using Windows Ansible modules that fixes only the evidenced root cause per host
3. Produce a recovery report

---

## Tasks

### Step 1 — Diagnose each host

For each log file in the inbox:
- Identify the host name and Windows Server version
- Identify the RDP failure category:
  - `CREDSSP_POLICY` — CredSSP encryption oracle remediation mismatch between client and server after a Windows patch
  - `FIREWALL_RULE` — Windows Firewall rule for RDP (TCP 3389) disabled, missing, or overridden by a block rule
  - `NLA_CERT` — Network Level Authentication failing due to a missing or expired RDP listener certificate
  - `SERVICE_STOPPED` — Remote Desktop Services (`TermService`) or its dependency (`SessionEnv`) is stopped or disabled
  - `OTHER` — anything else clearly evidenced in the logs
- Identify the specific evidence (event IDs, registry key values, rule names, service states)
- Assess user impact: how many users/sessions are affected

### Step 2 — Generate the Ansible playbook

Write a single file `recovery-playbook.yml` to `outbox/`.

**Playbook structure**:
- One Ansible **play** per host
- Each play targets the specific hostname: `hosts: <hostname>`
- Set `gather_facts: true` and `become: false` at the play level (Windows privilege is handled via admin `ansible_user`)
- Every task must have a descriptive `name:`
- Use `ansible.windows` and `community.windows` collection modules — do not write raw PowerShell where a dedicated module exists

**Connection variables** — include in each play's `vars:`:
```yaml
vars:
  ansible_connection: winrm
  ansible_winrm_transport: kerberos      # or ntlm for workgroup hosts
  ansible_winrm_server_cert_validation: ignore
```

**Important**: Since RDP is broken, these playbook tasks must run over **WinRM (port 5985/5986)**, not RDP. WinRM must already be enabled on the target (it is assumed to be available).

---

### CREDSSP_POLICY remediation tasks

The server was patched with a Windows CU that enforces updated CredSSP; unpatched clients receive `SEC_E_ALGORITHM_MISMATCH`. The emergency fix is to relax the server policy temporarily.

1. **Read and display the current CredSSP registry value**:
   ```yaml
   - name: Read current CredSSP AllowEncryptionOracle value
     ansible.windows.win_reg_stat:
       path: HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\CredSSP\Parameters
       name: AllowEncryptionOracle
     register: credssp_current

   - name: Show current CredSSP value
     ansible.builtin.debug:
       msg: "Current AllowEncryptionOracle value: <<credssp_current.value>>"
   ```

2. **Set AllowEncryptionOracle to 2** (Vulnerable — emergency fallback to allow unpatched clients):
   ```yaml
   - name: Set CredSSP AllowEncryptionOracle to Vulnerable (emergency workaround)
     ansible.windows.win_regedit:
       path: HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\CredSSP\Parameters
       name: AllowEncryptionOracle
       data: 2
       type: dword
   ```

3. **Restart Remote Desktop Services** to apply the change:
   ```yaml
   - name: Restart Remote Desktop Services to apply CredSSP policy change
     ansible.windows.win_service:
       name: TermService
       state: restarted
   ```

4. **Validate RDP port is accepting connections**:
   ```yaml
   - name: Wait for RDP port 3389 to be available
     ansible.windows.win_wait_for:
       port: 3389
       host: 127.0.0.1
       timeout: 30

   - name: Confirm RDP port is listening
     ansible.windows.win_shell: |
       $result = Test-NetConnection -ComputerName localhost -Port 3389 -WarningAction SilentlyContinue
       if (-not $result.TcpTestSucceeded) { exit 1 }
       Write-Output "RDP port 3389 is open."
     args:
       executable: powershell
     register: rdp_check

   - name: Show RDP validation result
     ansible.builtin.debug:
       var: rdp_check.stdout_lines
   ```

> **Note the playbook must include a comment** explaining that `AllowEncryptionOracle = 2` is a temporary emergency measure. The permanent fix is to apply the equivalent Windows CU to the connecting client machines, then restore the value to `1` (Mitigated) or `0` (Force Updated Clients).

---

### FIREWALL_RULE remediation tasks

The RDP Allow rules are disabled or overridden by a GPO-pushed Block rule.

1. **Enable the built-in Remote Desktop firewall rules** if they are disabled:
   ```yaml
   - name: Enable Remote Desktop firewall rule - TCP
     ansible.windows.win_firewall_rule:
       name: Remote Desktop - User Mode (TCP-In)
       enabled: true
       state: present

   - name: Enable Remote Desktop firewall rule - UDP
     ansible.windows.win_firewall_rule:
       name: Remote Desktop - User Mode (UDP-In)
       enabled: true
       state: present
   ```

2. **If a GPO-pushed Block rule is overriding the Allow rules**, add a higher-priority local Allow rule. (A local rule with a lower `priority` integer takes precedence over GPO rules in the same direction):
   ```yaml
   - name: Add high-priority local Allow rule for RDP to override GPO block
     ansible.windows.win_firewall_rule:
       name: Allow RDP Inbound - Emergency Override
       localport: 3389
       protocol: tcp
       direction: in
       action: allow
       enabled: true
       state: present
       profiles: domain,private,public
   ```

3. **Verify no active Block rule is shadowing RDP** (informational):
   ```yaml
   - name: Check for active block rules on port 3389
     ansible.windows.win_shell: |
       Get-NetFirewallRule | Where-Object {
         $_ | Get-NetFirewallPortFilter | Where-Object { $_.LocalPort -eq '3389' }
       } | Where-Object { $_.Action -eq 'Block' -and $_.Enabled -eq 'True' } |
       Select-Object DisplayName, Enabled, Action, PolicyStoreSourceType |
       Format-Table -AutoSize | Out-String
     args:
       executable: powershell
     register: block_rules

   - name: Show any active block rules on port 3389
     ansible.builtin.debug:
       var: block_rules.stdout_lines
   ```

4. **Validate RDP port is now reachable**:
   ```yaml
   - name: Wait for RDP port 3389 to be available after firewall change
     ansible.windows.win_wait_for:
       port: 3389
       host: 127.0.0.1
       timeout: 30
   ```

---

### SERVICE_STOPPED remediation tasks

`TermService` and/or its dependency `SessionEnv` are stopped or disabled.

1. **Ensure SessionEnv (dependency) is enabled and running first**:
   ```yaml
   - name: Set Remote Desktop Configuration service to Automatic
     ansible.windows.win_service:
       name: SessionEnv
       start_mode: auto

   - name: Start Remote Desktop Configuration service
     ansible.windows.win_service:
       name: SessionEnv
       state: started
   ```

2. **Ensure TermService is enabled and running**:
   ```yaml
   - name: Set Remote Desktop Services to Automatic
     ansible.windows.win_service:
       name: TermService
       start_mode: auto

   - name: Start Remote Desktop Services
     ansible.windows.win_service:
       name: TermService
       state: started
   ```

3. **Validate both services are running**:
   ```yaml
   - name: Verify TermService is running
     ansible.windows.win_service_info:
       name: TermService
     register: term_info

   - name: Assert TermService is running
     ansible.builtin.assert:
       that: term_info.services[0].state == "running"
       fail_msg: "TermService failed to start"
       success_msg: "TermService is running"
   ```

---

### NLA_CERT remediation tasks

The RDP listener certificate thumbprint in the registry points to a missing or expired certificate.

1. **Clear the stale certificate thumbprint** so RDS falls back to its auto-generated self-signed cert:
   ```yaml
   - name: Clear stale RDP certificate thumbprint from registry
     ansible.windows.win_regedit:
       path: HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp
       name: SSLCertificateSHA1Hash
       state: absent
   ```

2. **Restart TermService** so RDS regenerates its self-signed certificate:
   ```yaml
   - name: Restart Remote Desktop Services to regenerate RDP certificate
     ansible.windows.win_service:
       name: TermService
       state: restarted
   ```

3. **Validate the new thumbprint is present in the registry**:
   ```yaml
   - name: Verify new RDP certificate thumbprint was generated
     ansible.windows.win_reg_stat:
       path: HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp
       name: SSLCertificateSHA1Hash
     register: new_thumbprint

   - name: Show new RDP certificate thumbprint
     ansible.builtin.debug:
       msg: "New RDP certificate thumbprint: <<new_thumbprint.value>>"
   ```

---

### Step 3 — Generate a recovery report

Write `recovery-report.md` to `outbox/` with this structure per host:

```
## <hostname>

**RDP Failure Category**: <category>
**Evidence**: <specific event IDs, registry values, or rule states that confirm the diagnosis>
**Root Cause**: <one paragraph>
**Users Affected**: <estimate from the log>
**Ansible Modules Used**: <list of ansible.windows.* / community.windows.* modules>
**Fix Applied**: <numbered list matching playbook tasks>
**Permanent Prevention**: <what should be done after the emergency fix>
**Rollback**: <how to undo the fix if it causes problems>
```

---

## Output Files

Write to the `outbox/` folder:

1. `recovery-playbook.yml` — single Ansible playbook covering all hosts
2. `recovery-report.md` — combined recovery report for all hosts

---

## Important Notes

- All tasks run over **WinRM**, not RDP — the playbook connects on port 5985/5986
- Do **not** disable Windows Firewall entirely — enable or add only the specific RDP rules needed
- Do **not** set `AllowEncryptionOracle = 2` permanently — the report must flag it as a temporary workaround
- Do **not** disable NLA (`UserAuthentication = 0` in the registry) as a workaround — fix the underlying cert or CredSSP issue instead
- `TermService` depends on `SessionEnv` — always start `SessionEnv` first
- Use `ansible.windows.win_regedit` for all registry changes — do not use `win_shell` with `reg.exe` or `Set-ItemProperty`
- Use `ansible.windows.win_firewall_rule` for all firewall changes — do not use `win_shell` with `netsh advfirewall`
- The playbook must be valid YAML and tasks must be idempotent where the module supports it
