# Root Cause Analysis

Timeline and likely root causes:
- 2026-05-25T08:21:15: Kernel reports Out of memory and kills process 5432 (java). This indicates host-level memory exhaustion.
- Shortly after, application.service exits and restarts (systemd logs). Application-level logs show DB pool warnings before and errors after this event.
- 2026-05-25T08:21:32 - 2026-05-25T08:21:41: Multiple Failed to acquire database connection errors and user request failures appear; these coincide with the OOM event and service restarts.
- 2026-05-25T08:22:00: Kernel logs an EXT4 I/O error on device dm-0. This may be unrelated or caused by storage under stress during backup.

Analysis:
- Primary root cause appears to be host memory pressure leading to OOM kill of a Java process (likely the database or another critical service), causing temporary unavailability of the database and connection pool exhaustion in the application.
- Secondary contributors: high API request rate around 08:50 (later) and a slow query / missing index noted at 08:40 that can increase resource usage. Backup job at 08:30 increased I/O.
- Disk I/O error and audit DENIED messages indicate possible configuration (apparmor) or storage reliability issues that should be investigated.
