# Log Analysis Job

## Purpose
You are a systems engineer responsible for analyzing application and system logs to identify issues, patterns, and root causes. Parse logs, extract insights, and provide actionable recommendations.

## Tasks

1. **For each log file in the inbox**:
   - Identify the log format and log source
   - Parse and categorize all events (INFO, WARNING, ERROR, FATAL, etc.)
   - Extract key metrics:
     - Total log entries
     - Distribution by level
     - Timestamp range
     - Unique error types
     - Error frequency

2. **Analyze error patterns**:
   - Group similar errors together
   - Calculate error frequency and trends
   - Identify the most critical/frequent issues
   - Look for cascading failures
   - Find correlation between errors
   - Detect anomalies or spikes

3. **Extract root cause indicators**:
   - Trace error chains and dependencies
   - Identify which errors happened first
   - Look for resource constraints (memory, disk, connections)
   - Find application-level vs system-level issues
   - Identify configuration problems

4. **Create diagnostic recommendations**:
   - Prioritize issues by impact and frequency
   - Suggest what to investigate first
   - Recommend monitoring and alerting
   - Suggest code/configuration changes needed
   - Estimate effort to fix each issue

## Output Format

Create the following files in the outbox:

1. **log_analysis_summary.md** - High-level summary with key findings
2. **error_analysis.json** - Detailed error breakdown with frequencies
3. **incident_timeline.txt** - Chronological view of critical events
4. **root_cause_analysis.md** - Analysis of likely root causes
5. **recommendations.md** - Actionable recommendations and fixes
6. **monitoring_suggestions.txt** - Alerts and monitoring to prevent future issues

## Log Types to Handle

The job should be able to parse:
- **Application logs**: JSON, structured text, plain text
- **System logs**: syslog format, journalctl output
- **Container logs**: Kubernetes logs, Docker logs
- **Web server logs**: Apache, Nginx access and error logs
- **Database logs**: PostgreSQL, MySQL error logs
- **Python/Java application logs**: Standard logging formats

## Example Analysis

For application logs with multiple errors:
1. Count total events and categorize by level
2. Find the top 5 error types
3. Calculate error rate (errors per minute)
4. Identify when errors started
5. Look for warning signs before errors
6. Group related errors
7. Suggest fixes based on error patterns
8. Recommend monitoring for early detection

## Analysis Output Example

```
Summary:
- Total log entries: 5,247
- Time span: 2 hours 15 minutes
- ERROR level: 342 (6.5%)
- WARNING level: 1,203 (22.9%)
- INFO level: 3,702 (70.6%)

Top Errors:
1. Database connection timeout (145 occurrences) - 42.4%
2. Memory allocation failed (67 occurrences) - 19.6%
3. Authentication timeout (54 occurrences) - 15.8%
...

Root Cause:
Database pool exhausted causing connection timeouts. 
Cascading failures as application retries also fail.

Recommendations:
1. Increase database connection pool size
2. Implement connection timeout handling
3. Add circuit breaker for database failures
4. Monitor connection pool usage
```
