# Entity Resolution V0

## Purpose

Entity Resolution answers a foundational PMWizard question:

> When new project evidence arrives, does it refer to an existing project entity or something new?

V0 focuses only on resolving new Evidence against existing open Action Items.

Examples:

```text
Existing Action Item:
Verify API access

New email:
"API access has been verified and is working."
```

PMWizard should recognize the existing Action Item as a plausible match instead of automatically creating a duplicate.

---

## V0 Principles

### Explainable before sophisticated

V0 uses deterministic scoring rather than embeddings or an LLM.

Every candidate exposes the factors contributing to its score.

### Project and tenant scoped

Resolution runs only against Action Items that are:

- inside the same Project;
- accessible to the current tenant;
- still open (`not_started`, `in_progress`, `blocked`, `pending_external`, or
  `ready_for_review`; `completed` and `cancelled` are excluded).

`ProjectMemoryResolutionService` loads candidates using both tenant and project
filters. Its `tenant_id` must come from trusted application context. It verifies
that the project belongs to that tenant; it does not authenticate a user, check
project membership, or evaluate `Evidence.permission_scope`. The caller must
authorize the user and the source evidence before invoking this service.

`ActionItemResolver` is a pure scoring API, not an authorization boundary. It
filters supplied items by project and open status, but its domain objects do not
carry tenant identity. Use the service for persisted candidates and never pass
unauthorized candidate data to the resolver.

### Resolution is not project-state mutation

Matching Evidence to an Action Item does not mark the Action Item complete, blocked, or otherwise change governed state.

Progress interpretation remains a separate intelligence step governed by Human Review.

V0 only returns a `ResolutionResult`. It does not persist an Evidence–Action Item
relationship, update `latest_evidence_id`, create an Action Item, or write review
or audit records. A caller must handle any later authorized linking separately.

### Ambiguity is surfaced

When multiple candidates are plausible, PMWizard returns `needs_review` rather than forcing a match.

---

## Outcomes

### matched

A candidate has a sufficiently high and distinct deterministic score.

This means PMWizard may link the Evidence to the entity without interpreting the operational status of that entity.

### needs_review

At least one plausible candidate exists, but the score is not strong enough or multiple candidates are too close.

A later Project Inbox flow can ask the PM to select the correct entity.

### no_match

No existing Action Item reaches the minimum candidate threshold.

The Evidence may describe:

- a new Action Item;
- another entity type;
- general project context;
- irrelevant information.

---

## V0 Scoring Factors

The Action Item resolver currently considers:

```text
Exact title phrase      25%
Title keyword coverage  35%
Text similarity         10%
Token overlap           15%
Owner match             10%
Temporal proximity       5%
```

The score is a weighted lexical heuristic, not a calibrated probability. The six
weights above are fixed in V0 code. Constructor configuration currently covers
only `match_threshold`, `review_threshold`, and `ambiguity_margin`.

`ScoreBreakdown` contains unweighted factor values between 0 and 1. Multiply each
by its documented weight and sum them to reconstruct the score approximately
(the returned score and continuous factors are rounded to four decimal places).
The short `reasons` list highlights supporting factors rather than every
contribution.

Normalization lowercases text, strips accents and replaces punctuation with
spaces. Exact title matching requires a contiguous sequence of complete
normalized tokens: `review contract` is not an exact phrase match for
`review contracts`. Keyword factors separately apply a small English/Spanish
suffix reducer and stopword list; this is not semantic understanding. Only
`Evidence.content_excerpt` is scored. Owner hints must be supplied as structured
`ResolutionContext.owner_id`; names are not inferred from text.

Current default thresholds:

```text
Matched:       >= 0.78 and sufficiently distinct
Needs review:  >= 0.30
No match:      < 0.30

Ambiguity margin: 0.08
```

Thresholds must satisfy `0 <= review_threshold <= match_threshold <= 1`; the
ambiguity margin must be finite and within `[0, 1]`. A zero margin intentionally
allows tied scores to meet the separation rule; retain a positive margin when
ambiguity protection is required. Scores and the difference between the two best
scores are compared at four-decimal precision, so a margin of exactly `0.08`
qualifies.

The resolver ranks all eligible candidates by descending score, then by UUID
string for stable ties. `max_candidates` must be a positive integer (default 5)
and limits only the returned list: omitted competitors still affect ambiguity.
Consequently, a result with one returned candidate can still need review due to
an omitted competitor. Low-scoring candidates may be returned even for
`no_match`; in that case `best_candidate` is absent. Empty excerpts return
`no_match` with no candidates.

Temporal proximity uses `effective_at` (falling back to `captured_at`) and the
nearest of Action Item creation or last progress time: 1.0 within 7 days, 0.7
within 30, 0.4 within 90, and 0.1 otherwise. Naive timestamps are treated as UTC.
The example below assumes recent timestamps and no competing candidate.

These values are V0 defaults and should be evaluated with a representative benchmark dataset before production use.

---

## Example

```text
Action Item:
Confirm vendor access

Evidence:
"Confirm vendor access was completed today."

Resolution:
matched

Reasons:
- action title appears in evidence
- most Action Item keywords appear in evidence
- strong keyword overlap
- evidence is temporally close to the Action Item
```

This match does **not** mean the Action Item becomes Completed.

A later progress-intelligence step may propose:

```text
Suggested status: Completed
```

and Human Review governs whether that suggestion updates Project Memory.

---

## V0 Flow

```text
New Evidence
     ↓
Authorized Project Memory
     ↓
Open Action Items
     ↓
Deterministic candidate scoring
     ↓
┌──────────────┬──────────────┬──────────────┐
│   matched    │ needs_review │   no_match   │
└──────────────┴──────────────┴──────────────┘
```

---

## Deferred to Later Versions

V0 deliberately does not include:

- embeddings / pgvector candidate search;
- LLM-assisted classification;
- cross-project entity resolution;
- automatic creation of new Action Items;
- RAID or Decision resolution;
- semantic synonym models;
- organization-specific learned weights.

Potential V1 resolution sequence:

```text
Deterministic matching
        +
Semantic candidate retrieval
        +
LLM classification for ambiguous cases
        ↓
Explainable resolution result
        ↓
Human review where required
```

---

## Success Criteria

Entity Resolution should eventually be measured using a labeled benchmark containing:

- true existing-entity matches;
- ambiguous cases;
- duplicate-like Action Items;
- unrelated evidence;
- new-entity cases.

Important metrics include:

```text
Precision of deterministic matches
Recall of known matches
False-link rate
Duplicate-prevention rate
Human correction rate
Ambiguous-case accuracy
```

False linking is more dangerous than asking for human review, so V0 intentionally favors precision over aggressive automation.
