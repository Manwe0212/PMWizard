# Notification Delivery & Preferences V0

## Purpose

Notification Delivery extends the deterministic Attention Center without introducing a second rules engine.

The delivery path is:

```text
Project Memory / Health / Sources / Automations / Inbox
                     ↓
             AttentionCenterService
                     ↓
              active signal versions
                     ↓
        NotificationPreference filters
                     ↓
        NotificationDeliveryWorker
               ↓             ↓
             Email         Teams
```

The Attention Center remains the only place where notification-worthy project conditions are calculated.

## Personal preferences

Preferences are scoped by:

```text
tenant + user + project
```

V0 supports:

- master enable / disable;
- account email delivery;
- Microsoft Teams webhook delivery;
- minimum severity;
- category filters;
- interval cadence;
- recent sanitized delivery history.

Preference changes require only `project:read` because they are personal delivery settings and do not modify governed Project Memory.

## Channels

### Email

Email always targets the authenticated PMWizard account email.

Users cannot supply an arbitrary destination address.

Runtime SMTP configuration:

```text
PMWIZARD_NOTIFICATION_SMTP_HOST
PMWIZARD_NOTIFICATION_SMTP_PORT
PMWIZARD_NOTIFICATION_EMAIL_FROM
PMWIZARD_NOTIFICATION_SMTP_STARTTLS
PMWIZARD_NOTIFICATION_SMTP_CREDENTIAL_REF
```

The credential reference is optional.

If configured:

```text
PMWIZARD_NOTIFICATION_SMTP_CREDENTIAL_REF=env:SMTP_NOTIFICATIONS
```

the worker resolves:

```text
PMWIZARD_SECRET_SMTP_NOTIFICATIONS
```

Expected secret JSON:

```json
{
  "username": "smtp-user",
  "password": "smtp-password"
}
```

The password is never stored in PostgreSQL.

### Microsoft Teams

A preference may store only an opaque alias:

```text
env:TEAMS_PROJECT_ALERTS
```

The worker resolves:

```text
PMWIZARD_SECRET_TEAMS_PROJECT_ALERTS
```

whose value is the HTTPS Teams/Workflow webhook URL.

The API and Web UI expose only:

```text
teams_webhook_configured = true | false
```

They never return the alias or resolved URL.

Only `env:TEAMS_*` aliases are accepted for Teams delivery.

## Migration

```text
0010_notification_delivery_v0
```

adds:

```text
notification_preferences
notification_deliveries
```

### notification_preferences

Stores:

- tenant;
- user;
- Project;
- enabled state;
- channel enablement;
- Teams secret alias;
- minimum severity;
- category list;
- interval;
- next / last delivery timestamps;
- worker lease state.

### notification_deliveries

Stores sanitized operational history:

- preference;
- user;
- Project;
- channel;
- success / failed;
- delivered signal IDs;
- signal count;
- attempted / delivered timestamps;
- sanitized error.

No email password or Teams webhook is stored.

## Delivery semantics

The worker delivers only signals whose personal Attention state is:

```text
unread
```

It does not deliver:

- seen;
- acknowledged;
- snoozed.

Delivery itself does not mutate the Attention receipt.

Therefore:

```text
Signal = unread
      ↓
Email delivered
      ↓
Signal still = unread
```

The user must still open, acknowledge, snooze, or resolve the underlying condition through PMWizard.

## Severity filter

Order:

```text
critical > warning > info
```

Examples:

```text
minimum = critical
→ critical only

minimum = warning
→ warning + critical

minimum = info
→ all
```

## Category filter

V0 categories reuse Attention Center categories:

- health;
- execution;
- raid;
- decision;
- source;
- automation;
- review.

No separate notification category taxonomy is introduced.

## Deduplication

Attention signal IDs are already versioned by:

```text
signal_key + condition fingerprint
```

Successful delivery history records those IDs per channel.

Before sending:

```text
active eligible signal IDs
        -
successfully delivered IDs for channel
        =
new delivery batch
```

Therefore the same signal version is not repeatedly emailed or posted to Teams every worker cycle.

If the underlying condition changes materially, Attention Center produces a new signal ID and the new version becomes eligible for delivery.

Failed deliveries are not considered delivered and are retryable on the next cadence.

## Worker leases

Notification preferences use expiring database leases.

Multiple Automation Worker processes may poll the same database, but only one owns a due preference at a time.

A worker whose lease expires cannot finalize the preference cycle.

## Cadence

V0 supports a minimum of 15 minutes and a maximum of 7 days.

The Web workspace exposes common presets:

- every 15 minutes;
- hourly;
- every 4 hours;
- daily.

Changing preferences makes the preference immediately due for the next worker poll.

## Public application link

Optional:

```text
PMWIZARD_PUBLIC_BASE_URL=https://pmwizard.example.com
```

When configured, outbound messages include a generic PMWizard link.

V0 does not create signed deep links or embed authentication tokens in notifications.

## API

Read preferences and history:

```text
GET /v1/projects/{project_id}/notifications
```

Save personal preferences:

```text
PUT /v1/projects/{project_id}/notifications
```

Both require:

```text
project:read
```

## Failure safety

Provider failures are converted to safe operational messages.

For example, a Teams exception containing the resolved webhook URL is persisted only as:

```text
Microsoft Teams notification delivery failed.
```

SMTP credential material and webhook URLs never enter delivery history.

## Governance boundary

Notification Delivery does not:

- accept Project Inbox suggestions;
- edit Project Memory;
- acknowledge Attention signals;
- close risks/issues;
- approve decisions;
- repair Source failures;
- rerun failed Automations.

It delivers an authorized user's existing Attention signals through configured channels.

## Deferred

- Slack;
- mobile push;
- SMS;
- organization-wide routing policies;
- owner-based escalation;
- portfolio digest;
- quiet hours;
- timezone-aware scheduled digest windows;
- signed deep links;
- delivery-provider dashboards;
- bounce / webhook lifecycle handling.

## Guiding principle

> Deliver attention; never turn delivery into project truth.
