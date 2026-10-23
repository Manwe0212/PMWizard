# Project Health V0

## Purpose

Project Health V0 turns governed project state into an explainable operational health assessment.

It does not ask an LLM to label a project green, amber, or red.

The model is deterministic:

```text
Project Memory + Source Health
          ↓
four explicit scoring factors
          ↓
weighted normalized score
          ↓
Green / Amber / Red
          +
assessment coverage
          +
human-readable drivers
```

## API

```text
GET /v1/projects/{project_id}/health
```

The endpoint requires authenticated project membership and `project:read`.

No Project Health state is persisted in V0. The assessment is calculated from the current governed Project Memory and Sources snapshot each time it is requested.

## Factor weights

```text
Delivery   35%
RAID       35%
Decisions  15%
Sources    15%
          ----
          100%
```

Only factors with governed data participate in the weighted score.

A missing factor is excluded rather than treated as 100/100.

The percentage of model weight that has usable data becomes `coverage_percent`.

## Overall thresholds

```text
Green  80–100
Amber  60–79
Red     0–59
```

When less than 35% of the model has data, the numeric score is considered provisional and the overall band is `insufficient_data`.

Coverage is reported separately:

```text
High    75–100%
Medium  50–74%
Low      0–49%
```

This prevents a new/empty project from appearing healthy merely because no risks or overdue work have been recorded.

## Delivery — 35%

Delivery is available when the project has Action Items or schedule dates.

The factor starts at 100.

### Blocked Action Items

Penalty is proportional to the share of open Action Items that are blocked:

```text
penalty = 35 × blocked / open
max = 35
```

### Overdue Action Items

Penalty is proportional to open Action Items whose due date is before the assessment date:

```text
penalty = 30 × overdue / open
max = 30
```

### Pending external

Penalty is proportional to open Action Items in `pending_external`:

```text
penalty = 15 × pending_external / open
max = 15
```

### Forecast schedule slip

When forecast end is later than planned end:

```text
1–7 days     -10
8–30 days    -20
>30 days     -30
```

Delivery cannot fall below 0.

## RAID — 35%

RAID is available when at least one Risk, Assumption, Issue, or Dependency exists.

The factor starts at 100.

Penalties:

```text
Materialized Risk             -20 each, max -40
High/Critical open Risk       -10 each, max -25
Blocked Issue                 -15 each, max -30
High/Critical unresolved Issue -10 each, max -25
Blocked Dependency            -12 each, max -25
Invalidated Assumption         -8 each, max -15
```

A record can legitimately contribute to more than one explicit signal. For example, a blocked high-severity Issue represents both execution blockage and high impact.

The factor is clamped at 0.

Severity matching recognizes values such as:

```text
critical / very high / severe
high / major
medium / moderate
low / minor
```

Unknown/custom labels are not guessed.

## Decisions — 15%

Decisions are available when governed Decision records exist.

The factor starts at 100.

### Decision debt

Proposed or pending decisions:

```text
-10 each
max -40
```

### Overdue reviews

Decision review dates before the assessment date are penalized unless the decision has already been rejected, superseded, or reversed:

```text
-15 each
max -30
```

Historical rejected/superseded/reversed decisions remain part of Project Memory but do not automatically make current health worse.

## Sources — 15%

Sources is available when at least one enabled SourceConnection exists.

Each enabled source maps to a deterministic health score:

```text
healthy       100
attention      65
never_synced   45
failed         20
```

The Sources factor is the arithmetic average across enabled sources.

Disabled sources are excluded from the factor.

## Weighted score

Available factors are normalized so missing data does not inflate health.

Example:

```text
Delivery   80 × 35
RAID       60 × 35
Sources   100 × 15
Decisions unavailable

available weight = 85

overall =
(80×35 + 60×35 + 100×15) / 85
= 75
= Amber

coverage = 85%
```

## Key drivers

Every negative rule creates a `HealthSignal` with:

- severity;
- title;
- human-readable explanation;
- explicit penalty;
- canonical entity type;
- entity IDs.

The API surfaces the five largest current negative drivers.

The Web therefore explains *why* the project is red/amber/green rather than only displaying a color.

## Web workspace

The authenticated project navigation now includes:

```text
Project Health
Project Inbox
Project Memory
Sources
```

Project Health Web V0 shows:

- overall score;
- Green/Amber/Red/Insufficient Data;
- assessment coverage;
- Delivery factor;
- RAID factor;
- Decisions factor;
- Sources factor;
- factor-level signals and penalties;
- top key drivers;
- scoring weights and thresholds.

## Governance boundary

Project Health is read-only.

It consumes:

```text
Governed Project Memory
+
Durable Source telemetry
```

It does not:

- accept/reject suggestions;
- mutate Project Memory;
- change connector state;
- write RAG status back into source systems;
- use opaque LLM reasoning.

## Deferred

Future versions may add:

- calibrated weights from historical project outcomes;
- financial/budget health;
- milestone/schedule variance models;
- stakeholder sentiment;
- trend history;
- health snapshots over time;
- portfolio/program rollups;
- organization-specific scoring policies;
- predictive risk modeling;
- AI-generated narrative summaries grounded in deterministic signals.

Those additions should preserve explainability and allow the deterministic V0 score to remain auditable.

## Guiding principle

> A health score is useful only when the Project Manager can see why it exists.
