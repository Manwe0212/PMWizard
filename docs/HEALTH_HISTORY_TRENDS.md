# Health History + Trends V0

## Purpose

Health History + Trends turns Project Health from a current-state assessment into an auditable time series.

It answers:

```text
How healthy is the project now?
How healthy was it before?
Is the score improving, stable, or deteriorating?
Which factors changed?
Which health drivers appeared or were resolved?
```

## Snapshot boundary

Reading Project Health remains side-effect free.

```text
GET /v1/projects/{project_id}/health
```

does not create history.

A historical point is created only through an explicit capture:

```text
POST /v1/projects/{project_id}/health/snapshots
```

The capture endpoint requires:

```text
project:read
project:review
```

A future scheduler may call the same service without changing the scoring model.

## Persistence

Migration `0004_health_history_trends_v0` adds:

```text
project_health_snapshots
```

Each record stores:

- captured timestamp;
- capturing user when applicable;
- capture source;
- model version;
- score;
- health band;
- coverage;
- factor scores;
- top key drivers;
- the complete Project Health snapshot payload;
- a deterministic SHA-256 state fingerprint.

Snapshots are historical observations. They do not modify Project Memory, Action Items, RAID, Decisions, or Sources.

## Duplicate protection

An identical Project Health state captured again within five minutes returns the existing snapshot.

This prevents accidental double clicks from creating false historical events.

The same state may be captured again after five minutes. This is intentional because repeated observations over time can demonstrate stability.

## History API

```text
GET /v1/projects/{project_id}/health/history?limit=90
```

The endpoint requires `project:read`.

Limits:

```text
minimum: 2
default: 90
maximum: 365
```

History is returned chronologically for charting.

## Trend model

Trend compares the two latest captured snapshots.

```text
score delta >= +3  → improving
score delta <= -3  → deteriorating
-2 through +2      → stable
```

If fewer than two snapshots exist, or either snapshot has no numeric score:

```text
insufficient_history
```

The ±3 threshold prevents tiny score changes from being presented as meaningful direction.

## Factor deltas

For every factor available in both latest snapshots:

```text
latest factor score - previous factor score
```

Example:

```text
Delivery    -18
RAID        -10
Decisions     0
Sources      +35
```

Unavailable factors are not forced into the comparison.

## Driver changes

Trend also compares negative driver titles.

A driver appearing in the latest snapshot but not the previous snapshot is returned as:

```text
new_drivers
```

A driver that existed previously but is no longer present is returned as:

```text
resolved_drivers
```

Example:

```text
New:
+ Blocked Action Items
+ Materialized Risks

Resolved:
✓ Failed Source Connections
```

## Coverage trend

Coverage is tracked separately from score.

This matters because a project can appear to improve numerically while the amount of governed data supporting the assessment falls.

Trend therefore returns:

```text
score_delta
coverage_delta
```

and keeps coverage visible in the UI.

## Web experience

Project Health now contains a Health History & Trend panel with:

- trend direction;
- latest score delta;
- coverage delta;
- score timeline;
- Green/Amber/Red thresholds;
- factor deltas;
- new drivers;
- resolved drivers;
- snapshot count;
- explicit snapshot capture.

Users without `project:review` can see history but cannot capture new snapshots.

## BFF

The browser calls:

```text
GET  /api/health/history
POST /api/health/history
```

Next.js supplies the HttpOnly Bearer session and selected project server-side.

## Model versioning

Every historical snapshot stores:

```text
model_version = project-health-v0
```

This is important because future scoring versions may change weights or rules.

Historical records should preserve the model that produced them rather than silently recalculating old history under new rules.

## V0 boundaries

Deferred:

- scheduled/daily automatic snapshots;
- retention policies;
- trend windows longer than latest-vs-previous;
- moving averages;
- anomaly detection;
- portfolio/program trend rollups;
- notifications when health crosses a threshold;
- comparison of scoring-model versions;
- historical drilldown to the exact underlying canonical entity state.

## Guiding principle

> Current Health explains the project now. History proves how that assessment changed over time.
