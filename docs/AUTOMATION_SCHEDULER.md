# Automation & Scheduler V0

## Purpose

Automation & Scheduler allows PMWizard to perform recurring intelligence work without making interactive API requests execute background jobs.

V0 automates deterministic Project Health snapshot capture.

The architecture is intentionally lightweight:

```text
Web / API
   ↓
automation_schedules
   ↓
PostgreSQL durable queue state
   ↓
Automation Worker
   ↓
Task Handler
   ↓
Project Health Snapshot
   ↓
automation_runs
```

No Celery, Kafka, Kubernetes, or external scheduler is required.

## V0 task

The first supported task is:

```text
health_snapshot
```

It calls the existing `ProjectHealthHistoryService.capture()` with:

```text
captured_by = null
capture_source = automation
```

This means automated snapshots remain distinguishable from manual PM captures.

## Why Source Sync is not exposed yet

The scheduler has a handler abstraction designed for additional task types.

However, scheduling a production Source sync requires a secure runtime resolver for:

- connector configuration;
- credentials/tokens;
- tenant/project ownership;
- provider-specific refresh behavior.

The current Sources workspace deliberately stores only safe connection metadata.

V0 therefore does not expose a Source Sync schedule that would pretend those secrets are available.

A future Source Sync handler can plug into the same worker once credential resolution is production-safe.

## Persistence

Migration:

```text
0006_automation_scheduler_v0
```

adds:

```text
automation_schedules
automation_runs
```

### automation_schedules

Stores:

- tenant;
- Project;
- task type;
- display name;
- interval in minutes;
- enabled state;
- safe task config;
- next run time;
- pending trigger;
- last run/status;
- consecutive failure count;
- creator;
- lease owner;
- lease expiration;
- timestamps.

### automation_runs

Stores every execution attempt:

- Schedule/Project;
- task type;
- scheduled/manual trigger;
- status;
- worker ID;
- scheduled-for timestamp;
- start/finish timestamps;
- sanitized result summary;
- sanitized error message.

Run states:

```text
running
success
failed
abandoned
```

## Lease model

The worker does not rely on an in-memory lock.

A due schedule is claimed through a conditional database update:

```text
enabled
AND next_run_at <= now
AND (
  lease_expires_at IS NULL
  OR lease_expires_at <= now
)
```

The successful worker writes a unique lease token.

If two workers see the same due schedule, only one conditional update can own the lease.

## Crash recovery

If a worker disappears while a job is running:

1. the lease eventually expires;
2. another worker can claim the Schedule;
3. any previous unfinished `running` run is marked `abandoned`;
4. a new run attempt is created.

The old worker cannot finalize the stale run after its lease has been replaced.

This prevents late writes from an expired worker from overwriting the recovered execution.

## Lease duration boundary

V0 has no lease heartbeat.

Tasks should complete comfortably inside:

```text
PMWIZARD_AUTOMATION_LEASE_SECONDS
```

Default:

```text
300 seconds
```

Long-running connector jobs should introduce lease renewal before they are added as production automation handlers.

## Scheduling model

V0 uses interval schedules rather than cron expressions.

Allowed interval:

```text
5 minutes – 10080 minutes
```

The Web workspace currently offers:

```text
1 hour
6 hours
12 hours
Daily
Weekly
```

After a run finishes, the next run is scheduled from completion time:

```text
next_run_at = finished_at + interval
```

This avoids immediate catch-up storms after downtime.

## Run now

`Run now` does not execute work inside the API request.

It sets:

```text
next_run_at = now
pending_trigger = manual
```

The next worker claim executes it.

After completion the Schedule returns to:

```text
pending_trigger = scheduled
```

and resumes its normal cadence from that completion.

## Worker

Run continuously:

```bash
python -m pmwizard.automation.worker
```

Process one due batch and exit:

```bash
python -m pmwizard.automation.worker --once
```

This makes the worker suitable for:

- local development;
- a long-running process;
- a container;
- a platform scheduled invocation using `--once`.

## Worker configuration

```text
PMWIZARD_DATABASE_URL
PMWIZARD_AUTOMATION_POLL_SECONDS=15
PMWIZARD_AUTOMATION_LEASE_SECONDS=300
PMWIZARD_AUTOMATION_BATCH_SIZE=10
PMWIZARD_AUTOMATION_WORKER_ID=
```

If `PMWIZARD_AUTOMATION_WORKER_ID` is empty, PMWizard generates a process-specific ID from hostname, PID, and a short UUID.

## API

Read workspace:

```text
GET /v1/projects/{project_id}/automations
```

Requires:

```text
project:read
```

Create:

```text
POST /v1/projects/{project_id}/automations
```

Update:

```text
PATCH /v1/projects/{project_id}/automations/{schedule_id}
```

Queue now:

```text
POST /v1/projects/{project_id}/automations/{schedule_id}/run-now
```

Mutations require:

```text
project:read
project:review
```

## Web workspace

Navigation adds:

```text
Automations
```

The workspace shows:

- total schedules;
- enabled schedules;
- active leases;
- due jobs;
- failing schedules;
- next run;
- last run;
- cadence;
- consecutive failures;
- recent execution history.

Authorized reviewers can:

- create automatic Health snapshots;
- change cadence;
- pause/reactivate;
- queue Run now.

Read-only Project members can inspect schedules and history.

## Handler architecture

Execution is provider-neutral at the scheduler layer:

```text
AutomationClaim
      ↓
AutomationExecutor
      ↓
AutomationHandler registry
      ↓
HealthSnapshotAutomationHandler
```

Future handlers can include:

- Source Sync;
- grounded Status Report generation;
- Progress Intelligence refresh;
- notification delivery;
- Program/Portfolio materialization.

Each handler should remain explicit about its security and idempotency requirements.

## Failure behavior

A handler exception does not crash the Schedule definition.

The run becomes:

```text
failed
```

The sanitized exception is persisted in run history.

The Schedule increments:

```text
consecutive_failures
```

A later successful run resets that counter to zero.

## Governance

Automation does not bypass PMWizard's Human-in-the-Loop model.

Automated Health snapshots observe governed state.

They do not:

- accept Inbox suggestions;
- mutate Action Items;
- approve Decisions;
- close RAID;
- publish AI reports;
- write to external systems.

## Deferred

- cron/calendar schedules;
- timezone-aware wall-clock schedules;
- worker heartbeats;
- lease renewal;
- retry/backoff policies;
- Source Sync credential resolver;
- scheduled AI Status Reports;
- Program/Portfolio jobs;
- notification delivery;
- organization-level administration;
- delete/archive Schedule API.

## Guiding principle

> Automate observation and computation first; keep governance-changing actions human-controlled.
