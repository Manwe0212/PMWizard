# Program & Portfolio Intelligence V0

## Purpose

Program & Portfolio Intelligence extends PMWizard from a single-project intelligence product into a cross-project operating view.

The hierarchy is:

```text
Portfolio
   ↓
Program
   ↓
Project
```

Projects remain the primary governed intelligence unit. Program and Portfolio views are deterministic rollups over authorized projects rather than independent sources of truth.

## Structure entities

PR #15 introduces first-class canonical entities:

```text
Portfolio
Program
```

Migration `0005_program_portfolio_intelligence_v0` adds:

```text
portfolios
programs
```

The existing Project fields:

```text
program_id
portfolio_id
```

now reference real PMWizard structure records.

## Structure service

`StructureService` supports controlled application-level creation and assignment:

```python
portfolio = service.create_portfolio(...)
program = service.create_program(...)
service.assign_project(
    tenant_id=tenant_id,
    project_id=project_id,
    program_id=program.id,
)
```

When a Program belongs to a Portfolio, assigning a Project to that Program inherits the Program Portfolio.

A conflicting explicit Portfolio assignment is rejected.

V0 intentionally does not yet expose hierarchy mutation through the public Web UI; that belongs in Settings / Administration.

## Authorization boundary

Cross-project intelligence must never enumerate a tenant.

The API resolves all visible projects from the authenticated user's `ProjectMembership` records and includes only memberships containing:

```text
project:read
```

Therefore:

```text
Tenant projects
      ↓
ProjectMembership filter
      ↓
Authorized projects only
      ↓
Program / Portfolio rollup
```

A Project outside the user's authorized set:

- is not counted;
- does not affect rollup score;
- does not appear in Program/Portfolio hierarchy;
- does not contribute to attention ranking;
- does not participate in shared Risk/Dependency detection.

The legacy trusted-header compatibility mode cannot call the cross-project overview because it cannot prove the user's complete membership set.

## API

```text
GET /v1/intelligence/overview
```

Bearer authentication is required.

The endpoint returns:

- overall authorized-project rollup;
- Portfolio rollups;
- Program rollups;
- direct Portfolio Projects;
- standalone Programs;
- standalone Projects;
- attention-ranked Projects;
- repeated active cross-project Risk and Dependency signals.

## Project intelligence cards

Every visible Project contributes:

```text
project identity
Program / Portfolio
status
priority
live health score
health band
health coverage
latest captured trend direction
latest trend delta
top deterministic health drivers
```

The health score is current/live.

Trend comes from persisted Health History and therefore remains `insufficient_history` until enough snapshots exist.

## Rollup score

A rollup score is calculated from projects whose Health band is not `insufficient_data`.

```text
rollup score =
average reliable Project Health score
```

Projects without reliable Health do not receive an artificial 100.

Rollup coverage is the arithmetic average of Project Health coverage across all visible Projects.

If:

```text
average coverage < 35%
```

the rollup band is:

```text
insufficient_data
```

even when a provisional numeric average exists.

This prevents one well-instrumented green Project from making a mostly-unobserved Portfolio appear green.

## Rollup metrics

Every Program / Portfolio summary includes:

```text
projects_total
projects_scored
score
band
average_coverage_percent

green
amber
red
insufficient_data

improving
stable
deteriorating
insufficient_history
```

## Attention ranking

The executive attention list prioritizes:

1. Red Projects;
2. deteriorating Projects;
3. Amber Projects;
4. insufficient-data Projects;
5. Green/stable Projects.

The list remains explainable because each Project card includes its current deterministic Health drivers.

## Cross-project signals

V0 does not use semantic AI inference to claim that two Risks are related.

A shared signal is created only when the same active Risk or Dependency title appears in at least two authorized Projects after conservative normalization:

```text
case-fold
punctuation → spaces
whitespace normalization
```

Example:

```text
"Vendor capacity"
"Vendor-capacity"

→ same normalized title
```

The signal contains:

- type: Risk or Dependency;
- representative title;
- Project count;
- visible Project IDs/names;
- current statuses;
- severity/criticality labels.

Closed Risks are excluded.

Dependencies with status:

```text
satisfied
waived
closed
```

are excluded.

This is intentionally conservative. Fuzzy/semantic cross-project relationship discovery can be introduced later as an AI-proposed relationship requiring governance.

## Web workspace

The main PMWizard navigation now includes:

```text
Program & Portfolio
Project Health
Project Inbox
Project Memory
Sources
```

Program & Portfolio is a cross-project workspace and therefore replaces the normal Project selector with:

```text
Scope: N authorized projects
```

The workspace shows:

- overall rollup score and coverage;
- authorized project count;
- projects needing attention;
- healthy/improving projects;
- cross-project Risk/Dependency signals;
- Portfolio → Program → Project hierarchy;
- direct Portfolio Projects;
- standalone Programs/Projects.

Selecting a Project from the rollup updates the active Project and opens its Project Health workspace.

## V0 performance boundary

V0 calculates live Health per authorized Project at request time.

This keeps the model simple and correct for an initial PMO-sized deployment.

Future versions may use:

- precomputed rollup snapshots;
- cached current Health;
- incremental portfolio materialization;
- asynchronous rollup refresh.

Those optimizations must preserve the same authorization boundary.

## Deferred

- Program/Portfolio admin UI;
- Program/Portfolio-specific memberships;
- strategic objective scoring;
- budget/benefit rollups;
- capacity/resource rollups;
- milestone rollups;
- AI-proposed cross-project relationships;
- cross-project dependency graph;
- Program/Portfolio historical trend snapshots;
- executive exports;
- portfolio optimization.

## Guiding principle

> Cross-project intelligence is a projection over authorized Project truth, never a shortcut around Project governance or permissions.
