# Project Notifications & Attention Center V0

## Purpose

Attention Center gives each Project user one deterministic place to see active conditions that require intervention.

It is not a second Project Memory.

Signals are recomputed from current governed state and operational telemetry:

```text
Project Memory
Project Health
Health History
Sources
Automations
Project Inbox
      ↓
AttentionCenterService
      ↓
active deterministic signals
      ↓
per-user receipt state
      ↓
Attention Center
```

## Signal truth boundary

Attention signals are projections.

They do not become canonical facts and are not persisted as a duplicate copy of Action Items, RAID, Decisions, Source state, or Health.

If an underlying condition resolves, its Attention signal disappears automatically.

Example:

```text
Action Item = blocked
      ↓
attention signal active

Action Item = completed
      ↓
attention signal absent
```

No separate "close notification" workflow is required.

## V0 signal rules

### Health

- Project Health red → critical.
- Project Health amber → warning.
- Health Trend deteriorating → warning.
- Health Trend score delta <= -10 → critical.

### Execution

- blocked Action Item → critical;
- overdue open Action Item → warning;
- overdue Action Item with critical/severe priority → critical.

### RAID

- materialized Risk → critical;
- active Risk with critical/severe impact → critical;
- active Risk with high impact → warning;
- invalidated Assumption → warning;
- blocked Issue → critical;
- active high Issue → warning;
- active critical/severe Issue → critical;
- blocked Dependency → critical;
- active high Dependency → warning;
- active critical/severe Dependency → critical.

### Decisions

A proposed/pending Decision whose review date is in the past becomes an Attention signal.

- less than 7 days overdue → warning;
- 7+ days overdue → critical.

### Sources

- failed latest Source run → critical;
- partial/error/skip Source run → warning;
- enabled credential-ready Source with no sync yet → info;
- failed connection test → warning.

### Automations

An enabled Automation whose latest run is failed or abandoned becomes an Attention signal.

- fewer than 3 consecutive failures → warning;
- 3+ consecutive failures → critical.

### Project Inbox

Authorized pending Inbox suggestions are aggregated into one review signal.

The signal uses the same Evidence permission filtering as Project Inbox.

- pending < 3 days → info;
- oldest pending >= 3 days → warning.

## Versioned signals

Each logical condition has a stable `signal_key`.

Examples:

```text
action:blocked:<action-id>
source:health:<source-id>
automation:failure:<schedule-id>
health:trend
```

A fingerprint is calculated from the current condition version.

The externally returned signal ID is derived from:

```text
signal_key + fingerprint
```

Therefore:

```text
same condition version
→ same signal ID

condition changes
→ new signal ID
→ unread again
```

This prevents an old acknowledgement from suppressing a materially changed problem.

## Personal receipts

Migration:

```text
0009_attention_center_v0
```

adds:

```text
attention_receipts
```

The table stores only user interaction state:

- tenant;
- user;
- Project;
- signal key;
- signal fingerprint;
- seen timestamp;
- acknowledged timestamp;
- snoozed-until timestamp;
- timestamps.

It does not store a duplicate signal title/detail or canonical project data.

Unique boundary:

```text
tenant + user + project + signal_key
```

## User states

```text
unread
seen
acknowledged
snoozed
```

### Seen

The user opened or explicitly marked the current signal version as seen.

### Acknowledged

The user confirms awareness of the active condition.

Acknowledgement does not resolve or mutate the underlying project entity.

### Snoozed

The signal remains active but is temporarily deferred for that user.

V0 snooze maximum:

```text
30 days
```

The Web workspace currently offers a 24-hour shortcut.

When snooze expires, the signal returns to `seen` if the same condition remains active.

### Reset / Reopen

Clears personal interaction state for the current signal version.

## Permission model

Read Attention Center:

```text
project:read
```

Update personal receipt state:

```text
project:read
```

`project:review` is intentionally not required because Attention receipts do not mutate governed Project Memory.

Inbox-derived Attention signals still pass through the caller's Evidence permissions.

## API

Read:

```text
GET /v1/projects/{project_id}/attention
```

Change personal state:

```text
POST /v1/projects/{project_id}/attention/{signal_id}/state
```

Body examples:

```json
{ "action": "seen" }
```

```json
{ "action": "acknowledge" }
```

```json
{
  "action": "snooze",
  "snoozed_until": "2026-10-31T16:00:00Z"
}
```

```json
{ "action": "reset" }
```

State mutation validates that the signal ID is still active.

A stale/resolved signal cannot be acknowledged after it disappears.

## Web workspace

Navigation adds:

```text
Attention Center
```

The sidebar badge shows unread active signals.

Workspace summary:

- Unread;
- Critical;
- Warnings;
- Snoozed.

Filters:

- All;
- Unread;
- Critical;
- Snoozed.

Actions:

- Open target workspace;
- Acknowledge;
- Snooze 24h;
- Reopen.

Target routing:

```text
Health → Project Health
Execution / RAID / Decision → Project Memory
Source → Sources
Automation → Automations
Review → Project Inbox
```

Opening an unread signal first marks that version seen.

## Notifications boundary

V0 is an in-app Notification / Attention Center.

It does not send:

- email;
- Teams messages;
- Slack messages;
- SMS;
- push notifications.

Outbound delivery should consume the same deterministic signals in a later version rather than create a separate rule engine.

## Governance

Attention Center never:

- accepts an AI suggestion;
- edits Action Items;
- closes RAID;
- approves Decisions;
- changes Health;
- repairs Sources;
- reruns Automations automatically.

It tells the user where intervention is required and routes them to the governed workspace that owns the action.

## Deferred

- outbound email/Teams/Slack delivery;
- organization notification preferences;
- configurable signal thresholds;
- batched daily digests;
- portfolio-level personal Attention Center;
- escalation policies;
- assignment/routing to specific owners;
- acknowledgement analytics;
- mobile push.

## Guiding principle

> Attention is derived from truth; acknowledging attention does not change truth.
