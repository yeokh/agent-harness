# Incoming Support Cases

## Case 1: CRITICAL - Production Database Unavailable

**Ticket ID**: CASE-2026-0501
**Submitted**: 2026-05-25 10:30 AM
**Customer**: Global Financial Corp
**Contact**: DBA Team Lead

### Description
Our primary Oracle database cluster running on RHEL 8.6 has become completely unresponsive. All production applications depending on this database are down. We cannot connect to the database server at all - it's not responding on port 1521.

**Impact Details**:
- 8 critical business applications offline
- ~500 users unable to work
- Financial transactions cannot be processed
- Estimated business impact: $50,000+ per hour
- Customer-facing systems showing error pages

**Timeline**:
- Issue started at 10:15 AM
- 3 attempts to restart failed
- Database logs show nothing unusual before disconnect
- Network connectivity to server confirmed working

**Environment**:
- RHEL 8.6 with latest patches
- Oracle 19c Enterprise Edition
- 4-node RAC cluster (1 node down, others showing errors)
- VMware virtual machines
- 10TB database size

---

## Case 2: HIGH - API Performance Degradation

**Ticket ID**: CASE-2026-0502
**Submitted**: 2026-05-25 11:45 AM
**Customer**: TechStartup Inc
**Contact**: CTO

### Description
Our REST API endpoints hosted on RHEL 8.4 are responding very slowly. Normal response times are ~200ms, but we're seeing 5000-10000ms response times. Some requests are timing out (>30 seconds).

**Impact Details**:
- 15 customers affected
- API dashboard showing 60% error rate
- Mobile app experiencing timeouts
- Web application partially usable but slow
- Workaround: Users can wait longer or retry

**Timeline**:
- Started 30 minutes ago without any changes
- Coincides with sudden traffic spike
- Load balancer shows uneven distribution
- Backend servers showing high CPU (80-90%)

**Environment**:
- Kubernetes on Red Hat OpenShift 4.11
- Node.js application with 12 replicas
- Load balanced across 3 nodes
- Using persistent volume for data

---

## Case 3: MEDIUM - Dashboard Widget Not Rendering

**Ticket ID**: CASE-2026-0503
**Submitted**: 2026-05-25 01:30 PM
**Customer**: Manufacturing Corp
**Contact**: Application Owner

### Description
The "Production Metrics" widget on our monitoring dashboard stopped rendering properly. It shows an error message "Failed to load data" instead of the graphs. The dashboard is still functional for other areas.

**Impact Details**:
- 1 widget out of 8 not working
- Managers can view other metrics as workaround
- Data is being collected correctly (confirmed via API)
- Does not affect operational decisions immediately

**Timeline**:
- First noticed this morning
- Logs show no errors in the service
- Other widgets working fine
- Occurs in Chrome, Firefox, and Safari

**Environment**:
- RHEL 8.6 hosting the dashboard
- Grafana 9.2
- Prometheus backend
- Data source recently updated

---

## Case 4: LOW - Documentation Typo

**Ticket ID**: CASE-2026-0504
**Submitted**: 2026-05-25 02:15 PM
**Customer**: Internal Development Team
**Contact**: Senior Engineer

### Description
Found a typo in the Red Hat Enterprise Linux 8 installation guide (page 45, section 4.3). It says "partitiong" instead of "partitioning". This is in the PDF documentation provided with the subscription.

**Impact Details**:
- Cosmetic issue only
- Does not affect installation process
- Only affects people reading printed/PDF version
- No workaround needed (obvious what is meant)

**Timeline**:
- Discovered during documentation review
- Issue has been present for unknown duration

**Environment**:
- Documentation only
- No system impact

---

## Case 5: HIGH - Ansible Playbook Execution Failures

**Ticket ID**: CASE-2026-0505
**Submitted**: 2026-05-25 03:45 PM
**Customer**: Operations Team
**Contact**: Automation Lead

### Description
Our main Ansible playbooks running from Red Hat Ansible Automation Platform 2.2 are failing to execute all jobs. About 40% of scheduled jobs are not running, and those that do run are failing with timeout errors.

**Impact Details**:
- Critical infrastructure deployments blocked
- Configuration management out of sync
- 25+ hosts unable to receive updates
- Team cannot provision new servers
- Security patches not being applied (workaround: manual application)

**Timeline**:
- Started 4 hours ago
- Correlates with an update to the execution environment
- Failed jobs have varying symptoms
- Controller logs show "executor unavailable" warnings

**Environment**:
- Ansible Automation Platform 2.2 on RHEL 8.5
- 4 execution nodes
- 1 controller node
- Manages 150+ hosts

---

## Case 6: MEDIUM - Certificate Expiration Warning

**Ticket ID**: CASE-2026-0506
**Submitted**: 2026-05-25 04:20 PM
**Customer**: Identity Services Team
**Contact**: Security Officer

### Description
Our RHEL 8 system is showing a warning that an SSL certificate will expire in 60 days. This is for an internal authentication service that is not internet-facing.

**Impact Details**:
- Warning only - services still functioning
- Certificate is valid for 60 more days
- Used only by internal applications (10-15 users)
- Renewal process is standard procedure
- No immediate action required but planning needed

**Timeline**:
- Automated alert triggered
- Certificate was issued 2 years ago
- Normal certificate lifecycle

**Environment**:
- RHEL 8.6
- Self-signed internal certificate
- Used for LDAP over SSL
