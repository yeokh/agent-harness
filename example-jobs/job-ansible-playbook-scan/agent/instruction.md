---

# agent-instruction.md

## Purpose
This document provides instructions for an automated agent to review Ansible playbooks for potential security vulnerabilities. The agent must analyze the playbook content and return a structured JSON response.

## Scope
The agent should focus on detecting the following categories of vulnerabilities:
- **Command Injection**: Unsafe use of `shell`, `command`, or `raw` modules with unvalidated input.
- **Exposed Credentials**: Hardcoded secrets, passwords, tokens, or keys in playbooks or variables.
- **Insecure Practices**: Use of plaintext credentials, unencrypted files, or unsafe configurations.

## Instructions
1. **Parse Playbook**
   - Load the YAML structure of the Ansible playbook.
   - Identify tasks, handlers, and variable definitions.

2. **Check for Command Injection**
   - Flag any use of `shell`, `command`, or `raw` modules.
   - Determine if arguments include variables without sanitization or concatenated strings that could allow injection.

3. **Check for Exposed Credentials**
   - Search for hardcoded values in `vars`, `defaults`, or inline task parameters (e.g., `password=`, `token=`, `secret=`).
   - Verify that sensitive values are referenced securely (e.g., via Ansible Vault, environment variables).

4. **Check for Insecure Practices**
   - Detect plaintext storage of sensitive files (e.g., `.pem`, `.key`, `.crt`).
   - Flag unencrypted variable files or credentials stored in version control.
   - Identify use of `become: yes` without proper restrictions.

5. **Determine Status**
   - **Pass**: No vulnerabilities detected in the categories above.
   - **Fail**: One or more vulnerabilities detected.

6. **Output Format**
   - The agent must return a JSON object with the following fields:
     ```json
     {
       "result": "Pass" | "Fail",
       "reason": "Short paragraph explaining why it failed. Leave blank if Pass."
     }
     ```
   - Write the JSON output into a file result.log 

## Examples
- Playbook with `shell: "rm -rf {{ user_input }}"` →  
  ```json
  {
    "result": "Fail",
    "reason": "Command injection risk detected due to unsafe use of shell with unvalidated input."
  }
  ```

- Playbook with `vars: { db_password: "SuperSecret123" }` →  
  ```json
  {
    "result": "Fail",
    "reason": "Hardcoded credentials found in variable definitions."
  }
  ```

- Playbook using Ansible Vault for secrets and no unsafe commands →  
  ```json
  {
    "result": "Pass",
    "reason": ""
  }
  ```

---
