# Diagnostic Data Gathering Job

## Purpose

You are a support engineer tasked with gathering diagnostic data for Red Hat systems experiencing issues. Use the Red Hat Diagnostic Data Gathering skill ("**SKILL-red-hat-diagnostics.md**") to provide step-by-step instructions for collecting necessary diagnostic bundles.

## Tasks

1. **For each system listed in the inbox**, determine the appropriate diagnostic commands:

   * If the system is RHEL: Generate sosreport collection commands
   * If the system is OpenShift/Kubernetes: Generate must-gather commands
   * If the system is Ansible Automation Platform: Generate diagnostic bundle commands
   * If the system is mixed/unclear: Provide commands for all applicable types
2. **Document the diagnostic process**:

   * List all commands needed
   * Explain what each command collects
   * Provide estimated collection time
   * List expected output file sizes
   * Note any prerequisites or permissions needed
3. **Create a diagnostic checklist**:

   * What to collect
   * How to collect it
   * Where to store it
   * How to transfer to support
   * Retention/cleanup recommendations
4. **Generate a runbook**:

   * Step-by-step bash script to automate collection
   * Include error handling
   * Add status reporting
   * Include compression and archiving

## Output Format

Create the following files in the outbox:

1. **diagnostic\_checklist.md** - Detailed checklist with all diagnostics needed
2. **command\_runbook.sh** - Executable bash script for automation
3. **collection\_instructions.txt** - Human-readable step-by-step guide
4. **support\_package\_guide.md** - How to prepare and transfer to Red Hat Support

## Example

For a RHEL 8 system with performance issues:

* sosreport with performance data
* dmesg and journal logs
* Network configuration and statistics
* Process information and system state

Write a comprehensive guide to gather all this data.

