# Progress Intelligence V0

## Purpose

Progress Intelligence answers the next question after Entity Resolution:

> Once PMWizard knows which Action Item new evidence refers to, what progress does that evidence appear to indicate?

V0 focuses on explicit, explainable status signals in Action Item evidence.

It does not use an LLM.

---

## End-to-End Flow

```text
New Evidence
     ↓
Entity Resolution
     ↓
Existing Action Item
     ↓
Progress Classification
     ↓
┌──────────────────┬───────────────────┬─────────────────┐
│ Status / progress│ Ambiguous signals │ No clear signal │
└──────────────────┴───────────────────┴─────────────────┘
     ↓
AI Suggestion
     ↓
Project Inbox / Human Review
     ↓
Governed Project Memory
```

A Progress Intelligence result never changes governed project state by itself.

---

## V0 Status Signals

The deterministic classifier currently recognizes explicit phrases associated with:

```text
In Progress
Blocked
Pending External
Ready for Review
Completed
```

English and a small set of Spanish phrases are supported.

Examples:

```text
"Verify API access was completed today."
→ suggested status: Completed

"We are waiting for the vendor response."
→ suggested status: Pending External

"The migration is in progress."
→ suggested status: In Progress

"The work is blocked because access is unavailable."
→ suggested status: Blocked
```

---

## Outcomes

### status_change

Evidence contains one clear explicit status signal that differs from the governed Action Item status.

### progress_update

Evidence contains a clear signal that reinforces the current Action Item status.

The suggestion can still update:

- progress summary;
- last progress date;
- latest evidence reference.

### ambiguous

Evidence contains explicit signals for more than one status.

Example:

```text
"Legal review was completed, but two clauses remain unresolved."
```

V0 does not guess whether the overall Action Item is Completed or Blocked.

No suggestion is created.

### no_signal

The Action Item can be identified, but the evidence contains no explicit V0 progress signal.

Example:

```text
"Review contract was discussed today."
```

PMWizard does not invent progress.

---

## Completion Negation

V0 explicitly guards against common negated completion phrases.

Example:

```text
"Validate integration is not completed yet."
```

must not become:

```text
Completed
```

Instead, V0 treats the evidence conservatively as an In Progress signal.

---

## Suggestion Contract

When entity resolution is deterministic and progress classification is clear,
PMWizard creates an `AISuggestion`:

```text
Suggestion Type:
ACTION_PROGRESS

Target:
ActionItem

Proposed changes:
status
progress_summary
last_progress_date
latest_evidence_id

Evidence:
source Evidence ID

Confidence:
explicit lexical-signal confidence

Review status:
Pending
```

The suggestion is persisted separately from governed Project Memory.

---

## Human Governance

The existing Human Review flow remains authoritative:

```text
AI Suggestion
     ↓
Accept / Edit / Reject / Defer
     ↓
Governed Action Item
```

If accepted, the approved fields may update the Action Item and the transition is written to the audit log.

If edited, the PM's corrected values become the governed values.

If rejected, the Action Item remains unchanged.

---

## Interaction with Entity Resolution

Progress Intelligence only runs automatically when Entity Resolution returns:

```text
matched
```

If resolution returns:

```text
needs_review
```

the pipeline stops before progress classification and asks for entity confirmation.

If resolution returns:

```text
no_match
```

no progress suggestion is created.

This avoids interpreting status against the wrong Action Item.

---

## Confidence

V0 confidence is not a calibrated probability.

It is a deterministic confidence value assigned to explicit lexical signals.

Examples:

```text
blocked              0.96
completed            0.95
ready for review     0.94
waiting for          0.92
in progress          0.86
started              0.80
```

Later versions should evaluate confidence calibration against labeled project data.

---

## Security Boundary

Progress Intelligence inherits the same tenant/project boundary used by Entity Resolution.

The caller must authorize:

- the user;
- access to the Project;
- access to the source Evidence.

PMWizard must not expose or reason over unauthorized evidence.

---

## Deferred to Later Versions

V0 deliberately does not include:

- LLM-based interpretation;
- semantic understanding of indirect progress statements;
- progress percentage estimation;
- automatic milestone impact analysis;
- RAID progress classification;
- Decision lifecycle classification;
- automatic Action Item creation;
- autonomous governed-state updates.

Future versions may use the AI Provider Gateway for ambiguous or indirect language, while preserving evidence, confidence, and Human Review.

---

## Example

```text
ACTION-024
Verify API access
Status: In Progress

EMAIL-193
"Verify API access was completed today."

        ↓ Entity Resolution

ACTION-024 matched

        ↓ Progress Intelligence

Suggested status: Completed
Confidence: 0.95

        ↓ AI Suggestion

Governed Action Item remains In Progress

        ↓ Human Review

Accept

        ↓

ACTION-024
Status: Completed
Latest Evidence: EMAIL-193
```

---

## Guiding Principle

> **PMWizard can propose what changed. The Project Manager decides what becomes true.**
