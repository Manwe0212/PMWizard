# PR #36 — Executive Intelligence & Demo Experience

## Objective

Improve the PMWizard Executive Dashboard's usefulness in a technical
assessment by highlighting **next actions**, not only reporting scores
and counts. This is a frontend presentation feature. It does not
introduce AI-generated advice, new decision logic or backend writes.

## What changed

- A new **What needs attention next?** section below the executive KPIs.
- Up to three highlighted entries derived exclusively from authorized
  `ExecutiveDashboardSnapshot` data.
- Priority order: critical RAID, pending decisions, human review,
  then source alerts. This is a fixed UI ordering, not a predictive rank.
- Each card links to the correct existing project view (Project Memory,
  Project Inbox or Sources), preserving selected project context.
- Responsive layout, accessible named section and a truthful empty state.
- Explicit notice that highlights are governed records and not AI suggestions.

## Acceptance checklist

- Log in to the synthetic Atlas Delivery demo.
- Confirm the executive KPIs and critical RAID lists are unchanged.
- Confirm priority cards show actual data present in the dashboard;
  do **not** expect fixed titles or counts after user actions.
- Click a Critical RAID card and verify it opens the matching project
  in Project Memory.
- Click a decision/review/source card where present.
- Confirm no backend mutation occurs merely from opening a card.
- Verify narrow window layout and source/decision/Inbox empty conditions.
- Confirm `Status Reports` still shows the English optional
  integration walkthrough, without claiming a paid provider.

## Scope limits

This is not an automated remediation engine and does not calculate
a new risk score. Up to three highlights may omit other issues; the
complete inventory remains in existing panels. A production pilot
would require user research into priority ordering and verification
across multiple portfolios.
